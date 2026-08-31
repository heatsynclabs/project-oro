#!/bin/sh
# Put the members schema into the stack's database, and the login role the
# members API connects as.
#
# The "schema" service in compose.api.yaml runs this once, before the API
# starts, and it is the only thing that applies db/migrations to a database
# this stack owns.
#
# It is not in db/init/. The postgres image runs that directory once, against
# an empty data directory, and never again, so anybody who already has a
# database volume would never see it and their API would find no tables. This
# runs on every start instead, and does nothing when the work is already done.
#
# It is not a migration runner either, and nothing here pretends otherwise. It
# records nothing about which files ran, so a migration written after the
# database was built is not applied by it and will not be. Whoever needs that
# needs a decision written down first, in docs/decisions/, rather than a wider
# loop here.
#
# Every message it prints is read by whoever runs make up, so each one says
# what happened and what is true afterwards.

set -e

export PGPASSWORD="$ORO_DB_PASSWORD"
PSQL="psql --host db --username postgres --dbname oro --set ON_ERROR_STOP=1 --quiet"

if [ "$($PSQL --tuples-only --no-align --command "SELECT to_regclass('public.members') IS NOT NULL")" = "t" ]; then
  echo "The members database already has a schema, so no migration was applied."
else
  for statements in /oro/db/migrations/*.sql /oro/db/seed/*.sql; do
    echo "applying $(basename "$statements")"
    $PSQL --file "$statements" >/dev/null
  done
  echo "The schema and the reference data are in."
fi

# A separate question from the one above, because the two can be true
# separately: a database somebody migrated by hand has the tables and no login
# role, and the API would then start and fail to connect.
if [ "$($PSQL --tuples-only --no-align --command "SELECT count(*) FROM pg_roles WHERE rolname = 'oro_api_login'")" = "0" ]; then
  $PSQL --file /oro/api/oro_api_login.sql >/dev/null
  echo "oro_api_login is created, so the members API can log in."
else
  echo "oro_api_login already exists and its password was left as it was."
  echo "If the API answers nothing and its log says password authentication"
  echo "failed, the value in .env is not the one that role holds. Change it"
  echo "back, or run: ALTER ROLE oro_api_login PASSWORD '...' with make psql."
fi
