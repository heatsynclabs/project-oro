-- Where each signed waiver is kept. One row per legacy member who signed one.
--
-- This is not legacy data and it is not a table this system keeps. The legacy
-- users table records a waiver date and nothing else: no storage, no reference,
-- no document. The new waivers table needs a storage, because
-- docs/plan/data-model.md section 1.5 makes a waiver a pointer to a document
-- held somewhere else and forbids copying the document or anything on it in.
--
-- So this table is the shape of an answer a person gives. Somebody who knows
-- where the lab keeps its signed waivers fills it in on the staging copy before
-- the import runs, and 010_preflight.sql refuses to start while any member who
-- signed is missing from it. fixtures/decisions.sql fills it in for the
-- fixture, as one plausible answer and not a recommendation.
--
-- Applied outside the migration transaction, after the legacy schema it points
-- at and before the decisions that fill it in, because the answers have to
-- exist before anything can read them.

-- The foreign key is this file's own, not the legacy schema's. That schema has
-- no foreign keys anywhere, which is why a card can point at a member who was
-- deleted. A typed user_id that matches nobody would make a waiver silently not
-- arrive, so it is refused here instead.
CREATE TABLE IF NOT EXISTS legacy.waiver_documents (
  user_id   integer PRIMARY KEY REFERENCES legacy.users(id),
  storage   text NOT NULL,
  reference text
);

COMMENT ON TABLE legacy.waiver_documents IS
  'Answers, not legacy data. Where each signed waiver is kept, filled in by a '
  'person on the staging copy before the import runs. The legacy system '
  'recorded only the date a waiver was signed.';
COMMENT ON COLUMN legacy.waiver_documents.user_id IS
  'The legacy users.id whose waiver this is.';
COMMENT ON COLUMN legacy.waiver_documents.storage IS
  'Which system holds the document. For example google-form, paper-file.';
-- Rule 13 and data-model.md section 1.5: this system records that a waiver
-- exists and where, never anything on it. A reference filed under a member's
-- surname would carry a name into a table built not to hold one, so the column
-- comment says so where the person filling it in will read it.
COMMENT ON COLUMN legacy.waiver_documents.reference IS
  'How to find it there: a form response id, a file id, a box label. It must '
  'not name the member. This system holds no personal information about a '
  'waiver, and a reference is the one free text field where somebody could put '
  'some without meaning to.';
