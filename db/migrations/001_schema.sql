-- Project ORO, schema.
--
-- This file is the authority for the schema. docs/plan/data-model.md explains
-- why it looks like this and does not repeat the DDL, so the two cannot drift.
--
-- Order is lookups, then members, then everything that references members.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- Borrowed from heatsynclabs/members_api (Apache 2.0, Iced Development LLC),
-- migrations/up/20180217155311_initial.sql.
CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$;

-- ------------------------------------------------------------------ lookups

CREATE TABLE tiers (
  id             text PRIMARY KEY,
  name           text NOT NULL,
  monthly_cents  integer NOT NULL,
  sort_order     integer NOT NULL,
  card_eligible  boolean NOT NULL DEFAULT false,
  storage        text,
  active         boolean NOT NULL DEFAULT true,
  notes          text
);
COMMENT ON TABLE tiers IS
  'Membership tiers with a price. Replaces the legacy member_level integer, '
  'which encoded the tier and the dollar amount in one column and returned '
  'null for values 2 to 9.';
COMMENT ON COLUMN tiers.card_eligible IS
  'Whether this tier may be nominated for card access. Bylaws: the $50 level '
  'or higher. Data rather than a magic number in code.';

CREATE TABLE roles (
  id           text PRIMARY KEY,
  name         text NOT NULL,
  description  text NOT NULL,
  grants_roles boolean NOT NULL DEFAULT false
);
COMMENT ON COLUMN roles.grants_roles IS
  'True for roles that can themselves grant roles. This flag is what the two '
  'approver policy protects, so no application role has write access here: '
  'changing it is a migration.';

CREATE TABLE certifications (
  id               text PRIMARY KEY,
  name             text NOT NULL,
  description      text,
  prerequisite_id  text REFERENCES certifications(id),
  validity_months  integer,
  active           boolean NOT NULL DEFAULT true,
  legacy_id        integer UNIQUE
);

CREATE TABLE governance_parameters (
  key         text PRIMARY KEY,
  value       jsonb NOT NULL,
  unit        text,
  source      text NOT NULL,
  effective   date NOT NULL,
  updated_by  uuid,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE governance_parameters IS
  'Bylaws numbers as data, not as CHECK constraints. The card access rules '
  'changed three times in eight months; each change would otherwise be a '
  'developer writing a migration. Admins edit these with a citation.';
COMMENT ON COLUMN governance_parameters.source IS
  'Required. Which bylaws section or vote set this value. A number here '
  'without a citation is a number somebody made up.';

CREATE TABLE governance_parameter_history (
  id          bigserial PRIMARY KEY,
  key         text NOT NULL,
  old_value   jsonb,
  new_value   jsonb NOT NULL,
  source      text NOT NULL,
  changed_by  uuid,
  changed_at  timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ members

CREATE TABLE members (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identity_subject    text UNIQUE,
  email               citext UNIQUE,
  email_verified_at   timestamptz,
  name                text NOT NULL,
  display_name        text,
  pronouns            text,
  phone               text,
  postal_code         text,
  tier_id             text REFERENCES tiers(id),
  legacy_member_level integer,
  joined_on           date,
  paid_through        date,
  standing            text NOT NULL DEFAULT 'unknown'
                      CHECK (standing IN ('good','grace','lapsed','unknown')),
  oriented_at         timestamptz,
  oriented_by         uuid REFERENCES members(id),
  current_skills      text,
  desired_skills      text,
  marketing_source    text,
  email_visible       boolean NOT NULL DEFAULT false,
  phone_visible       boolean NOT NULL DEFAULT false,
  listed_in_directory boolean NOT NULL DEFAULT true,
  legacy_id           integer UNIQUE,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz
);
COMMENT ON TABLE members IS
  'A person the lab knows about. Not the same as a login account: a member may '
  'have signed a waiver and never created one. There are paying members today '
  'who never signed up on the members site.';
COMMENT ON COLUMN members.identity_subject IS
  'Stable subject id from the identity provider. Null means no login. Policies '
  'key on this, never on email, because emails change and the legacy accounts '
  'were never verified (Devise :confirmable was never enabled).';
COMMENT ON COLUMN members.standing IS
  'Payments are out of scope, so this is set by hand for now. unknown is the '
  'default because the legacy data does not support claiming good standing.';
COMMENT ON COLUMN members.legacy_id IS
  'users.id from the Rails database. Kept for audit and to re-run an import.';

CREATE TRIGGER members_updated_at BEFORE UPDATE ON members
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE governance_parameters
  ADD CONSTRAINT governance_parameters_updated_by_fkey
  FOREIGN KEY (updated_by) REFERENCES members(id);
ALTER TABLE governance_parameter_history
  ADD CONSTRAINT governance_parameter_history_changed_by_fkey
  FOREIGN KEY (changed_by) REFERENCES members(id);

COMMIT;
