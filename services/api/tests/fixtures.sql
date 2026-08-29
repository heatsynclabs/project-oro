-- Three invented people, for the members API suite.
--
-- Rule 13 of CLAUDE.md: nothing here resembles a member. The names are birds
-- and a workshop noun, and .test and .invalid are reserved suffixes nobody can
-- register, so an address here cannot reach a person by accident.
--
-- The three cover the directory's three states. Wren publishes an email and a
-- phone number. Ida is listed and publishes neither, which is the case the
-- phase 3 exit criterion turns on. Solder is a member who is not in the
-- directory at all.
--
-- Applied by services/api/tests/run.sh as the postgres superuser, which
-- bypasses row level security. That is what a fixture needs and it is the
-- reason the suite never queries this way: every check runs through the
-- service, which connects as oro_api_login and cannot bypass anything.

INSERT INTO members
  (id, identity_subject, name, display_name, pronouns, email, phone,
   postal_code, tier_id, joined_on, standing,
   current_skills, desired_skills, emergency_name, emergency_phone,
   email_visible, phone_visible, listed_in_directory)
VALUES
  ('cccccccc-0000-0000-0000-000000000001', 'sub-c-wren',
   'Wren Kestrel', NULL, 'she/her', 'wren@example.test', '480 555 0101',
   '85201', 'basic', '2025-01-06', 'good',
   'lathe, mig welding', 'kiln', 'Ida Bramble', '480 555 0102',
   true, true, true),

  ('cccccccc-0000-0000-0000-000000000002', 'sub-c-ida',
   'Ida Bramble', 'Bram', 'they/them', 'ida@example.test', '480 555 0102',
   '85202', 'volunteer', '2025-03-17', 'unknown',
   'sewing', 'cnc router', NULL, NULL,
   false, false, true),

  ('cccccccc-0000-0000-0000-000000000003', 'sub-c-solder',
   'Solder', NULL, NULL, 'solder@example.invalid', '480 555 0103',
   NULL, 'none', '2024-11-02', 'unknown',
   NULL, NULL, NULL, NULL,
   true, true, false);

-- One live role, so /me has something to put in its roles array. Host rather
-- than admin: db/seed/001_reference.sql gives host grants_roles false, so this
-- needs no approval behind it and spends none of the three bootstrap seats
-- db/migrations/013_bootstrap_three_admins.sql allows.
INSERT INTO member_roles (member_id, role_id, granted_at)
VALUES ('cccccccc-0000-0000-0000-000000000001', 'host', '2025-06-01T17:00:00Z');
