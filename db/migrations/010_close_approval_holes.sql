-- One admin could satisfy the two approver rule by themselves.
--
-- The UPDATE policy on approvals had no WITH CHECK, and freeze_approval_proposal
-- did not freeze decided_by. So one admin could propose, write somebody else's
-- id into decided_by, approve, and grant. The second admin never touched it.
--
-- Three separate holes closed here, all reachable by a single admin.

BEGIN;

-- 1. You may only record yourself as the decider, and only on a row you can see.
DROP POLICY admin_decides ON approvals;
CREATE POLICY admin_decides ON approvals FOR UPDATE
  USING (is_admin(current_member_id()))
  WITH CHECK (is_admin(current_member_id())
              AND (decided_by IS NULL OR decided_by = current_member_id()));

-- 2. Who decided, and when, is not editable after the fact.
CREATE OR REPLACE FUNCTION freeze_approval_proposal() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.kind             IS DISTINCT FROM OLD.kind
  OR NEW.target_member_id IS DISTINCT FROM OLD.target_member_id
  OR NEW.role_id          IS DISTINCT FROM OLD.role_id
  OR NEW.proposed_by      IS DISTINCT FROM OLD.proposed_by
  OR NEW.proposed_at      IS DISTINCT FROM OLD.proposed_at THEN
    RAISE EXCEPTION
      'What an approval proposes cannot be changed after it is created. '
      'Withdraw it and propose again.';
  END IF;
  IF OLD.decided_by IS NOT NULL
     AND (NEW.decided_by IS DISTINCT FROM OLD.decided_by
          OR NEW.decided_at IS DISTINCT FROM OLD.decided_at) THEN
    RAISE EXCEPTION 'Who decided an approval, and when, is a record.';
  END IF;
  IF OLD.status IN ('approved','rejected')
     AND NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION 'Approval % is already %. A decision is final.',
      OLD.id, OLD.status;
  END IF;
  -- A decision is always by the person making it, whatever the client sent.
  IF OLD.decided_by IS NULL AND NEW.decided_by IS NOT NULL
     AND current_user = 'oro_api' THEN
    IF NEW.decided_by IS DISTINCT FROM current_member_id() THEN
      RAISE EXCEPTION 'You can only record yourself as the approver.';
    END IF;
    NEW.decided_at := coalesce(NEW.decided_at, now());
  END IF;
  RETURN NEW;
END $$;

-- 3. A decided approval must carry a decision time, so expiry is not a no-op.
ALTER TABLE approvals ADD CONSTRAINT decided_rows_have_a_time
  CHECK ((status IN ('pending','withdrawn')) = (decided_at IS NULL));

-- 4. And the proposer is always the person proposing.
CREATE FUNCTION enforce_proposer_is_caller() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF current_user = 'oro_api'
     AND NEW.proposed_by IS DISTINCT FROM current_member_id() THEN
    RAISE EXCEPTION 'You can only record yourself as the proposer.';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER proposer_is_caller
  BEFORE INSERT ON approvals
  FOR EACH ROW EXECUTE FUNCTION enforce_proposer_is_caller();

-- 5. The bootstrap escape reopened on demand: revoke down to one admin, then
-- grant freely. It now only applies while the lab has never had two, which is
-- a fact about history rather than a fact about right now.
CREATE TABLE two_approver_armed (
  armed_at timestamptz NOT NULL DEFAULT now(),
  one_row  boolean PRIMARY KEY DEFAULT true CHECK (one_row)
);
COMMENT ON TABLE two_approver_armed IS
  'Records the first moment two admins existed. Once present, the bootstrap '
  'escape in the role grant trigger is closed permanently, so revoking admins '
  'to get back under the threshold does not reopen it.';

CREATE OR REPLACE FUNCTION two_approver_rule_can_bind() RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM two_approver_armed) THEN RETURN true; END IF;
  RETURN admin_count() >= 2;
END $$;

CREATE FUNCTION arm_two_approver_rule() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  IF admin_count() >= 2 AND NOT EXISTS (SELECT 1 FROM two_approver_armed) THEN
    INSERT INTO two_approver_armed DEFAULT VALUES;
  END IF;
  RETURN NULL;
END $$;

CREATE TRIGGER arm_the_rule
  AFTER INSERT OR UPDATE ON member_roles
  FOR EACH STATEMENT EXECUTE FUNCTION arm_two_approver_rule();

COMMIT;
