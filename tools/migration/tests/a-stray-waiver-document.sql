-- Hand authored for tools/migration/tests/run.sh. Not part of the fixture in
-- tools/migration/fixtures/, which a replica of the legacy application wrote
-- through its own models. Nothing here came from that replica.
--
-- A row saying where somebody's signed waiver is kept, for a member who never
-- signed one. A person writes that table by hand on the staging copy, so the
-- likeliest way this exists is a user_id typed wrong, which also means the
-- member it was meant for has no document at all.
INSERT INTO legacy.waiver_documents (user_id, storage, reference)
VALUES (5, 'google-form', 'sheet row typed wrong');
