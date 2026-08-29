-- Refuse to start if the legacy data holds anything the migration must not
-- decide on its own.
--
-- docs/plan/data-model.md section 6.2: "The migration names offending rows. It
-- does not truncate, renumber, or skip them." So this runs first, gathers every
-- offender, and raises with the list. A migration that fixed these quietly
-- would be a migration nobody could audit afterwards.
--
-- Several of these checks are questions phase 0 of
-- docs/plan/order-of-operations.md asks of the production data, so a run of
-- this against the staging copy answers those. It does not answer all of them:
-- what `contracts` holds and the spread of bcrypt cost prefixes are not
-- questions about rows this migration writes, and neither is checked here.

DO $$
DECLARE
  problems text[] := ARRAY[]::text[];
  detail   text;
BEGIN
  -- A slot is an EEPROM address. The firmware's usable range is 10 to 199, and
  -- the new schema refuses anything else outright, so a card outside it has to
  -- be decided by a person before this runs at all.
  SELECT string_agg(format('card %s (tag %s)', id, card_number), ', ' ORDER BY id)
    INTO detail FROM legacy.cards WHERE id < 10 OR id > 199;
  IF detail IS NOT NULL THEN
    problems := problems || format('cards outside slots 10 to 199: %s', detail);
  END IF;

  -- There are no foreign keys anywhere in the legacy schema, so a card can
  -- point at a user that was deleted. An active card belonging to nobody is a
  -- security finding rather than a data error.
  SELECT string_agg(format('card %s (tag %s, user_id %s)', c.id, c.card_number, c.user_id),
                    ', ' ORDER BY c.id)
    INTO detail
    FROM legacy.cards c LEFT JOIN legacy.users u ON u.id = c.user_id
   WHERE u.id IS NULL;
  IF detail IS NOT NULL THEN
    problems := problems || format('cards owned by nobody: %s', detail);
  END IF;

  -- email is citext UNIQUE on the new side. Two blanks collide, and so do two
  -- addresses differing only in case.
  SELECT string_agg(format('%s (%s rows)', lower(email), n), ', ' ORDER BY lower(email))
    INTO detail
    FROM (SELECT lower(email) AS email, count(*) AS n FROM legacy.users
           WHERE email IS NOT NULL AND email <> ''
           GROUP BY lower(email) HAVING count(*) > 1) AS d;
  IF detail IS NOT NULL THEN
    problems := problems || format('email addresses used more than once: %s', detail);
  END IF;

  SELECT string_agg(format('user %s (%s)', id, name), ', ' ORDER BY id)
    INTO detail FROM legacy.users WHERE email IS NULL OR email = '';
  IF detail IS NOT NULL THEN
    problems := problems || format('members with no email address: %s', detail);
  END IF;

  -- name is the one NOT NULL column on members with no default.
  SELECT string_agg(format('user %s', id), ', ' ORDER BY id)
    INTO detail FROM legacy.users WHERE name IS NULL OR name = '';
  IF detail IS NOT NULL THEN
    problems := problems || format('members with no name: %s', detail);
  END IF;

  -- The door service knows permission 1. Anything else is a mask nobody here
  -- has decided the meaning of.
  SELECT string_agg(format('card %s (permission %s)', id, card_permissions), ', ' ORDER BY id)
    INTO detail FROM legacy.cards WHERE card_permissions IS DISTINCT FROM 1;
  IF detail IS NOT NULL THEN
    problems := problems || format('cards carrying a permission other than 1: %s', detail);
  END IF;

  -- A tag has to survive the new schema's format check.
  SELECT string_agg(format('card %s (tag %L)', id, card_number), ', ' ORDER BY id)
    INTO detail FROM legacy.cards
   WHERE card_number IS NULL
      OR upper(regexp_replace(card_number, '^0+', '')) !~ '^[0-9A-F]{1,8}$';
  IF detail IS NOT NULL THEN
    problems := problems || format('cards whose tag is not hex: %s', detail);
  END IF;

  -- The legacy instructor boolean is global. In this schema an instructor is
  -- per certification and never global, which docs/glossary.md states and
  -- db/migrations/002_access.sql builds as certification_instructors, keyed on
  -- (member_id, certification_id). db/seed/001_reference.sql seeds no
  -- instructor role and no certifications at all, so a global flag has nothing
  -- here to point at. There is no arithmetic that turns one into the other.
  SELECT string_agg(format('user %s (%s)', id, name), ', ' ORDER BY id)
    INTO detail FROM legacy.users WHERE instructor;
  IF detail IS NOT NULL THEN
    problems := problems || format(
      'members carrying the legacy instructor flag: %s. An instructor here is '
      'an instructor on one tool, so somebody has to say which certifications '
      'each of these people may sign off, or say that the flag is dropped and '
      'the grants are made again by hand later', detail);
  END IF;

  -- A payee is the name of somebody paying on another member's behalf. Nothing
  -- in this schema holds that: db/migrations/001_schema.sql has no such column
  -- on members and db/migrations/002_access.sql has none on payments.
  SELECT string_agg(format('user %s (%s), payee %L', id, name, payee), ', ' ORDER BY id)
    INTO detail FROM legacy.users WHERE payee IS NOT NULL AND btrim(payee) <> '';
  IF detail IS NOT NULL THEN
    problems := problems || format(
      'members with a payee, somebody paying on their behalf: %s. There is no '
      'column for that anywhere in this schema, so somebody has to say where it '
      'goes or that it is dropped', detail);
  END IF;

  -- waivers.storage is NOT NULL, and a reference identifies one document rather
  -- than the lot, so neither can be guessed from a date. 005_staging.sql builds
  -- the table this reads and says why it is not legacy data.
  SELECT string_agg(format('user %s (%s), signed %s', u.id, u.name, u.waiver), ', ' ORDER BY u.id)
    INTO detail
    FROM legacy.users u
    LEFT JOIN legacy.waiver_documents d ON d.user_id = u.id
   WHERE u.waiver IS NOT NULL AND d.user_id IS NULL;
  IF detail IS NOT NULL THEN
    problems := problems || format(
      'members who signed a waiver with no row in legacy.waiver_documents: %s. '
      'This system records where a signed waiver is kept, never the document, '
      'so somebody has to say where each of these is before it can be carried',
      detail);
  END IF;

  -- The other direction. A document row whose member never signed is a row
  -- somebody typed by hand, and the likeliest way one exists is a user_id typed
  -- wrong, which also means the member it was meant for has no document and is
  -- caught above. Named here rather than discarded, because 024_waivers.sql
  -- would simply not use it and say nothing.
  SELECT string_agg(format('user %s', d.user_id), ', ' ORDER BY d.user_id)
    INTO detail
    FROM legacy.waiver_documents d
    JOIN legacy.users u ON u.id = d.user_id
   WHERE u.waiver IS NULL;
  IF detail IS NOT NULL THEN
    problems := problems || format(
      'rows in legacy.waiver_documents for members who never signed a waiver: '
      '%s. Nothing would carry these, so either the member signed and the date '
      'is missing, or the user_id is wrong', detail);
  END IF;

  -- A legacy admin or accountant flag that nobody cleared when the person left.
  -- 022_roles.sql would carry it into a live, unrevoked role, so somebody who
  -- walked out years ago would come out of the import able to grant admin. The
  -- legacy system records a departure in exit_reason and nothing ever went back
  -- and cleared the booleans, so the two facts sit in the same row and disagree.
  -- This is the same shape as a card belonging to nobody: a security finding
  -- rather than a data error, and not this script's to settle.
  SELECT string_agg(format('user %s (%s), %s, left saying %L',
                           id, name,
                           concat_ws(' and ',
                                     CASE WHEN admin THEN 'admin' END,
                                     CASE WHEN accountant THEN 'accountant' END),
                           exit_reason), ', ' ORDER BY id)
    INTO detail FROM legacy.users
   WHERE (admin OR accountant)
     AND exit_reason IS NOT NULL AND btrim(exit_reason) <> '';
  IF detail IS NOT NULL THEN
    problems := problems || format(
      'members who hold a role flag and have an exit_reason: %s. Carrying these '
      'would grant a live role to somebody who left, so somebody has to say for '
      'each whether they are still that thing', detail);
  END IF;

  IF array_length(problems, 1) > 0 THEN
    RAISE EXCEPTION E'the legacy data holds % thing(s) a person has to decide:\n  %',
      array_length(problems, 1), array_to_string(problems, E'\n  ')
      USING HINT = 'docs/plan/data-model.md section 6.3 gives most of these an owner, '
                   'and the rest are the same kind of question. Resolve them on the '
                   'staging copy, then run this again.';
  END IF;

  RAISE NOTICE 'preflight: nothing in the legacy data needs a decision';
END $$;
