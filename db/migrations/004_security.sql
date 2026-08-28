-- Row level security, the application role, and the door path.

BEGIN;

-- SECURITY DEFINER for two reasons: members has RLS forced, so without it the
-- lookup recurses into the policy that is calling it; and a missing setting
-- must raise rather than return NULL, because NULL makes every policy evaluate
-- false and the caller sees an empty result, which reads as "this member has
-- no cards". A wrong answer delivered confidently is worse than an error.
CREATE FUNCTION current_member_id() RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
DECLARE subject text := current_setting('oro.identity_subject', true);
        member  uuid;
BEGIN
  IF subject IS NULL OR subject = '' THEN
    RAISE EXCEPTION 'No identity set on this transaction'
      USING HINT = 'The service must SET LOCAL oro.identity_subject before querying. '
                   'SET LOCAL, never SET: a plain SET persists for the pooled '
                   'connection and leaks one member''s identity to the next request.';
  END IF;
  SELECT id INTO member FROM members WHERE identity_subject = subject;
  RETURN member;
END $$;

ALTER TABLE members               ENABLE ROW LEVEL SECURITY;
ALTER TABLE members               FORCE  ROW LEVEL SECURITY;
ALTER TABLE cards                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE cards                 FORCE  ROW LEVEL SECURITY;
ALTER TABLE door_events           ENABLE ROW LEVEL SECURITY;
ALTER TABLE door_events           FORCE  ROW LEVEL SECURITY;
ALTER TABLE waivers               ENABLE ROW LEVEL SECURITY;
ALTER TABLE waivers               FORCE  ROW LEVEL SECURITY;
ALTER TABLE member_certifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE member_certifications FORCE  ROW LEVEL SECURITY;

CREATE POLICY member_reads_self ON members FOR SELECT
  USING (id = current_member_id());
CREATE POLICY member_updates_self ON members FOR UPDATE
  USING (id = current_member_id());
CREATE POLICY admin_reads_all ON members FOR SELECT
  USING (is_admin(current_member_id()));

CREATE POLICY member_reads_own_cards ON cards FOR SELECT
  USING (member_id = current_member_id());
CREATE POLICY admin_reads_all_cards ON cards FOR SELECT
  USING (is_admin(current_member_id()));

-- Door events are access records for a physical building. Readable by the
-- member they concern and by admins, and nobody else. This narrows current
-- behaviour, where any oriented member can read everyone's, so it is a board
-- decision rather than a schema detail.
CREATE POLICY member_reads_own_door_events ON door_events FOR SELECT
  USING (member_id = current_member_id());
CREATE POLICY admin_reads_all_door_events ON door_events FOR SELECT
  USING (is_admin(current_member_id()));

CREATE POLICY member_reads_own_waiver ON waivers FOR SELECT
  USING (member_id = current_member_id());
CREATE POLICY admin_reads_all_waivers ON waivers FOR SELECT
  USING (is_admin(current_member_id()));

CREATE POLICY member_reads_own_certs ON member_certifications FOR SELECT
  USING (member_id = current_member_id());
CREATE POLICY admin_reads_all_certs ON member_certifications FOR SELECT
  USING (is_admin(current_member_id()));

-- The directory. Row visibility is a policy; column visibility cannot be,
-- because row level security is row level. So the directory endpoints read this
-- view and never the base table, and the view is what honours email_visible and
-- phone_visible.
CREATE POLICY member_reads_directory ON members FOR SELECT
  USING (listed_in_directory AND deleted_at IS NULL);

CREATE VIEW member_directory AS
SELECT m.id,
       coalesce(m.display_name, m.name) AS name,
       m.pronouns,
       CASE WHEN m.email_visible THEN m.email END AS email,
       CASE WHEN m.phone_visible THEN m.phone END AS phone,
       m.current_skills,
       m.desired_skills,
       m.joined_on
  FROM members m
 WHERE m.listed_in_directory AND m.deleted_at IS NULL;

COMMENT ON VIEW member_directory IS
  'The only thing the directory endpoints read. Hides email and phone unless the '
  'member chose to show them. A policy cannot do this: RLS filters rows, not '
  'columns.';

-- The application connects as this. Not a superuser, so the policies apply to
-- it too and there is no bypass to take.
CREATE ROLE oro_api NOLOGIN;
GRANT USAGE ON SCHEMA public TO oro_api;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO oro_api;
GRANT SELECT ON member_directory TO oro_api;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO oro_api;
-- Append only means append only.
REVOKE UPDATE, DELETE ON door_events FROM oro_api;
-- The rule's scope is data, so changing it is a migration, not a request.
REVOKE INSERT, UPDATE ON roles FROM oro_api;

-- FORCE applies to table owners, so a SECURITY DEFINER function owned by an
-- ordinary role is still filtered by member policies. Without this the door
-- would read an empty card table, the reconciler's shrink guard would refuse
-- to apply it, and sync would wedge permanently while alerting forever.
-- BYPASSRLS on a NOLOGIN role owning exactly one function is the narrowest
-- exemption that works.
CREATE ROLE door_reader NOLOGIN BYPASSRLS;
GRANT SELECT ON cards TO door_reader;

CREATE SCHEMA door;
CREATE FUNCTION door.active_card_table()
RETURNS TABLE (controller_slot integer, tag_number text, permission_mask integer)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
  SELECT c.controller_slot, c.tag_number, c.permission_mask
    FROM cards c
   WHERE c.active AND c.controller_slot IS NOT NULL
   ORDER BY c.controller_slot
$$;
ALTER FUNCTION door.active_card_table() OWNER TO door_reader;
GRANT USAGE ON SCHEMA door TO oro_api;
GRANT EXECUTE ON FUNCTION door.active_card_table() TO oro_api;

COMMIT;
