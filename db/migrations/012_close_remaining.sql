-- The rest of the fourth audit.

BEGIN;

-- 1. payments and schema_migrations had no row level security and the app role
-- held INSERT and UPDATE. A member could read and rewrite another member's
-- payment, and forge a migration record.
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments FORCE  ROW LEVEL SECURITY;
CREATE POLICY member_reads_own_payments ON payments FOR SELECT
  USING (member_id = current_member_id() OR is_admin(current_member_id()));
CREATE POLICY accountant_records_payments ON payments FOR INSERT
  WITH CHECK (is_admin(current_member_id())
              OR EXISTS (SELECT 1 FROM member_roles r
                          WHERE r.member_id = current_member_id()
                            AND r.role_id = 'accountant' AND r.revoked_at IS NULL));

-- Migrations are an operator action. The comment in 000 said the application
-- role has no access here, and that was not true.
REVOKE ALL ON schema_migrations FROM oro_api;

-- 2. An expired or revoked role, and a deleted member, still counted as an
-- admin. Nothing read expires_at or deleted_at.
CREATE OR REPLACE FUNCTION is_admin(who uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT EXISTS (
    SELECT 1 FROM member_roles r
      JOIN roles ro ON ro.id = r.role_id
      JOIN members m ON m.id = r.member_id
     WHERE r.member_id = who AND ro.grants_roles
       AND r.revoked_at IS NULL
       AND (r.expires_at IS NULL OR r.expires_at > now())
       AND m.deleted_at IS NULL)
$$;

CREATE OR REPLACE FUNCTION admin_count() RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT count(*)::integer FROM member_roles r
    JOIN roles ro ON ro.id = r.role_id
    JOIN members m ON m.id = r.member_id
   WHERE ro.grants_roles AND r.revoked_at IS NULL
     AND (r.expires_at IS NULL OR r.expires_at > now())
     AND m.deleted_at IS NULL
$$;

-- A deleted member cannot be anybody, so nothing they hold resolves.
CREATE OR REPLACE FUNCTION current_member_id() RETURNS uuid
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
  SELECT id INTO member FROM members
   WHERE identity_subject = subject AND deleted_at IS NULL;
  RETURN member;
END $$;

-- 3. granted_by and recorded_by were whatever the client sent, so one admin
-- could attribute their own action to somebody else.
CREATE FUNCTION stamp_actor() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF current_user <> 'oro_api' THEN RETURN NEW; END IF;
  IF TG_TABLE_NAME = 'member_roles' THEN
    NEW.granted_by := current_member_id();
  ELSIF TG_TABLE_NAME = 'waivers' THEN
    NEW.recorded_by := current_member_id();
  ELSIF TG_TABLE_NAME = 'member_certifications' THEN
    NEW.granted_by := current_member_id();
  ELSIF TG_TABLE_NAME = 'payments' THEN
    NEW.recorded_by := current_member_id();
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER stamp_actor BEFORE INSERT ON member_roles
  FOR EACH ROW EXECUTE FUNCTION stamp_actor();
CREATE TRIGGER stamp_actor BEFORE INSERT ON waivers
  FOR EACH ROW EXECUTE FUNCTION stamp_actor();
CREATE TRIGGER stamp_actor BEFORE INSERT ON member_certifications
  FOR EACH ROW EXECUTE FUNCTION stamp_actor();
CREATE TRIGGER stamp_actor BEFORE INSERT ON payments
  FOR EACH ROW EXECUTE FUNCTION stamp_actor();

-- 4. A card could be silently un-revoked or repointed at another member.
CREATE FUNCTION freeze_card_history() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.member_id IS DISTINCT FROM OLD.member_id THEN
    RAISE EXCEPTION 'A card belongs to who it was issued to. Revoke it and '
                    'issue another.';
  END IF;
  IF OLD.revoked_at IS NOT NULL
     AND (NEW.revoked_at IS NULL OR NEW.active) THEN
    RAISE EXCEPTION 'A revoked card cannot be brought back. Issue a new one.';
  END IF;
  IF NEW.controller_slot IS DISTINCT FROM OLD.controller_slot
     AND OLD.controller_slot IS NOT NULL THEN
    RAISE EXCEPTION 'A slot is an EEPROM address. Changing it remaps somebody '
                    'else''s door permission.';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER card_history_is_frozen BEFORE UPDATE ON cards
  FOR EACH ROW EXECUTE FUNCTION freeze_card_history();

-- 5. governance_parameter_history was forgeable and nothing ever wrote it.
REVOKE INSERT ON governance_parameter_history FROM oro_api;
DROP POLICY anyone_appends_governance_history ON governance_parameter_history;

CREATE FUNCTION record_governance_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  INSERT INTO governance_parameter_history (key, old_value, new_value, source, changed_by)
    VALUES (NEW.key, OLD.value, NEW.value, NEW.source,
            CASE WHEN current_user = 'oro_api' THEN current_member_id() END);
  RETURN NEW;
END $$;

CREATE TRIGGER governance_change_is_recorded AFTER UPDATE ON governance_parameters
  FOR EACH ROW WHEN (OLD.value IS DISTINCT FROM NEW.value)
  EXECUTE FUNCTION record_governance_change();

-- 6. An instructor could never revoke a certification, because no policy let
-- them see the row, so the UPDATE matched nothing and reported success.
CREATE POLICY instructor_reads_their_certifications ON member_certifications
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM certification_instructors i
             WHERE i.member_id = current_member_id()
               AND i.certification_id = member_certifications.certification_id));

