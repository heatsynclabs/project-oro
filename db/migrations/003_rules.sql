-- The rules that must hold no matter what writes to the database.
--
-- Two small predicates and two small triggers, each with one job. The earlier
-- draft put all of it in one forty line trigger, which nobody would read at
-- 2am.

BEGIN;

-- SECURITY DEFINER, and it matters. member_roles has row level security
-- forced, so without it these read only what the caller may see: a member
-- asking whether somebody else is an admin gets false, and admin_count() reads
-- zero for everyone. Every policy that calls is_admin() would then be deciding
-- on an answer that depends on who is asking, which is exactly backwards.
CREATE FUNCTION is_admin(who uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT EXISTS (
    SELECT 1 FROM member_roles r JOIN roles ro ON ro.id = r.role_id
     WHERE r.member_id = who AND ro.grants_roles AND r.revoked_at IS NULL)
$$;

CREATE FUNCTION admin_count() RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT count(*)::integer FROM member_roles r JOIN roles ro ON ro.id = r.role_id
   WHERE ro.grants_roles AND r.revoked_at IS NULL
$$;

-- A two approver rule cannot bind until two approvers exist. Below that there
-- is no set of people who could satisfy it, so enforcing it would make the
-- system permanently unadministrable: unbootstrappable when new, and stuck at
-- one admin forever after. The escape closes for good once a second admin
-- exists, and it grants no power that is not already held, because a lone
-- admin already controls everything the rule protects.
CREATE FUNCTION two_approver_rule_can_bind() RETURNS boolean
LANGUAGE sql STABLE AS $$ SELECT admin_count() >= 2 $$;

-- An approval is only valid if two admins made it. Checked here, at decision
-- time, rather than at grant time: a proposer who later loses the admin role
-- does not retroactively invalidate a decision a second admin already made.
CREATE FUNCTION enforce_approval_is_by_two_admins() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status <> 'approved' THEN RETURN NEW; END IF;
  IF NOT two_approver_rule_can_bind() THEN RETURN NEW; END IF;
  IF NOT is_admin(NEW.proposed_by) THEN
    RAISE EXCEPTION 'The proposer of this approval is not an admin.';
  END IF;
  IF NOT is_admin(NEW.decided_by) THEN
    RAISE EXCEPTION 'The approver of this approval is not an admin.';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER approval_is_by_two_admins
  BEFORE INSERT OR UPDATE ON approvals
  FOR EACH ROW EXECUTE FUNCTION enforce_approval_is_by_two_admins();

-- A protected role needs a usable approval. The composite foreign key already
-- guarantees the approval names this exact member and role, so this only has
-- to check that the approval is usable.
CREATE FUNCTION enforce_role_grant_rules() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE a approvals%ROWTYPE;
BEGIN
  IF NOT (SELECT grants_roles FROM roles WHERE id = NEW.role_id) THEN
    RETURN NEW;                                 -- ordinary roles, single actor
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.revoked_at IS NOT NULL AND OLD.revoked_at IS NULL THEN
    RETURN NEW;                                 -- revoking is not granting
  END IF;
  IF NOT two_approver_rule_can_bind() THEN
    RAISE WARNING 'Bootstrap grant of % to %: only % admin(s) exist, so the '
                  'two approver rule cannot yet be satisfied. Recorded.',
                  NEW.role_id, NEW.member_id, admin_count();
    RETURN NEW;
  END IF;

  IF NEW.approval_id IS NULL THEN
    RAISE EXCEPTION 'Granting % needs an approval from a second admin.', NEW.role_id;
  END IF;
  SELECT * INTO a FROM approvals WHERE id = NEW.approval_id;
  IF a.status <> 'approved' THEN
    RAISE EXCEPTION 'Approval % is %, not approved.', a.id, a.status;
  END IF;
  IF a.kind <> 'grant_role' THEN
    RAISE EXCEPTION 'Approval % is a %, not a role grant.', a.id, a.kind;
  END IF;
  IF a.decided_at > a.expires_at THEN
    RAISE EXCEPTION 'Approval % had expired when it was decided.', a.id;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER role_grant_rules
  BEFORE INSERT OR UPDATE ON member_roles
  FOR EACH ROW EXECUTE FUNCTION enforce_role_grant_rules();


COMMIT;
