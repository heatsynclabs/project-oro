-- Row level security on the two approval tables, and the table comments that
-- were missing. Rule 10: a table without a comment is a table whose meaning
-- lives only in somebody's memory.

BEGIN;

-- Approvals are an admin matter. Card proposals are a community process that
-- happens in a room, so every member can see who is up for a vote. That
-- asymmetry is deliberate and it is the same one the API design describes.
ALTER TABLE approvals      ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals      FORCE  ROW LEVEL SECURITY;

COMMENT ON TABLE cards IS
  'A physical RFID card. Its identity is a uuid; controller_slot is the EEPROM '
  'address on the door controller and is what the legacy card id becomes.';
COMMENT ON TABLE certifications IS
  'A tool a member can be certified on. validity_months drives expiry where the '
  'lab wants one.';
COMMENT ON TABLE governance_parameter_history IS
  'Append only. Every change to a bylaws number, with who changed it and the '
  'citation they gave. The application role has INSERT and SELECT only.';
COMMENT ON TABLE member_certifications IS
  'One live certification per member per tool, enforced by a partial unique '
  'index so somebody can be certified, revoked, and certified again.';
COMMENT ON TABLE member_roles IS
  'Roles as rows rather than boolean columns, so who granted what and when is '
  'recorded. Revocation is an update, never a delete. Granting a role whose '
  'grants_roles is true needs an approval from a second admin.';
COMMENT ON TABLE roles IS
  'The role vocabulary. No application role may write here: grants_roles '
  'defines the scope of the two approver rule, so changing it is a migration.';

COMMIT;
