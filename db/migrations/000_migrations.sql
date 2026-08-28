-- Which migrations have been applied to this database.
--
-- Applying db/migrations/*.sql in filename order to an empty database is fine
-- for a test run and wrong for a real one, because nothing records what already
-- ran. This table is what makes a second apply safe.

BEGIN;

CREATE TABLE schema_migrations (
  filename    text PRIMARY KEY,
  sha256      text NOT NULL,
  applied_at  timestamptz NOT NULL DEFAULT now(),
  applied_by  text NOT NULL DEFAULT current_user
);

COMMENT ON TABLE schema_migrations IS
  'One row per applied migration. sha256 is of the file as applied, so a '
  'migration edited after it ran is detectable rather than silent. Nothing '
  'grants the application role access here: migrations are an operator action.';

COMMIT;
