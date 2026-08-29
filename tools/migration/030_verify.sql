-- The assertions in docs/plan/data-model.md section 6.2, checked after the fact.
--
-- The preflight refuses what a person has to decide. These check what the
-- migration itself did, which is a different question: a preflight that passed
-- and a migration that carried everything correctly are two claims, and only
-- the second one is what the lab gets.

DO $$
DECLARE
  wrong  bigint;
  detail text;
BEGIN
  -- Not negotiable, in that document's words. controller_slot must equal the
  -- legacy card id for every row.
  SELECT count(*), string_agg(format('card %s is at slot %s', legacy_id, controller_slot),
                              ', ' ORDER BY legacy_id)
    INTO wrong, detail
    FROM cards WHERE controller_slot IS DISTINCT FROM legacy_id;
  IF wrong > 0 THEN
    RAISE EXCEPTION 'a card changed slot: %', detail;
  END IF;

  SELECT count(*) INTO wrong FROM cards
   WHERE controller_slot IS NULL OR controller_slot NOT BETWEEN 10 AND 199;
  IF wrong > 0 THEN
    RAISE EXCEPTION '% card(s) are outside slots 10 to 199', wrong;
  END IF;

  SELECT count(*) INTO wrong
    FROM (SELECT controller_slot FROM cards
           GROUP BY controller_slot HAVING count(*) > 1) AS shared;
  IF wrong > 0 THEN
    RAISE EXCEPTION '% slot(s) are held by more than one card', wrong;
  END IF;

  -- Every legacy user arrived, or is named as deliberately skipped. Nothing
  -- here skips anybody, so the count has to match exactly.
  SELECT count(*) INTO wrong
    FROM legacy.users u LEFT JOIN members m ON m.legacy_id = u.id
   WHERE m.id IS NULL;
  IF wrong > 0 THEN
    SELECT string_agg(format('user %s', u.id), ', ' ORDER BY u.id) INTO detail
      FROM legacy.users u LEFT JOIN members m ON m.legacy_id = u.id
     WHERE m.id IS NULL;
    RAISE EXCEPTION '% legacy member(s) did not arrive: %', wrong, detail;
  END IF;

  SELECT count(*) INTO wrong
    FROM legacy.cards c LEFT JOIN cards n ON n.legacy_id = c.id
   WHERE n.id IS NULL;
  IF wrong > 0 THEN
    RAISE EXCEPTION '% legacy card(s) did not arrive', wrong;
  END IF;

  -- A tag that is not normalised the same way on both sides makes the reconcile
  -- loop rewrite every slot on every pass while reporting success.
  SELECT count(*) INTO wrong FROM cards WHERE tag_number <> upper(tag_number);
  IF wrong > 0 THEN
    RAISE EXCEPTION '% card tag(s) are not uppercase', wrong;
  END IF;

  -- Who oriented whom points at another member, so it is carried by a second
  -- pass after every member exists. If that pass silently did nothing, the
  -- migration looks complete and the link is gone.
  SELECT count(*) INTO wrong
    FROM legacy.users u
    JOIN members m ON m.legacy_id = u.id
   WHERE u.oriented_by_id IS NOT NULL AND m.oriented_by IS NULL;
  IF wrong > 0 THEN
    RAISE EXCEPTION '% member(s) lost who oriented them', wrong;
  END IF;

  RAISE NOTICE 'verify: % member(s) and % card(s), every card at the slot it had',
    (SELECT count(*) FROM members), (SELECT count(*) FROM cards);
END $$;

-- Roles and waivers, checked the same way and in their own block.
--
-- 022_roles.sql turns the role grant trigger off to write its rows, so for the
-- length of that statement nothing in the database is checking. These are what
-- stands in its place, and they are the only reason turning it off is safe.
--
-- One half of "exactly one live role row per member per role" is not here, on
-- purpose. db/migrations/002_access.sql builds member_roles_one_live, a partial
-- unique index over (member_id, role_id) where revoked_at is null, and an index
-- cannot be turned off by name the way a trigger can. A second live admin row
-- for the same member fails at the INSERT. What is left to check is that every
-- legacy flag produced a row and that no row appeared without one.

DO $$
DECLARE
  wrong  bigint;
  detail text;
