-- Cards, the door log, waivers, certifications, and the two approval
-- mechanisms. Everything that references members.

BEGIN;

-- ------------------------------------------------------------------- cards

CREATE TABLE cards (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id        uuid REFERENCES members(id) ON DELETE SET NULL,
  tag_number       text NOT NULL,
  controller_slot  integer UNIQUE,
  permission_mask  integer NOT NULL DEFAULT 1,
  label            text,
  active           boolean NOT NULL DEFAULT true,
  issued_at        timestamptz NOT NULL DEFAULT now(),
  revoked_at       timestamptz,
  revoked_by       uuid REFERENCES members(id),
  revoked_reason   text,
  legacy_id        integer UNIQUE,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT tag_is_normalised_hex CHECK (tag_number ~ '^[0-9A-F]{1,8}$'),
  CONSTRAINT controller_slot_is_addressable
    CHECK (controller_slot IS NULL OR controller_slot BETWEEN 10 AND 199),
  CONSTRAINT revoked_cards_are_inactive
    CHECK (revoked_at IS NULL OR NOT active)
);
CREATE UNIQUE INDEX cards_active_tag ON cards (tag_number) WHERE active;
CREATE INDEX cards_member ON cards (member_id);
CREATE TRIGGER cards_updated_at BEFORE UPDATE ON cards
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON COLUMN cards.controller_slot IS
  'EEPROM user slot on the Open_Access_Control controller, 10 to 199. Slots 0 '
  'to 9 are reserved for testing. Slot 200 passes the firmware bounds check '
  '(it uses > rather than >=) and its offset wraps through the AVR 10 bit '
  'address register onto the alarm state bytes, so the range is enforced here '
  'rather than in a form. On migration this is set to the legacy cards.id, '
  'which preserves every existing door mapping.';
COMMENT ON COLUMN cards.tag_number IS
  'Uppercase hex, at most 8 characters. The controller reads only the first 8 '
  'and does not error on a longer value, it writes a different tag. Mixed case '
  'would defeat the reconciler diff and silently rewrite every slot on every '
  'pass, which wears out the EEPROM.';

CREATE TABLE door_events (
  id             bigserial PRIMARY KEY,
  occurred_at    timestamptz NOT NULL,
  recorded_at    timestamptz NOT NULL DEFAULT now(),
  source         text NOT NULL CHECK (source IN ('controller','service','portal')),
  event_key      text NOT NULL,
  raw_data       integer,
  card_id        uuid REFERENCES cards(id) ON DELETE SET NULL,
  member_id      uuid REFERENCES members(id) ON DELETE SET NULL,
  door           text,
  detail         jsonb NOT NULL DEFAULT '{}',
  dedupe_key     text NOT NULL
);
CREATE UNIQUE INDEX door_events_dedupe ON door_events (dedupe_key);
CREATE INDEX door_events_time ON door_events (occurred_at DESC);
CREATE INDEX door_events_member ON door_events (member_id, occurred_at DESC);

COMMENT ON TABLE door_events IS
  'Append only. A record of who entered a building and when. No application '
  'role is granted UPDATE or DELETE here.';
COMMENT ON COLUMN door_events.dedupe_key IS
  'The door service buffers events during a partition and flushes on '
  'reconnect. A retried flush must not double record somebody entering.';
COMMENT ON COLUMN door_events.recorded_at IS
  'Separate from occurred_at because buffered events arrive late. Collapsing '
  'them would make every event look like it happened at flush time.';

-- ----------------------------------------------------------------- waivers

CREATE TABLE waivers (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id         uuid REFERENCES members(id),
  signed_name       text NOT NULL,
  signed_email      citext NOT NULL,
  signed_phone      text,
  signed_address    text,
  emergency_name    text,
  emergency_phone   text,
  emergency_email   citext,
  is_minor          boolean NOT NULL DEFAULT false,
  guardian_name     text,
  document_version  text,
  document_sha256   text,
  signed_at         timestamptz NOT NULL,
  expires_at        timestamptz,
  signature_ip      inet,
  legacy_source     text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT minor_needs_guardian
    CHECK (NOT is_minor OR guardian_name IS NOT NULL),
  CONSTRAINT new_waivers_record_what_was_signed
    CHECK (legacy_source IS NOT NULL
           OR (document_version IS NOT NULL AND document_sha256 IS NOT NULL))
);
CREATE INDEX waivers_member ON waivers (member_id, signed_at DESC);

COMMENT ON COLUMN waivers.document_sha256 IS
  'Hash of the exact text the person agreed to. Null only for imported '
  'records: the Google Form used since 2022 stores a spreadsheet row, not a '
  'document, so there is nothing to hash. A null here means the record proves '
  'somebody signed something, not what they signed.';

-- Hosts and instructors need to check a waiver exists without seeing what is
-- on it. That is this view, not a permission on the table.
CREATE VIEW waiver_status AS
SELECT member_id,
       max(signed_at) AS latest_signed_at,
       bool_or(expires_at IS NULL OR expires_at > now()) AS has_valid_waiver
FROM waivers WHERE member_id IS NOT NULL GROUP BY member_id;

-- ---------------------------------------------------------- certifications

