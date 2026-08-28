-- Test helpers. Loaded only by db/tests/run.sh, never by a migration.
--
-- Without these, a psql script with ON_ERROR_STOP off prints each error after
-- the *next* label, so reading the output means counting lines backwards. With
-- them a test reads as a list of assertions and the output says what happened.

CREATE SCHEMA IF NOT EXISTS t;
-- Tests switch role to exercise the policies as a real member would, so the
-- helpers have to be callable from those roles too.
GRANT USAGE ON SCHEMA t TO PUBLIC;

CREATE OR REPLACE PROCEDURE t.must_fail(what text, stmt text, want text DEFAULT '')
LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE stmt;
  EXCEPTION WHEN others THEN
    IF want <> '' AND position(lower(want) in lower(SQLERRM)) = 0 THEN
      RAISE NOTICE 'FAIL % (refused, but for the wrong reason: %)', what, SQLERRM;
    ELSE
      RAISE NOTICE 'ok   %', what;
    END IF;
    RETURN;
  END;
  RAISE NOTICE 'FAIL % (this was allowed and must not be)', what;
END $$;

CREATE OR REPLACE PROCEDURE t.must_pass(what text, stmt text)
LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE stmt;
  RAISE NOTICE 'ok   %', what;
EXCEPTION WHEN others THEN
  RAISE NOTICE 'FAIL % (refused: %)', what, SQLERRM;
END $$;

CREATE OR REPLACE PROCEDURE t.must_equal(what text, got anyelement, want anyelement)
LANGUAGE plpgsql AS $$
BEGIN
  IF got IS NOT DISTINCT FROM want THEN
    RAISE NOTICE 'ok   %', what;
  ELSE
    RAISE NOTICE 'FAIL % (got %, wanted %)', what, got, want;
  END IF;
END $$;

-- A comment in the test output. Deliberately a NOTICE rather than \echo:
-- \echo writes to stdout and NOTICE writes to stderr, so mixing them makes the
-- output order depend on buffering, and the suite goes flaky.
CREATE OR REPLACE PROCEDURE t.note(what text)
LANGUAGE plpgsql AS $$ BEGIN RAISE NOTICE '--   %', what; END $$;

-- Postgres refuses a subquery as a CALL argument, so a test that wants to
-- assert on a query result passes the query as text and this runs it.
CREATE OR REPLACE PROCEDURE t.must_query(what text, stmt text, want text)
LANGUAGE plpgsql AS $$
DECLARE got text;
BEGIN
  EXECUTE stmt INTO got;
  IF got IS NOT DISTINCT FROM want THEN
    RAISE NOTICE 'ok   %', what;
  ELSE
    RAISE NOTICE 'FAIL % (got %, wanted %)', what, coalesce(got,'<null>'), coalesce(want,'<null>');
  END IF;
EXCEPTION WHEN others THEN
  RAISE NOTICE 'FAIL % (query failed: %)', what, SQLERRM;
END $$;

-- Run after every helper is defined, so a role-switching test can call them.
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA t TO PUBLIC;
