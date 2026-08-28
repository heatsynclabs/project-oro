-- Say out loud what this migration did not carry.
--
-- Members and cards are what 020_migrate.sql writes. The legacy users table has
-- forty columns and eighteen of them do not appear in it, and an import that
-- goes quiet about that is an import somebody will mistake for complete.
--
-- Three of the eighteen are access: admin, instructor and accountant. Those
-- become rows in member_roles, and docs/plan/data-model.md section 6.1 says how
-- and why that is a separate step: the legacy booleans have no approval behind
-- them, so the import that writes them runs with the role trigger disabled
-- inside one transaction and records that they predate the policy. Inventing an
-- approval here would be a lie in an audit trail that exists to be trusted.

DO $$
DECLARE
  admins      bigint;
  instructors bigint;
  accountants bigint;
  waivers     bigint;
  oriented    bigint;
  payees      bigint;
BEGIN
  SELECT count(*) FILTER (WHERE admin),
         count(*) FILTER (WHERE instructor),
         count(*) FILTER (WHERE accountant),
         count(*) FILTER (WHERE waiver IS NOT NULL),
         count(*) FILTER (WHERE oriented_by_id IS NOT NULL),
         count(*) FILTER (WHERE payee IS NOT NULL AND payee <> '')
    INTO admins, instructors, accountants, waivers, oriented, payees
    FROM legacy.users;

  RAISE NOTICE 'not carried, and each needs its own step in phase 3:';
  RAISE NOTICE '  % member(s) are admin, % are instructor, % are accountant. These are roles and they need the exception in data-model.md section 6.1',
    admins, instructors, accountants;
  RAISE NOTICE '  % member(s) have a waiver date. waivers records that one exists and where it is kept, and nobody has said where that is',
    waivers;
  RAISE NOTICE '  % member(s) have a payee, somebody paying on their behalf. There is no column for that yet',
    payees;
  RAISE NOTICE '  payment_method, exit_reason and the legacy member integer have no home in this schema and are not carried';
  RAISE NOTICE '  the Devise session columns are deliberately dropped: sign in counts, addresses, remember and reset tokens';
  RAISE NOTICE '  encrypted_password is not carried here on purpose. Credentials go to the identity service, which is a separate database, and tools/identity/ imports them';

  IF oriented > 0 THEN
    RAISE NOTICE '  % member(s) were oriented by somebody, and that link is carried below', oriented;
  END IF;
END $$;

-- Who oriented whom. A second pass, because it points at another member and
-- every member has to exist before any of them can be pointed at.
UPDATE members m
   SET oriented_by = by.id
  FROM legacy.users u
  JOIN members by ON by.legacy_id = u.oriented_by_id
 WHERE m.legacy_id = u.id
   AND u.oriented_by_id IS NOT NULL;
