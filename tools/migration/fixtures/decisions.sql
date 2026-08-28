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
