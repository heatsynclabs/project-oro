-- The decisions a person makes on the staging copy before the migration runs.
--
-- 010_preflight.sql refuses the fixture beside this file until these are made,
-- which is the point of it: docs/plan/data-model.md section 6.3 says each of
-- these is a person's judgement rather than code.
--
-- What is written here is one plausible set of answers, so the suite can prove
-- the migration works once the answers exist. It is not a recommendation, and
-- the real answers belong to the people named in
-- docs/plan/people-and-custody.md section 5.

-- A card below slot 10 or above 199 cannot be addressed by the firmware, so it
-- is not a card the controller holds. Removed from the import rather than
-- renumbered, because renumbering is the one thing section 6.2 forbids.
DELETE FROM legacy.cards WHERE id < 10 OR id > 199;

-- A card owned by nobody. The answer taken here is that it is removed and
-- reported, because an active tag with no member is a security finding.
DELETE FROM legacy.cards c
 WHERE NOT EXISTS (SELECT 1 FROM legacy.users u WHERE u.id = c.user_id);

-- Permission 20 is a mask nobody here has decided the meaning of. Taken down to
-- 1, which is what the door service understands, so the member keeps access.
UPDATE legacy.cards SET card_permissions = 1 WHERE card_permissions IS DISTINCT FROM 1;

-- A member with no email address cannot sign in to the new system, because the
-- identity service is keyed on one. The row is kept, so the card and the
-- history survive, and the member is invited by an admin later.
UPDATE legacy.users
   SET email = format('legacy-%s@members.invalid', id)
 WHERE email IS NULL OR email = '';

-- The legacy instructor flag. An instructor here is an instructor on one tool,
-- so a global boolean has nothing to land on, and no certification exists yet
-- for it to land on even per tool. The answer taken here is that the flag is
-- dropped and the names go to whoever owns certifications, who grants each
-- person on each tool once the certifications exist. Seeding certifications
-- first and guessing which ones each instructor covers would be a longer
-- conversation than an import gets to start.
UPDATE legacy.users SET instructor = NULL WHERE instructor;

-- A payee, somebody paying on another member's behalf. Nothing in this schema
-- holds that. The answer taken here is that the name is dropped and whoever
-- handles payments records the arrangement again, because a name in a text
-- column is not an arrangement anybody can act on.
UPDATE legacy.users SET payee = NULL WHERE payee IS NOT NULL AND btrim(payee) <> '';

-- Where the signed waivers are kept. docs/plan/data-model.md section 1.5 says
-- the lab currently keeps them in a Google Form and its sheet, so that is the
-- answer taken here, with the sheet row as the reference. A real answer needs a
-- real reference per document and somebody has to go and look at the sheet.
INSERT INTO legacy.waiver_documents (user_id, storage, reference)
SELECT id, 'google-form', format('sheet row for legacy user %s', id)
  FROM legacy.users WHERE waiver IS NOT NULL;

-- A role flag on somebody who left. The legacy system recorded the departure in
-- exit_reason and never cleared the boolean, so the row says both things. The
-- answer taken here is that leaving ends the role: the flag is cleared and the
-- person arrives as an ordinary former member. If any of them is still an
-- admin, an admin grants it again afterwards, which puts a real approval behind
-- it instead of carrying one that never had any.
--
-- Nothing in the fixture beside this file matches, so this changes no row here.
-- It is written down because the production data will have rows that do, and
-- whoever adapts this file needs the shape of the answer rather than a surprise.
UPDATE legacy.users
   SET admin = false, accountant = false
 WHERE (admin OR accountant)
   AND exit_reason IS NOT NULL AND btrim(exit_reason) <> '';
