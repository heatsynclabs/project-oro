#!/bin/sh
# Migrate a legacy database into the ORO schema, in a throwaway container.
#
#   tools/migration/run.sh              the fixture, with the decisions applied
#   tools/migration/run.sh --undecided  the fixture as it comes, which must be refused
#
# Needs docker and nothing else. Builds the ORO schema from db/migrations, loads
# the legacy schema and data beside it, and runs the migration inside one
# transaction. Leaves nothing behind. Exit code is 1 if anything failed.
#
# The legacy fixture was written by a replica of the legacy application through
# its own models. tools/migration/README.md says how it was made.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NAME="oro-migration-test-$$"
UNDECIDED=""
[ "$1" = "--undecided" ] && UNDECIDED="yes"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=migration-test \
  -e POSTGRES_DB=oro postgres:18 >/dev/null

printf 'waiting for postgres'
i=0
until docker exec "$NAME" psql -U postgres -d oro -c 'SELECT 1' >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then echo " timed out"; exit 1; fi
  printf '.'; sleep 1
done
echo " ready"

run() { docker exec -i "$NAME" psql -v ON_ERROR_STOP=1 -q -U postgres -d oro < "$1"; }

for f in "$ROOT"/db/migrations/*.sql "$ROOT"/db/seed/*.sql; do run "$f"; done
run "$ROOT/tools/migration/fixtures/legacy-schema.sql"
run "$ROOT/tools/migration/fixtures/legacy-data.sql"
echo "schema, seed and the legacy fixture are loaded"
echo

if [ -z "$UNDECIDED" ]; then
  run "$ROOT/tools/migration/fixtures/decisions.sql"
  echo "the decisions in fixtures/decisions.sql are applied"
fi

# One transaction. A migration that half ran is worse than one that did not.
{
  echo "BEGIN;"
  cat "$ROOT/tools/migration/010_preflight.sql"
  cat "$ROOT/tools/migration/020_migrate.sql"
  cat "$ROOT/tools/migration/030_verify.sql"
  echo "COMMIT;"
} > "/tmp/$NAME.sql"

OUTPUT="/tmp/$NAME.out"
if docker exec -i "$NAME" psql -v ON_ERROR_STOP=1 -q -U postgres -d oro < "/tmp/$NAME.sql" > "$OUTPUT" 2>&1; then
  cat "$OUTPUT"
  rm -f "/tmp/$NAME.sql" "$OUTPUT"
  if [ -n "$UNDECIDED" ]; then
    echo "FAIL the undecided fixture migrated, and it should have been refused" >&2
    exit 1
  fi
  docker exec "$NAME" psql -U postgres -d oro -At -c \
    "SELECT 'member ' || legacy_id || ' -> ' || coalesce(tier_id,'no tier') || ', ' || coalesce(email::text,'no email') FROM members ORDER BY legacy_id"
  docker exec "$NAME" psql -U postgres -d oro -At -c \
    "SELECT 'card ' || legacy_id || ' -> slot ' || controller_slot || ', tag ' || tag_number FROM cards ORDER BY legacy_id"
  echo
  echo "the migration ran and every assertion in data-model.md section 6.2 holds"
  exit 0
fi

cat "$OUTPUT"
rm -f "/tmp/$NAME.sql"
if [ -n "$UNDECIDED" ]; then
  # Refused is only the right answer if it was refused by the preflight. Any
  # other error means the script broke, and a broken script that exits nonzero
  # looks exactly like a working refusal from the outside.
  if grep -q "a person has to decide" "$OUTPUT"; then
    rm -f "$OUTPUT"
    echo
    echo "refused by the preflight, naming what a person has to decide"
    exit 0
  fi
  rm -f "$OUTPUT"
  echo "FAIL it failed, but not by refusing. Read the error above" >&2
  exit 1
fi
rm -f "$OUTPUT"
echo "FAIL the migration did not run" >&2
exit 1
