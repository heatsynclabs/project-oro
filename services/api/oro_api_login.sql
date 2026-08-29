-- The role the members API logs in as, and the reason it is not oro_api.
--
-- db/migrations/004_security.sql creates oro_api NOLOGIN, so nothing can connect
-- as it. That is deliberate: a role with a password is a role somebody can reach
-- from outside, and the role the policies are written against should not be one.
-- So the service logs in as this role and becomes oro_api for the length of each
-- transaction.
--
-- NOINHERIT is the part that matters, and it is not a style choice. Five places
-- in the schema branch on whether current_user is 'oro_api', which is how they
-- tell a member's own request apart from a migration or an import:
-- 004_security.sql line 86, 010_close_approval_holes.sql lines 43 and 60, and
-- 012_close_remaining.sql lines 69 and 123. A login role that inherited
-- oro_api's privileges would hold them while current_user still read
-- 'oro_api_login', so every one of those carve outs would fire and the profile
-- self edit trigger, among others, would wave the request through. With
-- NOINHERIT this role holds nothing at all until it runs SET LOCAL ROLE oro_api,
-- and after that current_user is oro_api and the carve outs read correctly.
--
-- What this leaves: a connection that has not set the role can read nothing, so
-- a bug that skips the role fails closed with a permission error rather than
-- silently reading past a policy. And there is no bypass to take, because
-- oro_api is not a superuser, owns no table, and does not carry BYPASSRLS.
--
-- WHERE THIS FILE BELONGS. Next to db/init/001_identity_role.sql, as
-- db/init/002_api_role.sql, so the postgres image runs it once against an empty
-- data directory the way it runs the identity role. It is here instead because
-- this change owns services/api and does not own db/. services/api/README.md
-- names that as the next step, and until it is taken the only thing that applies
-- this file is services/api/tests/run.sh.
--
-- Apply it as the postgres superuser, against the oro database:
--
--   ORO_API_DB_PASSWORD=... psql -U postgres -d oro -f services/api/oro_api_login.sql

\getenv api_password ORO_API_DB_PASSWORD

-- psql expands the password into the statement text before sending it, so an
-- error on the next line would put the plaintext into the server log. This is
-- the same guard db/init/001_identity_role.sql uses, for the same reason.
SET log_statement = 'none';
SET log_min_error_statement = 'panic';

CREATE ROLE oro_api_login LOGIN NOINHERIT PASSWORD :'api_password';
GRANT oro_api TO oro_api_login;

RESET log_min_error_statement;
RESET log_statement;

COMMENT ON ROLE oro_api_login IS
  'The members API logs in as this and runs SET LOCAL ROLE oro_api on every '
  'transaction. NOINHERIT, so it holds nothing until it does, and so that '
  'current_user reads oro_api once it has.';