BEGIN
  SELECT count(*), string_agg(format('user %s (%s)', u.id, u.name), ', ' ORDER BY u.id)
    INTO wrong, detail
    FROM legacy.users u
   WHERE u.admin
     AND NOT EXISTS (SELECT 1 FROM members m JOIN member_roles r ON r.member_id = m.id
                      WHERE m.legacy_id = u.id AND r.role_id = 'admin'
                        AND r.revoked_at IS NULL);
  IF wrong > 0 THEN
    RAISE EXCEPTION '% legacy admin(s) did not get the role: %', wrong, detail;
  END IF;

  SELECT count(*), string_agg(format('user %s (%s)', u.id, u.name), ', ' ORDER BY u.id)
    INTO wrong, detail
    FROM legacy.users u
   WHERE u.accountant
     AND NOT EXISTS (SELECT 1 FROM members m JOIN member_roles r ON r.member_id = m.id
                      WHERE m.legacy_id = u.id AND r.role_id = 'accountant'
                        AND r.revoked_at IS NULL);
  IF wrong > 0 THEN
    RAISE EXCEPTION '% legacy accountant(s) did not get the role: %', wrong, detail;
  END IF;

  -- The other direction, and the expensive one. A role nobody held in the
  -- legacy system is a role this import handed out, and admin is the most
  -- expensive thing in this database to hand out by accident.
  SELECT count(*), string_agg(format('member %s (%s) holds %s',
                                     coalesce(m.legacy_id::text, 'with no legacy id'),
                                     m.name, r.role_id),
                              ', ' ORDER BY m.legacy_id, r.role_id)
    INTO wrong, detail
    FROM member_roles r JOIN members m ON m.id = r.member_id
   WHERE r.revoked_at IS NULL
     -- Only rows this import could have written. A member with no legacy_id
     -- was not carried by it, and the bootstrap admins that
     -- db/migrations/013_bootstrap_three_admins.sql exists to allow are exactly
     -- that shape. Aborting an import because the lab already seated an admin
     -- would be this check refusing the thing the schema is designed for.
     AND m.legacy_id IS NOT NULL
     AND NOT EXISTS (
       SELECT 1 FROM legacy.users u
        WHERE u.id = m.legacy_id
          AND ((r.role_id = 'admin' AND u.admin)
            OR (r.role_id = 'accountant' AND u.accountant)));
  IF wrong > 0 THEN
    RAISE EXCEPTION '% role(s) exist that no legacy flag asked for: %', wrong, detail;
  END IF;

  -- A waiver that arrived with a different date, or with a blank storage, is a
  -- waiver nobody can find again. storage is NOT NULL, so blank is the only way
  -- through, and an empty string satisfies a NOT NULL.
  SELECT count(*), string_agg(format('user %s (%s)', u.id, u.name), ', ' ORDER BY u.id)
    INTO wrong, detail
    FROM legacy.users u
   WHERE u.waiver IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM members m JOIN waivers w ON w.member_id = m.id
                      WHERE m.legacy_id = u.id AND w.signed_at = u.waiver AT TIME ZONE 'UTC'
                        AND btrim(coalesce(w.storage, '')) <> '');
  IF wrong > 0 THEN
    RAISE EXCEPTION '% legacy waiver date(s) did not arrive with the date and a storage: %',
      wrong, detail;
  END IF;

  SELECT count(*), string_agg(format('member %s has %s waivers', m.legacy_id, n.how_many),
                              ', ' ORDER BY m.legacy_id)
    INTO wrong, detail
    FROM (SELECT member_id, count(*) AS how_many FROM waivers
           GROUP BY member_id HAVING count(*) > 1) AS n
    JOIN members m ON m.id = n.member_id;
  IF wrong > 0 THEN
    RAISE EXCEPTION 'one legacy waiver date became more than one row: %', detail;
  END IF;

  SELECT count(*), string_agg(format('member %s (%s)',
                                     coalesce(m.legacy_id::text, 'with no legacy id'), m.name),
                              ', ' ORDER BY m.legacy_id)
    INTO wrong, detail
    FROM waivers w JOIN members m ON m.id = w.member_id
   WHERE m.legacy_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM legacy.users u
                      WHERE u.id = m.legacy_id AND u.waiver IS NOT NULL);
  IF wrong > 0 THEN
    RAISE EXCEPTION '% waiver(s) exist for members who never signed one: %', wrong, detail;
  END IF;

  -- updated_at is carried, and the oriented_by second pass in 040 fires a
  -- BEFORE UPDATE trigger that would set it to now() for the members it
  -- touches. That is a silent rewrite of a column this import claims to carry,
  -- and it shows up on some members and not others, which is the hardest kind
  -- to notice. 040 turns the trigger off around the pass; this is what holds it.
  SELECT count(*), string_agg(format('member %s', u.id), ', ' ORDER BY u.id)
    INTO wrong, detail
    FROM legacy.users u
    JOIN members m ON m.legacy_id = u.id
   WHERE m.updated_at IS DISTINCT FROM (u.updated_at AT TIME ZONE 'UTC');
  IF wrong > 0 THEN
    RAISE EXCEPTION '% member(s) did not keep the updated_at they arrived with: %',
      wrong, detail;
  END IF;

  -- Counted the same way the roles above are: only what this import wrote.
  -- Rule 13. The legacy schema is staging, not a keepsake, and nothing in this
  -- repository drops it. It is left standing on purpose so that whoever ran the
  -- import can compare against the source, and that means a second copy of every
  -- member's address, phone, emergency contact and password hash is sitting in
  -- the database this system is about to serve from. Saying so here is the only
  -- reminder anybody gets.
  RAISE NOTICE 'the legacy schema is still in this database, with % member row(s) and their encrypted_password. It is staging and not a backup. Drop it with DROP SCHEMA legacy CASCADE once this import has been checked',
    (SELECT count(*) FROM legacy.users);

  RAISE NOTICE 'verify: % role(s) and % waiver(s) carried, and nothing that no legacy row asked for',
    (SELECT count(*) FROM member_roles r JOIN members m ON m.id = r.member_id
      WHERE r.revoked_at IS NULL AND m.legacy_id IS NOT NULL),
    (SELECT count(*) FROM waivers w JOIN members m ON m.id = w.member_id
      WHERE m.legacy_id IS NOT NULL);
END $$;
