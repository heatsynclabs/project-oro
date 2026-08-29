-- One person: a member row, and the admin role on it.
--
-- Read by tools/bootstrap/database.py, which supplies subject, email and name
-- as psql variables. Not a migration and not part of db/migrations: it writes
-- rows rather than schema, and it runs when a person runs the command.
--
-- One transaction, because a member row written for somebody the database then
-- refuses to make an admin is a row nobody asked for.
--
-- The insert is guarded by NOT EXISTS rather than left to the unique index. A
-- second run without the guard reaches the role grant trigger before the index,
-- and is refused for needing an approval, which is a confusing answer to
-- "seat the people who are already seated". With the guard a second run inserts
-- no rows, so no trigger fires and nothing is written.
BEGIN;

SELECT link_or_create_member(:'subject', :'email', :'name') AS member_id \gset

INSERT INTO member_roles (member_id, role_id)
SELECT :'member_id'::uuid, 'admin'
 WHERE NOT EXISTS (SELECT 1 FROM member_roles
                    WHERE member_id = :'member_id'::uuid
                      AND role_id = 'admin'
                      AND revoked_at IS NULL);

-- The member id, and 1 when this call took a seat or 0 when it was already
-- held. ROW_COUNT is psql's count of the statement above.
SELECT :'member_id' || ' ' || :ROW_COUNT;

COMMIT;
