-- What a restore has to reproduce. Printed with psql -tA before the backup is
-- taken and again after the restore, and the two are compared line by line.
--
-- Row counts on their own would pass a restore that carried every row and put
-- a card at a different slot. A slot is an EEPROM address on the door
-- controller, so renumbering maps every member to the wrong door permission,
-- which is why tools/migration/030_verify.sql refuses to finish if any card
-- moved and why every slot is printed here one card at a time.

-- Every table in the database, counted for real. reltuples is an estimate and
-- would agree with itself while rows went missing. The list comes from the
-- catalog rather than being written out here, so a table added later is
-- covered without anybody remembering to come back to this file.
SELECT format('table %s.%s %s rows', table_schema, table_name,
              (xpath('/row/c/text()',
                     query_to_xml(format('SELECT count(*) AS c FROM %I.%I',
                                         table_schema, table_name),
                                  false, true, '')))[1]::text)
  FROM information_schema.tables
 WHERE table_type = 'BASE TABLE'
   AND table_schema NOT IN ('pg_catalog', 'information_schema')
 ORDER BY table_schema, table_name;

-- Every ORDER BY here ends on a primary key. Two snapshots of the same data
-- are compared line by line, and a sort that leaves rows tied puts them in
-- whatever order the heap happens to hold them, which a restore changes. That
-- reports a difference where there is none, and worse, it lines two different
-- rows up against each other and reports a match where there is a difference.
-- legacy_id is null on every card issued after the migration, so cards tie.
SELECT format('card %s at slot %s, tag %s', legacy_id, controller_slot, tag_number)
  FROM cards
 ORDER BY legacy_id, controller_slot, tag_number, id;

SELECT format('member %s holds %s, revoked %s',
              coalesce(m.legacy_id::text, 'with no legacy id'),
              r.role_id,
              coalesce(r.revoked_at::text, 'no'))
  FROM member_roles r
  JOIN members m ON m.id = r.member_id
-- A role revoked and granted again is two rows for one member and one role, and
-- member_roles carries a surrogate key for exactly that reason.
 ORDER BY m.legacy_id, m.id, r.role_id, r.revoked_at, r.id;

-- A sequence that came back at 1 hands out an id somebody already holds.
SELECT format('sequence %s.%s last value %s',
              schemaname, sequencename, coalesce(last_value::text, 'unset'))
  FROM pg_sequences
 ORDER BY schemaname, sequencename;

-- The access control layer travels in the archive with everything else, and a
-- restore that dropped it would look complete: every row present, and every
-- member able to read every other member's address.
SELECT format('policy %s on %s.%s for %s',
              policyname, schemaname, tablename, array_to_string(roles, ' and '))
  FROM pg_policies
 ORDER BY schemaname, tablename, policyname;

SELECT format('row security on %s.%s enabled %s forced %s',
              n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity)
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind = 'r'
   AND n.nspname NOT IN ('pg_catalog', 'information_schema')
 ORDER BY n.nspname, c.relname;

-- The database roles the archive's grants name. No policy names a role: they
-- all default to PUBLIC, and 004_security.sql needs oro_api and door_reader for
-- its GRANT statements instead. Roles are cluster wide, so they are not inside
-- the archive of one database, and a restore into a cluster that has never
-- heard of them fails on the first GRANT. tools/backup/backup.sh writes them to
-- a second file for that reason.
SELECT format('database role %s', rolname)
  FROM pg_roles
 WHERE rolname IN ('oro_api', 'door_reader')
 ORDER BY rolname;
