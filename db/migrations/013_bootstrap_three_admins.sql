-- The bootstrap escape seats three admins, not two.
--
-- docs/plan/people-and-custody.md section 1 requires two holders for every role
-- and names a single holder as the failure this project is designed against.
-- Two admins is the smallest number the two approver rule can bind at, so a lab
-- that stops at two has no spare: lose one and nothing can be approved by
-- anybody until an operator intervenes at the database. Three is the smallest
-- number that survives losing one.
--
-- The escape stays a quota rather than becoming a higher threshold, and the
-- difference is the whole reason this file is not a one word edit. A threshold
-- of three live admins would hold the escape open for as long as the lab had
-- only two, so two people who could satisfy the rule would never have to. A
-- quota is spent by use instead. Three admin grants carry no approval, ever,
-- and the fourth needs one.
--
-- Nothing new is recorded to count them. A bootstrap grant is already a row in
-- member_roles with a null approval_id, and no application role holds DELETE on
-- that table, so the count only goes up.

BEGIN;

-- One number, one place. Its source is people-and-custody.md section 1: two
-- holders per role, and one is the failure being designed against.
CREATE FUNCTION bootstrap_admin_quota() RETURNS integer
LANGUAGE sql IMMUTABLE AS $$ SELECT 3 $$;

COMMENT ON FUNCTION bootstrap_admin_quota() IS
  'How many grants of a role that can itself grant roles may ever be made with '
  'no approval behind them. Three, so the lab can seat two admins and a spare '
  'before the two approver rule binds.';

-- SECURITY DEFINER for the reason in HANDOFF.md section 7. member_roles has row
-- level security forced, so without it this counts only the rows the caller
-- happens to be allowed to see, and every decision downstream depends on who is
-- asking rather than on what is true.
CREATE FUNCTION bootstrap_admin_grants_used() RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT count(*)::integer
    FROM member_roles r JOIN roles ro ON ro.id = r.role_id
   WHERE ro.grants_roles AND r.approval_id IS NULL
$$;

COMMENT ON FUNCTION bootstrap_admin_grants_used() IS
  'Admin grants made with no approval behind them, over the whole history of '
  'the database. A revoked row still counts, because removing somebody must '
  'never hand the escape back.';

CREATE FUNCTION bootstrap_is_spent() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT admin_count() >= bootstrap_admin_quota()
      OR bootstrap_admin_grants_used() >= bootstrap_admin_quota()
$$;

COMMENT ON FUNCTION bootstrap_is_spent() IS
  'True once the lab holds three live admins, or has used three unapproved '
  'admin grants. The used count is what bounds the escape. The live count is '
  'what closes it early if three admins arrive by any other route.';

CREATE OR REPLACE FUNCTION two_approver_rule_can_bind() RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM two_approver_armed) THEN RETURN true; END IF;
  RETURN bootstrap_is_spent();
END $$;

CREATE OR REPLACE FUNCTION arm_two_approver_rule() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  IF bootstrap_is_spent() AND NOT EXISTS (SELECT 1 FROM two_approver_armed) THEN
    INSERT INTO two_approver_armed DEFAULT VALUES;
  END IF;
  RETURN NULL;
END $$;

COMMENT ON TABLE two_approver_armed IS
  'Records the first moment the bootstrap ran out, which is three live admins '
  'or three unapproved admin grants, whichever came first. Once this row '
  'exists the escape in the role grant trigger is closed permanently, so '
  'revoking admins to get back under the threshold does not reopen it.';

-- Only the warning text changes. It used to name the live admin count, which
-- stops being the thing that decides the escape once a quota decides it, and a
-- message that names the wrong reason is how the next person mis-reads the rule.
CREATE OR REPLACE FUNCTION enforce_role_grant_rules() RETURNS trigger
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
    RAISE WARNING 'Bootstrap grant of % to %: seat % of %, with no approval '
                  'because a two approver rule cannot bind until approvers '
                  'exist. Recorded.',
                  NEW.role_id, NEW.member_id,
                  bootstrap_admin_grants_used() + 1, bootstrap_admin_quota();
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

COMMIT;
