-- Hand authored for tools/migration/tests/run.sh. Not part of the fixture in
-- tools/migration/fixtures/, which a replica of the legacy application wrote
-- through its own models. Nothing here came from that replica.
--
-- Takes back the answer to where a signed waiver is kept, leaving a member with
-- a waiver date and nowhere to point at. waivers.storage is NOT NULL, so this
-- has to be refused rather than carried with a blank.
DELETE FROM legacy.waiver_documents;
