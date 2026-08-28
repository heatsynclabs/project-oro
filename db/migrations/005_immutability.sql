-- Append only means append only, and a recorded decision stays recorded.
--
-- Granting UPDATE on every table and revoking it from one is the wrong default:
-- it leaves the audit trail editable by the application role. These are the
-- tables where history is the point.

BEGIN;

-- Pure audit. Rows go in and never change.
REVOKE UPDATE ON governance_parameter_history FROM oro_api;

-- Views. Write grants on them were meaningless.
REVOKE INSERT, UPDATE ON member_directory, waiver_status FROM oro_api;

-- An approval must stay updatable, because deciding one is an UPDATE. What must
-- not change is what was proposed and by whom, otherwise a single admin can
-- repoint an approved approval at a different member or role after the fact and
-- the composite foreign key will happily follow it.
CREATE FUNCTION freeze_approval_proposal() RETURNS trigger
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
  IF OLD.status IN ('approved','rejected')
     AND NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION 'Approval % is already %. A decision is final.',
      OLD.id, OLD.status;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER approval_proposal_is_frozen
  BEFORE UPDATE ON approvals
  FOR EACH ROW EXECUTE FUNCTION freeze_approval_proposal();

-- Same shape for a role grant: revoking is an UPDATE, but who was granted what,
-- by whom, and under which approval is history.
CREATE FUNCTION freeze_role_grant() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.member_id   IS DISTINCT FROM OLD.member_id
  OR NEW.role_id     IS DISTINCT FROM OLD.role_id
  OR NEW.approval_id IS DISTINCT FROM OLD.approval_id
  OR NEW.granted_by  IS DISTINCT FROM OLD.granted_by
  OR NEW.granted_at  IS DISTINCT FROM OLD.granted_at THEN
    RAISE EXCEPTION
      'A role grant is a historical record. Revoke it and grant again.';
  END IF;
  IF OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS NULL THEN
    RAISE EXCEPTION
      'A revocation cannot be undone by clearing it. Grant the role again.';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER role_grant_is_frozen
  BEFORE UPDATE ON member_roles
  FOR EACH ROW EXECUTE FUNCTION freeze_role_grant();

-- A recorded door event is an access record for a physical building.
CREATE FUNCTION door_events_are_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'door_events is append only.';
END $$;

CREATE TRIGGER door_events_no_update
  BEFORE UPDATE OR DELETE ON door_events
  FOR EACH ROW EXECUTE FUNCTION door_events_are_append_only();

COMMIT;
