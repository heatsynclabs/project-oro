#!/bin/sh
# Rebuild the schema from nothing and run every database test.
#
#   db/tests/run.sh
#
# Needs docker. Leaves nothing behind. Exit code is the number of failures.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NAME="oro-test-$$"
WORK="$(mktemp -d)"
PSQL="docker exec -i $NAME psql -U postgres -d oro -v ON_ERROR_STOP=1 -q"

# macOS ships shasum and no sha256sum. A plain Debian or Ubuntu image, which is
# what CI runs on, ships sha256sum and no shasum. Both print the digest first,
# so the caller does not care which one answered.
if command -v shasum >/dev/null 2>&1; then SHA256="shasum -a 256"
else SHA256="sha256sum"; fi

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT

docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=test -e POSTGRES_DB=oro \
  postgres:18 >/dev/null
# The official postgres image runs a temporary server during initdb and then
# restarts it. pg_isready goes true during that first phase, so waiting on it
# alone races the restart and the schema lands in a database that is about to
# disappear. Wait for a real query against the real database, twice in a row.
printf 'waiting for postgres'
i=0
ok=0
while [ "$ok" -lt 2 ]; do
  if docker exec "$NAME" psql -U postgres -d oro -tAc 'SELECT 1' >/dev/null 2>&1; then
    ok=$((ok+1))
  else
    ok=0
  fi
  i=$((i+1)); [ "$i" -gt 90 ] && { echo " timed out"; exit 1; }
  printf '.'; sleep 1
done
echo " ready"

for f in "$ROOT"/db/migrations/*.sql "$ROOT"/db/seed/*.sql; do
  base="$(basename "$f")"
  printf 'applying %-28s' "$base"
  docker cp "$f" "$NAME:/tmp/m.sql" >/dev/null
  $PSQL -f /tmp/m.sql >/dev/null
  # Record it, the same way a real apply would, so the runner exercises the
  # tracking table rather than leaving it untested.
  case "$base" in
    000_*) : ;;
    *) sum=$($SHA256 "$f" | cut -d' ' -f1)
       $PSQL -c "INSERT INTO schema_migrations (filename, sha256)
                 VALUES ('$base', '$sum')" >/dev/null ;;
  esac
  echo "ok"
done

docker cp "$ROOT/db/tests/helpers.sql" "$NAME:/tmp/h.sql" >/dev/null
$PSQL -f /tmp/h.sql >/dev/null
echo "loaded test helpers"
echo

fails=0
if grep -l '^FAIL' "$ROOT"/db/tests/*.expected >/dev/null 2>&1; then
  echo "refusing to run: these expected files contain failing assertions"
  grep -l '^FAIL' "$ROOT"/db/tests/*.expected | sed 's/^/  /'
  exit 1
fi

for f in "$ROOT"/db/tests/*.expected; do
  base="$(basename "$f" .expected)"
  printf 'test %-32s' "$base"
  # Each file runs in its own transaction and rolls back, so tests are
  # independent and can be run in any order. Without this, one file's rows
  # leak into the next and a passing suite depends on filename sort order.
  { echo "BEGIN;"; cat "$ROOT/db/tests/$base.sql"; echo "ROLLBACK;"; } > "$WORK/wrapped.sql"
  docker cp "$WORK/wrapped.sql" "$NAME:/tmp/t.sql" >/dev/null
  # stderr only. Every assertion is a RAISE NOTICE, which goes to stderr, while
  # stdout carries CALL/SET/INSERT noise. Merging the two with 2>&1 lets them
  # interleave mid line and the suite goes flaky, which it did.
  docker exec -i "$NAME" psql -U postgres -d oro -q -f /tmp/t.sql 2>"$WORK/$base.err" >/dev/null || true
  grep -vE '^(CONTEXT|HINT|DETAIL)' "$WORK/$base.err" \
    | sed -e 's/^psql:[^:]*:[0-9]*: //' -e 's/^NOTICE:  //' > "$WORK/$base.actual" || true
  if grep -qE 'relation "(members|cards|roles|tiers)" does not exist' \
       "$WORK/$base.actual" 2>/dev/null; then
    echo "BROKEN RUN"
    echo "  The schema was missing when this test ran. Not a test failure."
    head -3 "$WORK/$base.actual" | sed 's/^/  /'
    fails=$((fails+1)); continue
  fi
  # A failing assertion must never become expected output. Capturing one is how
  # a suite reports green forever while a rule it claims to enforce is broken,
  # which is exactly what happened here: five FAIL lines sat in expected files
  # and every run said all tests passed.
  # A file that aborts produces no FAIL lines at all, so counting them is not
  # enough. Every `CALL t.must` must produce exactly one ok or FAIL line, or the
  # file did not finish and its silence is not a pass.
  want=$(grep -c 'CALL t\.must' "$ROOT/db/tests/$base.sql" || true)
  got=$(grep -cE '^(ok|FAIL) ' "$WORK/$base.actual" 2>/dev/null || true)
  if [ "$want" -ne "$got" ]; then
    echo "INCOMPLETE"
    echo "  $want assertions in the file, $got reported. It did not finish."
    grep -m3 -E '^ERROR' "$WORK/$base.actual" 2>/dev/null | sed 's/^/  /'
    fails=$((fails+1)); continue
  fi
  if grep -q '^FAIL' "$WORK/$base.actual" 2>/dev/null; then
    echo "FAILING ASSERTIONS"
    grep '^FAIL' "$WORK/$base.actual" | sed 's/^/  /'
    fails=$((fails+1)); continue
  fi
  if [ "$1" = "--update" ]; then
    cp "$WORK/$base.actual" "$f"; echo "updated"; continue
  fi
  if diff -q "$f" "$WORK/$base.actual" >/dev/null 2>&1; then
    echo "ok"
  else
    echo "FAILED"
    diff "$f" "$WORK/$base.actual" | head -30
    fails=$((fails+1))
  fi
done

echo
[ "$fails" -eq 0 ] && echo "all database tests passed" || echo "$fails test file(s) failed"
exit "$fails"
