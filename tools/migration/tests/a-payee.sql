-- Hand authored for tools/migration/tests/run.sh. Not part of the fixture in
-- tools/migration/fixtures/, which a replica of the legacy application wrote
-- through its own models. Nothing here came from that replica.
--
-- Puts a payee back after fixtures/decisions.sql answered it, so the preflight
-- is left with exactly one thing to refuse.
UPDATE legacy.users SET payee = 'Ada Invented' WHERE id = 3;
