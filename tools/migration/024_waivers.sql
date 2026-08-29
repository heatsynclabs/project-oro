-- The legacy waiver date, carried into waivers.
--
-- docs/plan/data-model.md section 1.5: this system records that a member signed
-- a waiver, when, and where the document is kept. It holds nothing that is on
-- the document, and db/tests/waivers.sql asserts that no column here even could.
--
-- The legacy users table has only the date, so where the document is kept comes
-- from legacy.waiver_documents, which is a person's answer rather than legacy
-- data. 005_staging.sql builds that table and 010_preflight.sql refuses to
-- start while any member who signed is missing from it, so the join below
-- cannot quietly drop anybody.

INSERT INTO waivers (member_id, signed_at, expires_at, storage, reference, recorded_by, note)
SELECT
  m.id,
  -- The legacy column is `timestamp without time zone` and signed_at is
  -- `timestamptz`, so something has to say which zone the naive value is in.
  -- Left implicit it would be read in whatever the session is set to, and the
  -- lab's own zone is America/Phoenix, which would move every waiver seven
  -- hours and leave both sides of the verify agreeing about the wrong answer.
  -- Rails 3.2 stores UTC: `config.time_zone = 'America/Phoenix'` in
  -- config/application.rb is the display zone, and nothing sets
  -- config.active_record.default_timezone, which defaults to :utc.
  u.waiver AT TIME ZONE 'UTC',
  -- The legacy system recorded no expiry and the lab has no written rule that
  -- gives a waiver one, so this stays null rather than being computed from a
  -- policy nobody has agreed. A null expiry is a waiver that has not lapsed,
  -- which is how waiver_status reads it.
  NULL,
  d.storage,
  d.reference,
  -- Somebody recorded each of these in the legacy system and it did not say
  -- who. Naming a member here would be inventing that.
  NULL,
  'Carried from the legacy members database by tools/migration'
  FROM legacy.users u
  JOIN members m ON m.legacy_id = u.id
  JOIN legacy.waiver_documents d ON d.user_id = u.id
 WHERE u.waiver IS NOT NULL
 ORDER BY u.id;

DO $$
DECLARE carried bigint;
BEGIN
  -- Only the rows this import wrote. Counting the whole table would report a
  -- waiver somebody recorded by hand as one this import carried.
  SELECT count(*) INTO carried
    FROM waivers w JOIN members m ON m.id = w.member_id
   WHERE m.legacy_id IS NOT NULL;
  RAISE NOTICE 'waivers: % row(s) carried, each holding a date and where the document is kept and nothing else', carried;
END $$;
