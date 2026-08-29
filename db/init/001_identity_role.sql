-- The identity service gets its own role and its own database on this server,
-- created before it first connects.
--
-- Zitadel can create both for itself, and this file exists so that it does not.
-- Its own initialisation opens an admin connection, and the only admin account
-- on this server is the Postgres superuser, so letting Zitadel do it means the
-- identity service holds the database password for the rest of its life. Rule 13
-- of CLAUDE.md gives each of the three secrets that matter exactly one holder
-- process, and docs/plan/architecture.md section 1 says the identity service can
-- be replaced without touching member data. Neither survives handing it the
-- superuser password.
--
-- So the role is made here, with a login and nothing else, and the database is
-- made with that role as its owner. Zitadel connects as itself and finds both
-- already there.
--
-- This runs from /docker-entrypoint-initdb.d, which the postgres image executes
-- once, on an empty data directory, and never again. A stack whose volume
-- predates this file has no identity role: take it down with its volume, or run
-- these two statements by hand with make psql.

\getenv identity_password ORO_IDENTITY_DB_PASSWORD

-- psql expands the password into the statement text before sending it, so an
-- error on the next line would put the plaintext into the server log, which
-- make logs prints to whoever is watching. Statement logging is off for the
-- rest of this file and restored at the end of it.
SET log_statement = 'none';
SET log_min_error_statement = 'panic';

CREATE ROLE identity LOGIN PASSWORD :'identity_password';

-- Owner, so Zitadel can create its own schema, tables and extensions inside it
-- without any right on the oro database beside it.
CREATE DATABASE identity OWNER identity;

COMMENT ON DATABASE identity IS
  'Credentials, held by the identity service. Separate from oro on purpose: the API role cannot read a password hash and the identity service cannot read a member row.';

RESET log_min_error_statement;
RESET log_statement;
