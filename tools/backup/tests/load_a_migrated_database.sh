#!/bin/sh
# Start a throwaway Postgres and fill it with a database shaped like the one
# the lab will have on the day the migration runs: the ORO schema, the
# reference seed, and the legacy fixture carried through the real import.
#
#   tools/backup/tests/load_a_migrated_database.sh CONTAINER_NAME
#
# The steps and their order belong to tools/migration/run.sh, which is the file
# that owns them. 040 runs before 030 there and here, for the reason its
# comment gives. If the two ever disagree, 030_verify.sql fails inside this
# import and says which assertion broke.
#
# The rows are invented members. tools/migration/README.md says how the fixture
# was written, and rule 13 of CLAUDE.md is why it is not a copy of anybody.
#
# Needs docker. The container it starts has no published port and no volume, so
# removing the container destroys the cluster, which is what the drill wants.

set -e
NAME="$1"
if [ -z "$NAME" ]; then
  echo "load_a_migrated_database.sh: name the container to start." >&2
  echo "The drill in tools/backup/tests/run.sh passes a name carrying its own" >&2
  echo "process id, so two runs on one machine cannot collide." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=drill \
  -e POSTGRES_DB=oro postgres:18 >/dev/null

. "$ROOT/tools/backup/tests/checks.sh"
wait_for_postgres "$NAME"

run() { docker exec -i "$NAME" psql -v ON_ERROR_STOP=1 -q -U postgres -d oro < "$1"; }

for f in "$ROOT"/db/migrations/*.sql "$ROOT"/db/seed/*.sql; do run "$f"; done
run "$ROOT/tools/migration/fixtures/legacy-schema.sql"
run "$ROOT/tools/migration/fixtures/legacy-data.sql"
run "$ROOT/tools/migration/005_staging.sql"
run "$ROOT/tools/migration/fixtures/decisions.sql"
echo "schema, seed, the legacy fixture and the decisions are loaded"

{
  echo "BEGIN;"
  cat "$ROOT/tools/migration/010_preflight.sql"
  cat "$ROOT/tools/migration/020_migrate.sql"
  cat "$ROOT/tools/migration/022_roles.sql"
  cat "$ROOT/tools/migration/024_waivers.sql"
  cat "$ROOT/tools/migration/040_not_carried.sql"
  cat "$ROOT/tools/migration/030_verify.sql"
  echo "COMMIT;"
} > "$WORK/import.sql"

# Not piped into grep. A pipeline reports the exit code of its last command, so
# an import that failed would be filtered away and this script would carry on
# and hand the drill an empty database to back up.
if ! docker exec -i "$NAME" psql -v ON_ERROR_STOP=1 -q -U postgres -d oro \
     < "$WORK/import.sql" > "$WORK/import.out" 2>&1; then
  cat "$WORK/import.out" >&2
  echo "load_a_migrated_database.sh: the legacy import did not run, and the" >&2
  echo "error above says why. The same import runs on its own under" >&2
  echo "tools/migration/tests/run.sh, which is the shorter thing to debug." >&2
  exit 1
fi
grep 'verify:' "$WORK/import.out"
echo "the legacy import ran"
