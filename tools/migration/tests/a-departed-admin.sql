-- Hand authored for tools/migration/tests/run.sh. Not part of the fixture in
-- tools/migration/fixtures/, which a replica of the legacy application wrote
-- through its own models. Nothing here came from that replica.
--
-- The legacy system never cleared the admin boolean when somebody left. It
-- recorded the departure in exit_reason and left the flag alone, so the two
-- facts sit in one row disagreeing. Carrying the flag would hand a live admin
-- role to somebody who walked out. This puts one such row back so the preflight
-- has exactly one thing to refuse.
UPDATE legacy.users SET exit_reason = 'moved away' WHERE id = 1;