-- 7. card_access.min_tier was decorative, and a missing parameter row made
-- everybody instantly eligible. Both now fail closed.
CREATE OR REPLACE FUNCTION card_eligibility(p_member uuid)
RETURNS TABLE (eligible boolean, eligible_on date, reason text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  months   integer := (SELECT (value::text)::integer FROM governance_parameters
                        WHERE key = 'card_access.tenure_months');
  min_tier text    := (SELECT trim(both '"' from value::text) FROM governance_parameters
                        WHERE key = 'card_access.min_tier');
  min_rank integer;
  m        members%ROWTYPE;
  m_rank   integer;
  ready_on date;
BEGIN
  IF months IS NULL OR min_tier IS NULL THEN
    RETURN QUERY SELECT false, NULL::date,
      'The card access rules are not configured, so nobody is eligible.';
    RETURN;
  END IF;

  SELECT * INTO m FROM members WHERE id = p_member AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RETURN QUERY SELECT false, NULL::date, 'No such member.'; RETURN;
  END IF;

  SELECT sort_order INTO min_rank FROM tiers WHERE id = min_tier;
  SELECT sort_order INTO m_rank   FROM tiers WHERE id = m.tier_id;
  ready_on := (coalesce(m.joined_on, m.created_at::date)
               + (months || ' months')::interval)::date;

  IF m_rank IS NULL OR min_rank IS NULL OR m_rank < min_rank THEN
    RETURN QUERY SELECT false, ready_on,
      format('Card access needs the %s tier or higher.', min_tier); RETURN;
  END IF;
  IF m.standing <> 'good' THEN
    RETURN QUERY SELECT false, ready_on,
      'Card access needs a member in good standing.'; RETURN;
  END IF;
  IF ready_on > current_date THEN
    RETURN QUERY SELECT false, ready_on,
      format('Card access needs %s months at this tier.', months); RETURN;
  END IF;
  RETURN QUERY SELECT true, ready_on,
    'Eligible. A cardholder nominates, and card members vote at Hack Your Hackerspace.';
END $$;

-- 8. link_or_create_member claimed any un-linked row by email, roles included,
-- so an admin's row could be taken over by whoever controlled that address.
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

COMMIT;
