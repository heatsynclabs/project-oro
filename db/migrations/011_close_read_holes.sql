-- Four ways to read things you should not.

BEGIN;

-- 1. NULL is not false. A subject matching no member made current_member_id()
-- return NULL, so the guard evaluated to NULL, IF NOT NULL was skipped, and the
-- function returned anybody's waiver status. Every guard of this shape needs
-- coalesce, and the caller must be a real member.
CREATE OR REPLACE FUNCTION waiver_status(p_member uuid)
RETURNS TABLE (member_id uuid, latest_signed_at timestamptz, has_valid_waiver boolean)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
DECLARE caller uuid;
BEGIN
  -- No carve out for an operator, deliberately. Inside a SECURITY DEFINER
  -- function current_user is the owner rather than the caller's role, so a
  -- role based exemption would always fire and the gate would never apply at
  -- all. An operator does not need this function: they own the table and can
  -- read it directly. So this fails closed and always requires an identity.
  caller := current_member_id();
  IF caller IS NULL THEN
    RAISE EXCEPTION 'No member matches the identity on this transaction.';
  END IF;
  IF NOT coalesce(
        is_admin(caller)
        OR EXISTS (SELECT 1 FROM member_roles r
                    WHERE r.member_id = caller AND r.revoked_at IS NULL
                      AND r.role_id IN ('host','operations','board'))
        OR EXISTS (SELECT 1 FROM certification_instructors i
                    WHERE i.member_id = caller)
        OR caller = p_member, false) THEN
    RAISE EXCEPTION 'Checking somebody else''s waiver needs a hosting or '
                    'instructing role.';
  END IF;

  RETURN QUERY
    SELECT w.member_id, max(w.signed_at),
           bool_or(w.expires_at IS NULL OR w.expires_at > now())
      FROM waivers w WHERE w.member_id = p_member GROUP BY w.member_id;
END $$;

-- 2. member_reads_directory was a policy on the base table, so any member could
-- SELECT * FROM members and read every listed member's email, phone, postal
-- code, emergency contact, standing and paid_through directly, whatever they
-- had chosen to make visible. Row level security cannot hide columns, so the
-- directory must be reached only through the view.
DROP POLICY member_reads_directory ON members;

-- The view runs as its owner so it can read a base table that deliberately has
-- no member to member policy. That means it must gate itself, or it hands the
-- directory to a caller with no identity, which is the leak this replaced.
-- current_member_id() raises in that case, so calling it is the guard.
CREATE OR REPLACE VIEW member_directory AS
SELECT m.id,
       coalesce(m.display_name, m.name) AS name,
       m.pronouns,
       CASE WHEN m.email_visible THEN m.email END AS email,
       CASE WHEN m.phone_visible THEN m.phone END AS phone,
       m.current_skills,
       m.desired_skills,
       m.joined_on
  FROM members m
 WHERE m.listed_in_directory
   AND m.deleted_at IS NULL
   AND current_member_id() IS NOT NULL;

ALTER VIEW member_directory SET (security_invoker = false);
GRANT SELECT ON member_directory TO oro_api;

COMMENT ON VIEW member_directory IS
  'The only route to the directory. It runs as its owner deliberately, because '
  'the base table deliberately has no policy letting one member read another. '
  'Its own WHERE and CASE expressions are the filter: listed members only, and '
  'contact details only where the member chose to show them.';

-- 3. door.active_card_table() was granted to the application role, so any
-- member could call it and read every active RFID tag number in the building.
-- The door service has its own credentials; the members API has no business
-- reading the card table.
REVOKE EXECUTE ON FUNCTION door.active_card_table() FROM oro_api;
REVOKE USAGE ON SCHEMA door FROM oro_api;

-- 4. door.record_event() could never have worked. door_reader had INSERT but
-- not SELECT on door_events, so both RETURNING and ON CONFLICT raised
-- permission denied on every call.
GRANT SELECT ON door_events TO door_reader;

COMMIT;
