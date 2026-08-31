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

-- Anvil pays at the highest tier, joined years ago, and is lapsed. Nobody else
-- in this fixture can reach the standing branch of card_eligibility: every
-- other member fails on tier or on tenure first, and the function stops at the
-- first rule that fails. Not in the directory, so the directory checks still
-- see exactly two people.
INSERT INTO members
  (id, identity_subject, name, email, tier_id, joined_on, standing,
   listed_in_directory)
VALUES
  ('cccccccc-0000-0000-0000-000000000004', 'sub-c-anvil',
   'Anvil', 'anvil@example.test', 'plus', '2023-04-11', 'lapsed', false);

-- Wren holds one live card and one she lost. Solder holds one, which is the
-- card nobody else may read.
--
-- The slot on Wren's live card is what makes the withholding check mean
-- something: an endpoint that handed back the whole row would hand back an
-- EEPROM address that exists.
INSERT INTO cards
  (id, member_id, tag_number, controller_slot, label, active, issued_at,
   revoked_at, revoked_reason)
VALUES
  ('dddddddd-0000-0000-0000-000000000001',
   'cccccccc-0000-0000-0000-000000000001', 'A1B2C4D9', 42,
   'Front desk spare', true, '2025-02-01T18:00:00Z', NULL, NULL),
  ('dddddddd-0000-0000-0000-000000000002',
   'cccccccc-0000-0000-0000-000000000001', 'BEEF0002', NULL,
   NULL, false, '2024-09-01T18:00:00Z', '2025-05-01T18:00:00Z',
   'Left in a taxi.'),
  ('dddddddd-0000-0000-0000-000000000003',
   'cccccccc-0000-0000-0000-000000000003', 'FEED0003', 43,
   NULL, true, '2025-01-15T18:00:00Z', NULL, NULL);

-- Two tools. db/seed/001_reference.sql seeds no certifications at all, so
-- these are the fixture's own.
INSERT INTO certifications (id, name, description, validity_months, active)
VALUES
  ('laser', 'Laser cutter', 'The big laser, and only the big laser', 24, true),
  ('mill', 'Manual mill', NULL, NULL, true);

-- Wren is certified on the laser and was certified on the mill until somebody
-- took it back. A revoked grant stays in the list, which is the behaviour the
-- contract describes and the reason both are here.
INSERT INTO member_certifications
  (member_id, certification_id, granted_at, expires_at, revoked_at,
   revoked_reason, note)
VALUES
  ('cccccccc-0000-0000-0000-000000000001', 'laser',
   '2025-03-01T18:00:00Z', '2027-03-01T18:00:00Z', NULL, NULL,
   'Signed off on the sample cut'),
  ('cccccccc-0000-0000-0000-000000000001', 'mill',
   '2025-04-01T18:00:00Z', NULL, '2025-06-01T18:00:00Z',
   'Refresher owed after the head crash', NULL),
  ('cccccccc-0000-0000-0000-000000000002', 'laser',
   '2025-05-01T18:00:00Z', NULL, NULL, NULL, NULL);

-- Two waivers for Wren, because /me/waiver answers with the most recent one
-- and one row cannot show that it picked. Ida has none, which is the 404 the
-- members portal reads as an empty section.
INSERT INTO waivers (member_id, signed_at, expires_at, storage, reference, note)
VALUES
  ('cccccccc-0000-0000-0000-000000000001', '2024-01-20T17:00:00Z',
   '2025-01-20T17:00:00Z', 'paper-file', 'drawer 2, 2024', 'The old one'),
  ('cccccccc-0000-0000-0000-000000000001', '2025-01-18T17:00:00Z',
   NULL, 'google-form', 'response-8814', NULL);
