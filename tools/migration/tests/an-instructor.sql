-- Hand authored for tools/migration/tests/run.sh. Not part of the fixture in
-- tools/migration/fixtures/, which a replica of the legacy application wrote
-- through its own models. Nothing here came from that replica.
--
-- Puts the legacy instructor flag back after fixtures/decisions.sql answered
-- it, so the preflight is left with exactly one thing to refuse and the refusal
-- can only be about that one thing.
UPDATE legacy.users SET instructor = true WHERE id = 2;
