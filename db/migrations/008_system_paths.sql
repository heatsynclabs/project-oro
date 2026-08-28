-- The three things that cannot run as "a member acting on their own rows".

BEGIN;

-- 1. Signing in for the first time.
--
-- A person authenticates with the identity provider and arrives with a subject
-- and no member row, or with a member row somebody created for them years ago.
-- Neither case can run under a member policy, because there is no current
-- member yet. This is the single, auditable entry point.
--
-- Matching an existing row by email is what makes the waiver the front door and
-- what handles the paying members who never signed up: an admin created them,
-- and their first sign in claims that row instead of making a duplicate.
CREATE FUNCTION link_or_create_member(p_subject text, p_email citext, p_name text)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE existing members%ROWTYPE;
        new_id  uuid;
BEGIN
  IF p_subject IS NULL OR p_subject = '' THEN
    RAISE EXCEPTION 'An identity subject is required.';
  END IF;

  SELECT * INTO existing FROM members WHERE identity_subject = p_subject;
  IF FOUND THEN RETURN existing.id; END IF;

  SELECT * INTO existing FROM members
   WHERE email = p_email AND identity_subject IS NULL AND deleted_at IS NULL;
  IF FOUND THEN
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

REVOKE ALL ON FUNCTION link_or_create_member(text, citext, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION link_or_create_member(text, citext, text) TO oro_api;

COMMENT ON FUNCTION link_or_create_member(text, citext, text) IS
  'First sign in. Claims an existing member row by email when it has no '
  'identity yet, otherwise creates one. The only path that writes a member '
  'without an admin, and it grants nothing: no roles, no tier, standing '
  'unknown.';

-- 2. The door service recording what happened at the door.
--
-- Not a member action. It runs with no member identity and must not be
-- filtered by member policies.
GRANT INSERT ON door_events TO door_reader;
GRANT USAGE, SELECT ON SEQUENCE door_events_id_seq TO door_reader;

CREATE FUNCTION door.record_event(
  p_occurred_at timestamptz, p_source text, p_event_key text,
  p_dedupe_key text, p_card_id uuid DEFAULT NULL, p_member_id uuid DEFAULT NULL,
  p_door text DEFAULT NULL, p_raw_data integer DEFAULT NULL,
  p_detail jsonb DEFAULT '{}')
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE new_id bigint;
BEGIN
  INSERT INTO door_events (occurred_at, source, event_key, dedupe_key,
                           card_id, member_id, door, raw_data, detail)
    VALUES (p_occurred_at, p_source, p_event_key, p_dedupe_key,
            p_card_id, p_member_id, p_door, p_raw_data, p_detail)
    ON CONFLICT (dedupe_key) DO NOTHING
    RETURNING id INTO new_id;
  RETURN new_id;   -- null when the event was already recorded
END $$;
ALTER FUNCTION door.record_event(timestamptz,text,text,text,uuid,uuid,text,integer,jsonb)
  OWNER TO door_reader;
GRANT EXECUTE ON FUNCTION
  door.record_event(timestamptz,text,text,text,uuid,uuid,text,integer,jsonb) TO oro_api;

COMMENT ON FUNCTION door.record_event(timestamptz,text,text,text,uuid,uuid,text,integer,jsonb) IS
  'Append a door event. Returns null when the dedupe key was already present, '
  'so a retried flush after a network partition does not double record '
  'somebody entering the building.';

-- 3. Card access eligibility, which is what actually reads the bylaws numbers.
--
-- Until this existed, nothing in the database consumed governance_parameters
-- and the claim that those numbers are enforced rather than decorative was
-- false.
CREATE FUNCTION card_eligibility(p_member uuid)
RETURNS TABLE (eligible boolean, eligible_on date, reason text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  months   integer := (SELECT (value::text)::integer FROM governance_parameters
                        WHERE key = 'card_access.tenure_months');
  min_tier text    := (SELECT trim(both '"' from value::text) FROM governance_parameters
                        WHERE key = 'card_access.min_tier');
  m        members%ROWTYPE;
  ok_tier  boolean;
  ready_on date;
BEGIN
  SELECT * INTO m FROM members WHERE id = p_member;
  IF NOT FOUND THEN
    RETURN QUERY SELECT false, NULL::date, 'No such member.'; RETURN;
  END IF;

  SELECT t.card_eligible INTO ok_tier FROM tiers t WHERE t.id = m.tier_id;
  ready_on := (coalesce(m.joined_on, m.created_at::date) + (months || ' months')::interval)::date;

  IF coalesce(ok_tier, false) IS NOT TRUE THEN
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

COMMENT ON FUNCTION card_eligibility(uuid) IS
  'Reads the tenure and tier rules from governance_parameters, so amending the '
  'bylaws is an admin editing a row rather than a developer writing a migration.';

COMMIT;
