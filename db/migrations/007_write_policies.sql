-- Write policies, and row level security on the tables that had none.
--
-- An earlier pass built read isolation and stopped. Every protected table had
-- SELECT policies and no INSERT or UPDATE, so the API could read correctly and
-- write nothing. Worse, the tables that carry authority (member_roles,
-- governance_parameters) had no row level security at all while the
-- application role held INSERT and UPDATE on them, so any member could grant
-- themselves a role or edit the bylaws numbers.

BEGIN;

-- ---------------------------------------------------------------- approvals
-- These three were collateral damage when the card proposal tables were cut:
-- the removal took the approvals policies sitting between them, leaving the
-- table forced with no policy, which reads and writes as empty for everyone.

CREATE POLICY admin_reads_approvals ON approvals FOR SELECT
  USING (is_admin(current_member_id()));
CREATE POLICY admin_proposes ON approvals FOR INSERT
  WITH CHECK (is_admin(current_member_id()) AND proposed_by = current_member_id());
CREATE POLICY admin_decides ON approvals FOR UPDATE
  USING (is_admin(current_member_id()));

-- ------------------------------------------------------------ member writes

CREATE POLICY admin_writes_members ON members FOR INSERT
  WITH CHECK (is_admin(current_member_id()));
CREATE POLICY admin_updates_members ON members FOR UPDATE
  USING (is_admin(current_member_id()));

CREATE POLICY admin_writes_cards ON cards FOR INSERT
  WITH CHECK (is_admin(current_member_id()));
CREATE POLICY admin_updates_cards ON cards FOR UPDATE
  USING (is_admin(current_member_id()));

CREATE POLICY admin_writes_waivers ON waivers FOR INSERT
  WITH CHECK (is_admin(current_member_id()));
CREATE POLICY admin_updates_waivers ON waivers FOR UPDATE
  USING (is_admin(current_member_id()));

-- Only an instructor for that certification may grant it, or an admin. This
-- carries forward the rule the 2018 rewrite enforced and is the reason
-- instructors are per tool rather than a global flag.
CREATE POLICY instructor_grants_certification ON member_certifications FOR INSERT
  WITH CHECK (
    is_admin(current_member_id())
    OR EXISTS (SELECT 1 FROM certification_instructors i
                WHERE i.member_id = current_member_id()
                  AND i.certification_id = member_certifications.certification_id));
CREATE POLICY instructor_revokes_certification ON member_certifications FOR UPDATE
  USING (
    is_admin(current_member_id())
    OR EXISTS (SELECT 1 FROM certification_instructors i
                WHERE i.member_id = current_member_id()
                  AND i.certification_id = member_certifications.certification_id));

-- ------------------------------------- tables that carry authority, unguarded

ALTER TABLE member_roles                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE member_roles                 FORCE  ROW LEVEL SECURITY;
ALTER TABLE governance_parameters        ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance_parameters        FORCE  ROW LEVEL SECURITY;
ALTER TABLE governance_parameter_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance_parameter_history FORCE  ROW LEVEL SECURITY;
ALTER TABLE certifications               ENABLE ROW LEVEL SECURITY;
ALTER TABLE certifications               FORCE  ROW LEVEL SECURITY;
ALTER TABLE certification_instructors    ENABLE ROW LEVEL SECURITY;
ALTER TABLE certification_instructors    FORCE  ROW LEVEL SECURITY;
ALTER TABLE tiers                        ENABLE ROW LEVEL SECURITY;
ALTER TABLE tiers                        FORCE  ROW LEVEL SECURITY;

-- Everyone reads their own roles; admins read all. Only an admin writes, and
-- the approval trigger still governs which roles need a second admin.
CREATE POLICY member_reads_own_roles ON member_roles FOR SELECT
  USING (member_id = current_member_id() OR is_admin(current_member_id()));
CREATE POLICY admin_grants_roles ON member_roles FOR INSERT
  WITH CHECK (is_admin(current_member_id()));
CREATE POLICY admin_revokes_roles ON member_roles FOR UPDATE
  USING (is_admin(current_member_id()));

-- The bylaws numbers the lab runs on are visible to the lab and editable by
-- admins. History is append only for everyone.
CREATE POLICY anyone_reads_governance ON governance_parameters FOR SELECT USING (true);
CREATE POLICY admin_edits_governance ON governance_parameters FOR UPDATE
  USING (is_admin(current_member_id()));
CREATE POLICY admin_adds_governance ON governance_parameters FOR INSERT
  WITH CHECK (is_admin(current_member_id()));
CREATE POLICY anyone_reads_governance_history ON governance_parameter_history
  FOR SELECT USING (true);
CREATE POLICY anyone_appends_governance_history ON governance_parameter_history
  FOR INSERT WITH CHECK (true);

-- Reference data: everyone reads, admins write.
CREATE POLICY anyone_reads_certifications ON certifications FOR SELECT USING (true);
CREATE POLICY admin_writes_certifications ON certifications FOR INSERT
  WITH CHECK (is_admin(current_member_id()));
CREATE POLICY admin_updates_certifications ON certifications FOR UPDATE
  USING (is_admin(current_member_id()));

CREATE POLICY anyone_reads_instructors ON certification_instructors FOR SELECT USING (true);
CREATE POLICY admin_sets_instructors ON certification_instructors FOR INSERT
  WITH CHECK (is_admin(current_member_id()));

CREATE POLICY anyone_reads_tiers ON tiers FOR SELECT USING (true);
CREATE POLICY admin_writes_tiers ON tiers FOR INSERT
  WITH CHECK (is_admin(current_member_id()));
CREATE POLICY admin_updates_tiers ON tiers FOR UPDATE
  USING (is_admin(current_member_id()));

COMMIT;
