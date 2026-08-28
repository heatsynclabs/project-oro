-- Views ran as their owner, which bypasses row level security entirely.
--
-- A view is not covered by the policies on the tables underneath it unless it
-- says so. Both views here were created without `security_invoker`, so they ran
-- with the owner's rights and returned rows to a caller with no identity set at
-- all. The base tables refused that caller correctly; the views handed the same
-- data over. member_directory leaked the directory and waiver_status leaked
-- everyone's waiver status, which is the thing it exists to gate.

BEGIN;

-- The directory now runs as whoever asked, so the member_reads_directory
-- policy applies and a caller with no identity is refused like anywhere else.
ALTER VIEW member_directory SET (security_invoker = true);

-- Waiver status cannot be a plain invoker view. Under the caller's rights a
-- host would see only their own row, which defeats the endpoint, and a policy
-- wide enough to fix that would also expose the storage reference and the note
-- on the base table. Row level security filters rows, not columns.
--
-- So it becomes a function that decides for itself who may ask, and returns
-- only the fact and the date.
DROP VIEW waiver_status;

CREATE FUNCTION waiver_status(p_member uuid)
RETURNS TABLE (member_id uuid, latest_signed_at timestamptz, has_valid_waiver boolean)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
DECLARE caller uuid := current_member_id();
BEGIN
  IF NOT (is_admin(caller) OR EXISTS (
            SELECT 1 FROM member_roles r
             WHERE r.member_id = caller AND r.revoked_at IS NULL
               AND r.role_id IN ('host','operations','board'))
          OR EXISTS (
            SELECT 1 FROM certification_instructors i WHERE i.member_id = caller)
          OR caller = p_member) THEN
    RAISE EXCEPTION 'Checking somebody else''s waiver needs a hosting or '
                    'instructing role.';
  END IF;

  RETURN QUERY
    SELECT w.member_id, max(w.signed_at),
           bool_or(w.expires_at IS NULL OR w.expires_at > now())
      FROM waivers w
     WHERE w.member_id = p_member
     GROUP BY w.member_id;
END $$;

REVOKE ALL ON FUNCTION waiver_status(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION waiver_status(uuid) TO oro_api;

COMMENT ON FUNCTION waiver_status(uuid) IS
  'Whether a member has a valid waiver, and when it was signed. Nothing else: '
  'not the storage, not the reference, not the note. Callable by an admin, by '
  'anybody holding a hosting role, by any instructor, and by the member about '
  'themselves. This is a function rather than a view because a view either '
  'bypasses row level security or is filtered to the caller''s own rows, and '
  'neither is what a host checking somebody in needs.';

COMMIT;
