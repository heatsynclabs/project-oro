-- The legacy admin and accountant booleans, carried into member_roles.
--
-- docs/plan/data-model.md section 6.1: these booleans have no approval behind
-- them, and inventing one would be a lie in an audit trail that exists to be
-- trusted. So this runs with the role grant trigger disabled, writes granted_by
-- NULL and approval_id NULL, and then names every member it granted to. That
-- listing is the log the deliberate, logged exception in section 6.1 asks for.
-- Without it the exception is only deliberate.
--
-- Only role_grant_rules is turned off, and only by name. arm_the_rule is a
-- separate trigger on the same table and stays on, so if these grants take the
-- lab to three admins the two approver rule arms itself here and the bootstrap
-- escape closes for good, exactly as it would have had a person made the grants
-- by hand.
--
-- The legacy instructor boolean is not carried. An instructor in this schema is
-- an instructor on one tool, and 010_preflight.sql refuses to start while any
-- legacy user still carries the global flag.

-- Everything that turns the trigger off, writes, and turns it back on is inside
-- one DO block, and that is the whole safety argument. A DO block is a single
-- statement, so an exception anywhere in it rolls back the ALTER as well, and it
-- does that whether or not the caller opened a transaction and whether or not
-- psql was given ON_ERROR_STOP.
--
-- An earlier version put the guard in its own DO block and the ALTER in a
-- statement after it. That does not work. RAISE EXCEPTION aborts its own
-- statement, and in autocommit psql goes on to the next one, so the trigger was
-- turned off and committed by the very script that had just refused to do it.
--
-- Turning a trigger off needs ownership of the table and takes a
-- ShareRowExclusiveLock on member_roles until the transaction ends, so anybody
-- writing a role grant while an import runs waits. Both are reasons this runs as
-- the owner against a staging copy and not as oro_api against a live one.
DO $$
BEGIN
  -- pg_current_xact_id_if_assigned() is null until the transaction has written
  -- something. 020_migrate.sql has written every member by the time this runs,
  -- so inside the migration's transaction it is set, and on its own it is not.
  IF pg_current_xact_id_if_assigned() IS NULL THEN
    RAISE EXCEPTION 'The role step has to run after the members it grants to, '
                    'inside the migration transaction. Nothing was changed.'
      USING HINT = 'Run tools/migration/run.sh, which wraps every step from '
                   '010_preflight.sql onward in one transaction.';
  END IF;

  ALTER TABLE member_roles DISABLE TRIGGER role_grant_rules;

  -- granted_at is left to its default, which is when this import ran. The legacy
  -- users table records no date for when somebody was made an admin: the column
  -- is a bare boolean. created_at is when the member joined, and putting that on
  -- a grant would be a date nobody can stand behind.
  --
  -- 010_preflight.sql has already refused any member who is flagged here and
  -- carries an exit_reason, so nobody who left the lab reaches these two
  -- statements still holding a role.
  INSERT INTO member_roles (member_id, role_id, granted_by, approval_id)
  SELECT m.id, 'admin', NULL, NULL
    FROM legacy.users u
    JOIN members m ON m.legacy_id = u.id
   WHERE u.admin
   ORDER BY u.id;

  INSERT INTO member_roles (member_id, role_id, granted_by, approval_id)
  SELECT m.id, 'accountant', NULL, NULL
    FROM legacy.users u
    JOIN members m ON m.legacy_id = u.id
   WHERE u.accountant
   ORDER BY u.id;

  ALTER TABLE member_roles ENABLE TRIGGER role_grant_rules;

  -- The postcondition, checked rather than assumed. If this ever reads anything
  -- but enabled, the import stops here and the whole transaction goes back,
  -- rather than committing a database whose role grants nothing is guarding.
  IF (SELECT tgenabled FROM pg_trigger
       WHERE tgrelid = 'member_roles'::regclass
         AND tgname = 'role_grant_rules') <> 'O' THEN
    RAISE EXCEPTION 'role_grant_rules did not come back on. Nothing was kept.';
  END IF;
END $$;

-- The log. Separate from the block above because it only reads, and keeping the
-- writing block short enough to hold in the head is worth more than one block.
DO $$
DECLARE granted record;
BEGIN
  RAISE NOTICE 'roles carried from the legacy booleans, every one of them with no approval behind it:';
  -- Only the rows those two statements wrote. Selecting every live grant with a
  -- null approval_id would also name the bootstrap admins the lab seated by
  -- hand, under a heading that says this import granted them.
  FOR granted IN
    SELECT m.legacy_id, m.name, r.role_id, r.granted_at
      FROM member_roles r
      JOIN members m ON m.id = r.member_id
      JOIN legacy.users u ON u.id = m.legacy_id
     WHERE r.approval_id IS NULL AND r.revoked_at IS NULL
       AND ((r.role_id = 'admin' AND u.admin)
         OR (r.role_id = 'accountant' AND u.accountant))
     ORDER BY m.legacy_id, r.role_id
  LOOP
    RAISE NOTICE '  member % (%) now holds %, granted by nobody, recorded %',
      granted.legacy_id, granted.name, granted.role_id, granted.granted_at;
  END LOOP;
  RAISE NOTICE '  that timestamp is when this import ran. It is not when the role was given, which the legacy system never recorded';

  -- Both branches say something. An import that leaves a bootstrap seat open is
  -- the quieter outcome and the one worth hearing about, so it does not get to
  -- be the silent one.
  IF EXISTS (SELECT 1 FROM two_approver_armed) THEN
    RAISE NOTICE '  the two approver rule armed itself while these landed. Every admin grant after this one needs an approval from a second admin';
  ELSE
    RAISE NOTICE '  the two approver rule has NOT armed: % of % bootstrap admin grant(s) are used, so a further admin can still be granted with no approval behind it. Seat the remaining admin(s) and it closes',
      bootstrap_admin_grants_used(), bootstrap_admin_quota();
  END IF;
END $$;
