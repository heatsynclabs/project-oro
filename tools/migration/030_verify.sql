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
