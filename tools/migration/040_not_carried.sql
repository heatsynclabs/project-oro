-- Say out loud what this migration did not carry.
--
-- The legacy users table has forty columns. Twenty six of them arrive: twenty
-- two through 020_migrate.sql, the admin and accountant booleans through
-- 022_roles.sql, the waiver date through 024_waivers.sql, and oriented_by_id
-- through the second pass at the end of this file. Fourteen do not, and an
-- import that goes quiet about that is an import somebody will mistake for
-- complete.
--
-- Two of the fourteen never get this far. 010_preflight.sql refuses to start
-- while any legacy user carries the instructor flag or a payee, because neither
-- has anywhere to go in this schema and both are a person's decision rather
-- than this script's. The counts below are the other twelve.

DO $$
DECLARE
  paid_by      bigint;
  left_saying  bigint;
  member_ints  bigint;
  devise_rows  bigint;
  credentials  bigint;
  oriented     bigint;
BEGIN
  SELECT count(*) FILTER (WHERE payment_method IS NOT NULL AND btrim(payment_method) <> ''),
         count(*) FILTER (WHERE exit_reason IS NOT NULL AND btrim(exit_reason) <> ''),
         count(*) FILTER (WHERE member IS NOT NULL),
         count(*) FILTER (WHERE sign_in_count > 0
                             OR current_sign_in_at IS NOT NULL
                             OR last_sign_in_at IS NOT NULL
                             OR current_sign_in_ip IS NOT NULL
                             OR last_sign_in_ip IS NOT NULL
                             OR reset_password_token IS NOT NULL
                             OR reset_password_sent_at IS NOT NULL
                             OR remember_created_at IS NOT NULL),
         count(*) FILTER (WHERE btrim(encrypted_password) <> ''),
         count(*) FILTER (WHERE oriented_by_id IS NOT NULL)
    INTO paid_by, left_saying, member_ints, devise_rows, credentials, oriented
    FROM legacy.users;

  RAISE NOTICE 'not carried, twelve columns of the forty:';
  RAISE NOTICE '  % member(s) have a payment_method, % an exit_reason, % the legacy member integer. None of the three has a home in this schema and none is read by anything',
    paid_by, left_saying, member_ints;
  RAISE NOTICE '  % member(s) carry Devise session state across eight columns: sign in counts and dates, sign in addresses, and the remember and reset tokens. Dropped on purpose, because a session from the old site is not a session on the new one',
    devise_rows;
  RAISE NOTICE '  % member(s) have an encrypted_password, and it is not carried here on purpose. Credentials go to the identity service, which is a separate database, and tools/identity/ imports them',
    credentials;
  RAISE NOTICE '  the instructor flag and a payee are the other two of the fourteen. Neither reaches here: 010_preflight.sql refuses while either exists, and whoever ran this answered both before it started';

  IF oriented > 0 THEN
    RAISE NOTICE '  % member(s) were oriented by somebody, and that link is carried below', oriented;
  END IF;
END $$;

-- Who oriented whom. A second pass, because it points at another member and
-- every member has to exist before any of them can be pointed at.
--
-- members_updated_at is a BEFORE UPDATE trigger that sets updated_at to now(),
-- so this pass would overwrite the legacy updated_at that 020_migrate.sql had
-- just carried, for exactly the members it touches and no others. That is a
-- column this import says it carries, changed silently by the import itself.
-- The trigger is turned off around the pass and the legacy value written back
-- explicitly, and 030_verify.sql asserts every member kept the timestamp it
-- arrived with.
--
-- One DO block, for the reason 022_roles.sql gives at length: an exception
-- inside a block takes the ALTER back with it, whatever the caller did about
-- transactions or ON_ERROR_STOP.
DO $$
BEGIN
  ALTER TABLE members DISABLE TRIGGER members_updated_at;

  UPDATE members m
     SET oriented_by = by.id,
         updated_at = u.updated_at AT TIME ZONE 'UTC'
    FROM legacy.users u
    JOIN members by ON by.legacy_id = u.oriented_by_id
   WHERE m.legacy_id = u.id
     AND u.oriented_by_id IS NOT NULL;

  ALTER TABLE members ENABLE TRIGGER members_updated_at;

  IF (SELECT tgenabled FROM pg_trigger
       WHERE tgrelid = 'members'::regclass
         AND tgname = 'members_updated_at') <> 'O' THEN
    RAISE EXCEPTION 'members_updated_at did not come back on. Nothing was kept.';
  END IF;
END $$;