CREATE TABLE member_certifications (
  id               bigserial PRIMARY KEY,
  member_id        uuid NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  certification_id text NOT NULL REFERENCES certifications(id),
  granted_by       uuid REFERENCES members(id),
  granted_at       timestamptz NOT NULL DEFAULT now(),
  expires_at       timestamptz,
  revoked_at       timestamptz,
  revoked_by       uuid REFERENCES members(id),
  revoked_reason   text,
  note             text,
  CONSTRAINT cert_revocations_have_a_reason
    CHECK (revoked_at IS NULL OR revoked_reason IS NOT NULL)
);
-- Partial, not total: somebody can be certified, revoked, and certified again.
CREATE UNIQUE INDEX member_certifications_one_live
  ON member_certifications (member_id, certification_id) WHERE revoked_at IS NULL;

CREATE TABLE certification_instructors (
  member_id        uuid NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  certification_id text NOT NULL REFERENCES certifications(id),
  granted_by       uuid REFERENCES members(id),
  granted_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (member_id, certification_id)
);
COMMENT ON TABLE certification_instructors IS
  'Instructors are per tool, never global. Someone who instructs on the laser '
  'is not thereby an instructor on the mill, and only an instructor for a '
  'given certification may grant it.';

-- ---------------------------------------------- the two approval mechanisms

CREATE TABLE approvals (
  id               bigserial PRIMARY KEY,
  kind             text NOT NULL CHECK (kind IN ('grant_role','revoke_role')),
  target_member_id uuid NOT NULL REFERENCES members(id),
  role_id          text NOT NULL REFERENCES roles(id),
  reason           text,
  proposed_by      uuid NOT NULL REFERENCES members(id),
  proposed_at      timestamptz NOT NULL DEFAULT now(),
  decided_by       uuid REFERENCES members(id),
  decided_at       timestamptz,
  status           text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','approved','rejected','withdrawn')),
  expires_at       timestamptz NOT NULL DEFAULT now() + interval '30 days',
  CONSTRAINT approver_is_not_proposer
    CHECK (decided_by IS NULL OR decided_by <> proposed_by),
  CONSTRAINT decided_rows_have_a_decider
    CHECK ((status IN ('pending','withdrawn')) = (decided_by IS NULL)),
  UNIQUE (id, target_member_id, role_id)
);
COMMENT ON TABLE approvals IS
  'Two approver control on admin access changes. NEW POLICY introduced by this '
  'project: no two admin rule exists in the bylaws, the Rules page, or the '
  'legacy app. It needs an HYH vote before it binds anyone. The bylaws two '
  'signature rule is about monetary expenditure and is unrelated.';
COMMENT ON CONSTRAINT approver_is_not_proposer ON approvals IS
  'Not a policy parameter. No bylaws amendment makes self approval acceptable.';

CREATE TABLE member_roles (
  id             bigserial PRIMARY KEY,
  member_id      uuid NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  role_id        text NOT NULL REFERENCES roles(id),
  granted_by     uuid REFERENCES members(id),
  granted_at     timestamptz NOT NULL DEFAULT now(),
  approval_id    bigint,
  expires_at     timestamptz,
  revoked_at     timestamptz,
  revoked_by     uuid REFERENCES members(id),
  revoked_reason text,
  CONSTRAINT role_revocations_have_a_reason
    CHECK (revoked_at IS NULL OR revoked_reason IS NOT NULL),
  -- The composite key is what stops one approval justifying a different grant.
  CONSTRAINT approval_authorises_this_exact_grant
    FOREIGN KEY (approval_id, member_id, role_id)
    REFERENCES approvals (id, target_member_id, role_id)
);
-- Surrogate key, not (member_id, role_id): revocation is a recorded row rather
-- than a DELETE, so a composite key would block ever granting a role back to
-- somebody it was revoked from.
CREATE UNIQUE INDEX member_roles_one_live
  ON member_roles (member_id, role_id) WHERE revoked_at IS NULL;
CREATE UNIQUE INDEX member_roles_one_grant_per_approval
  ON member_roles (approval_id) WHERE approval_id IS NOT NULL;
CREATE INDEX member_roles_live ON member_roles (member_id) WHERE revoked_at IS NULL;

CREATE TABLE card_proposals (
  id                  bigserial PRIMARY KEY,
  nominee_id          uuid NOT NULL REFERENCES members(id),
  nominator_id        uuid NOT NULL REFERENCES members(id),
  posted_at           timestamptz,
  meeting_date        date,
  cardholders_present integer,
  votes_for           integer,
  votes_against       integer,
  status              text NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft','posted','approved','rejected','withdrawn')),
  outcome_note        text,
  mentorship_ends_on  date,
  created_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT nominator_is_not_nominee CHECK (nominator_id <> nominee_id)
);
COMMENT ON TABLE card_proposals IS
  'The bylaws card access process. Quorum, notice period, and tenure are read '
  'from governance_parameters at validation time rather than hardcoded, '
  'because the bylaws change and a bylaws change must not require a developer.';

CREATE TABLE payments (
  id            bigserial PRIMARY KEY,
  member_id     uuid REFERENCES members(id),
  amount_cents  integer NOT NULL,
  paid_on       date NOT NULL,
  method        text NOT NULL,
  external_ref  text,
  note          text,
  recorded_by   uuid REFERENCES members(id),
  legacy_id     integer UNIQUE,
  created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE payments IS
  'Reserved. Payments are out of scope for this build; the table exists so '
  'adding them later is not a reshape. Deliberately no unique constraint on '
  '(member_id, paid_on): the legacy schema had one and it made two payments on '
  'the same day impossible to record. No amount whitelist either, so the '
  'teacher half rate and prorated amounts are recordable.';

COMMIT;
