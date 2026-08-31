-- A sign in whose member record was removed had nowhere to go.
--
-- 012 taught current_member_id and link_or_create_member to read
-- deleted_at IS NULL, which was right and left one gap between them. A member
-- whose record is soft deleted resolves to no member, so every read answers
-- no-member-record and sends them to POST /me. That operation calls this
-- function, the subject branch skips the removed row, and the INSERT at the
-- bottom hits members_identity_subject_key, which is UNIQUE over removed rows
-- too. The service turned that into a 500. The member sat in a loop: the read
-- told them to write a record, and the write broke, forever.
--
-- Found by the audit of 2026-08-31, reproduced against a real stack.

BEGIN;

CREATE OR REPLACE FUNCTION link_or_create_member(p_subject text, p_email citext, p_name text)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE existing members%ROWTYPE;
        new_id  uuid;
BEGIN
  IF p_subject IS NULL OR p_subject = '' THEN
    RAISE EXCEPTION 'An identity subject is required.';
  END IF;

  SELECT * INTO existing FROM members
   WHERE identity_subject = p_subject AND deleted_at IS NULL;
  IF FOUND THEN RETURN existing.id; END IF;

  -- Before the INSERT rather than after it, so the answer is a sentence
  -- somebody can act on instead of a unique constraint. Removing a record is
  -- reversible by design, per the deleted_at comment in 001_schema.sql, so the
  -- way out is an admin restoring it and not a second record beside it.
  IF EXISTS (SELECT 1 FROM members WHERE identity_subject = p_subject) THEN
    RAISE EXCEPTION
      'This sign in belongs to a member record that was removed. An admin '
      'restores it.';
  END IF;

  SELECT * INTO existing FROM members
   WHERE email = p_email AND identity_subject IS NULL AND deleted_at IS NULL;
  IF FOUND THEN
    -- A row that already holds a role is not claimable by whoever turns up
    -- with that address. An admin links those by hand.
    IF EXISTS (SELECT 1 FROM member_roles r
                WHERE r.member_id = existing.id AND r.revoked_at IS NULL) THEN
      RAISE EXCEPTION
        'That member already holds a role and must be linked by an admin.';
    END IF;
    UPDATE members SET identity_subject = p_subject WHERE id = existing.id;
    RETURN existing.id;
  END IF;

  IF EXISTS (SELECT 1 FROM members WHERE email = p_email) THEN
    RAISE EXCEPTION 'That email already belongs to another account.';
  END IF;

  INSERT INTO members (identity_subject, email, name)
    VALUES (p_subject, p_email, coalesce(nullif(p_name,''), p_email::text))
    RETURNING id INTO new_id;
  RETURN new_id;
END $$;

COMMENT ON FUNCTION link_or_create_member(text, citext, text) IS
  'First sign in. Claims an existing member row by email when it has no '
  'identity yet, otherwise creates one. The only path that writes a member '
  'without an admin, and it grants nothing: no roles, no tier, standing '
  'unknown. A subject whose record was removed is refused rather than given a '
  'second record, because removal is reversible and duplication is not.';

COMMIT;
