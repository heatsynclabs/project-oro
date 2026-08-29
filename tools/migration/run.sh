#!/bin/sh
# Migrate a legacy database into the ORO schema, in a throwaway container.
#
#   tools/migration/run.sh              the fixture, with the decisions applied
#   tools/migration/run.sh --undecided  the fixture as it comes, which must be refused
#
# Four options exist for the suite beside this file, and each is named rather
# than inferred so a reader can see what a test changed:
#
#   --also FILE      apply FILE after the decisions, to put one thing back
#   --refusal TEXT   the run must be refused, and the message must contain TEXT
#   --roles FILE     the role step, normally 022_roles.sql. A test replaces it
#                    with a copy that does not disable the role grant trigger,
#                    which is how the disable is proved to be load bearing
#   --timezone TZ    run the migration transaction in this session time zone.
#                    A date carried out of a `timestamp without time zone`
#                    column lands wrong if anything reads it in the local zone,
#                    and the lab's own zone is the one that would do it
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
ALSO=""
REFUSAL=""
ROLES="$ROOT/tools/migration/022_roles.sql"
TIMEZONE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --undecided) UNDECIDED="yes"; REFUSAL="a person has to decide" ;;
    --also)      ALSO="$2"; shift ;;
    --refusal)   REFUSAL="$2"; shift ;;
    --roles)     ROLES="$2"; shift ;;
    --timezone)
      # Interpolated into SQL below, so it is checked here rather than trusted.
      # A zone name is letters, digits, slash, underscore, plus and minus.
      case "$2" in
        *[!A-Za-z0-9/_+-]*|"") echo "run.sh: --timezone '$2' is not a time zone name" >&2; exit 1 ;;
      esac
      TIMEZONE="$2"; shift ;;
    *) echo "run.sh: unknown option '$1'. The header of this file lists them" >&2; exit 1 ;;
  esac
  shift
done

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
# The staging table for the answers, before the answers. It is not legacy data
# and 005_staging.sql says why it is not.
run "$ROOT/tools/migration/005_staging.sql"
echo "schema, seed and the legacy fixture are loaded"
echo

if [ -z "$UNDECIDED" ]; then
  run "$ROOT/tools/migration/fixtures/decisions.sql"
  echo "the decisions in fixtures/decisions.sql are applied"
fi
if [ -n "$ALSO" ]; then
  run "$ALSO"
  echo "and $ALSO on top of them"
fi

# One transaction. A migration that half ran is worse than one that did not.
{
  echo "BEGIN;"
  [ -n "$TIMEZONE" ] && echo "SET TIME ZONE '$TIMEZONE';"
  cat "$ROOT/tools/migration/010_preflight.sql"
  cat "$ROOT/tools/migration/020_migrate.sql"
  cat "$ROLES"
  cat "$ROOT/tools/migration/024_waivers.sql"
  # 040 before 030, which is not the numeric order and is not a mistake: 040
  # carries who oriented whom, and 030 asserts that it did.
  cat "$ROOT/tools/migration/040_not_carried.sql"
  cat "$ROOT/tools/migration/030_verify.sql"
  echo "COMMIT;"
} > "/tmp/$NAME.sql"

OUTPUT="/tmp/$NAME.out"
if docker exec -i "$NAME" psql -v ON_ERROR_STOP=1 -q -U postgres -d oro < "/tmp/$NAME.sql" > "$OUTPUT" 2>&1; then
  cat "$OUTPUT"
  rm -f "/tmp/$NAME.sql" "$OUTPUT"
  if [ -n "$REFUSAL" ]; then
    echo "FAIL it migrated, and it should have been refused for: $REFUSAL" >&2
    exit 1
  fi
  docker exec "$NAME" psql -U postgres -d oro -At -c \
    "SELECT 'member ' || legacy_id || ' -> ' || coalesce(tier_id,'no tier') || ', ' || coalesce(email::text,'no email') FROM members ORDER BY legacy_id"
  docker exec "$NAME" psql -U postgres -d oro -At -c \
    "SELECT 'card ' || legacy_id || ' -> slot ' || controller_slot || ', tag ' || tag_number FROM cards ORDER BY legacy_id"
  docker exec "$NAME" psql -U postgres -d oro -At -c \
    "SELECT 'role ' || m.legacy_id || ' -> ' || r.role_id || ', approval ' || coalesce(r.approval_id::text,'none') FROM member_roles r JOIN members m ON m.id = r.member_id ORDER BY m.legacy_id, r.role_id"
  # Rendered in UTC so the line means the same thing whatever zone the run was
  # given. A naive legacy timestamp read in the wrong zone lands seven hours out
  # and every assertion inside the migration still agrees with itself.
  docker exec "$NAME" psql -U postgres -d oro -At -c \
    "SELECT 'oriented ' || legacy_id || ' -> ' || (oriented_at AT TIME ZONE 'UTC') || ' UTC' FROM members WHERE oriented_at IS NOT NULL ORDER BY legacy_id"
  docker exec "$NAME" psql -U postgres -d oro -At -c \
    "SELECT 'card issued ' || legacy_id || ' -> ' || (issued_at AT TIME ZONE 'UTC') || ' UTC' FROM cards ORDER BY legacy_id LIMIT 1"
  docker exec "$NAME" psql -U postgres -d oro -At -c \
    "SELECT 'waiver ' || m.legacy_id || ' -> signed ' || (w.signed_at AT TIME ZONE 'UTC') || ' UTC, kept in ' || w.storage FROM waivers w JOIN members m ON m.id = w.member_id ORDER BY m.legacy_id"
  echo
  echo "the migration ran and every assertion in data-model.md section 6.2 holds"
  exit 0
fi

cat "$OUTPUT"
rm -f "/tmp/$NAME.sql"
if [ -n "$REFUSAL" ]; then
  # Refused is only the right answer if it was refused for the stated reason.
  # Any other error means the script broke, and a broken script that exits
  # nonzero looks exactly like a working refusal from the outside.
  if grep -qF "$REFUSAL" "$OUTPUT"; then
    rm -f "$OUTPUT"
    echo
    echo "refused, saying: $REFUSAL"
    exit 0
  fi
  rm -f "$OUTPUT"
  echo "FAIL it failed, but not by saying '$REFUSAL'. Read the error above" >&2
  exit 1
fi
rm -f "$OUTPUT"
echo "FAIL the migration did not run" >&2
exit 1
