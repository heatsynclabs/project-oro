-- Refuse to start if the legacy data holds anything the migration must not
-- decide on its own.
--
-- docs/plan/data-model.md section 6.2: "The migration names offending rows. It
-- does not truncate, renumber, or skip them." So this runs first, gathers every
-- offender, and raises with the list. A migration that fixed these quietly
-- would be a migration nobody could audit afterwards.
--
-- Each check is one of the questions phase 0 of
-- docs/plan/order-of-operations.md asks of the production data, so a run of
-- this against the staging copy is also the answer to that phase.

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

  IF array_length(problems, 1) > 0 THEN
    RAISE EXCEPTION E'the legacy data holds % thing(s) a person has to decide:\n  %',
      array_length(problems, 1), array_to_string(problems, E'\n  ')
      USING HINT = 'docs/plan/data-model.md section 6.3 gives each of these an owner. '
                   'Resolve them on the staging copy, then run this again.';
  END IF;

  RAISE NOTICE 'preflight: nothing in the legacy data needs a decision';
END $$;
