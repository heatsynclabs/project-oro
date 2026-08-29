#!/bin/sh
# Prove 022_roles.sql cannot leave the role grant trigger turned off.
#
#   tools/migration/tests/check_the_guard.sh
#
# This is the one case tools/migration/tests/run.sh cannot reach, because every
# path through run.sh wraps the role step in a transaction and so satisfies the
# guard. What has to be proved is the opposite: the file run on its own, in
# autocommit, with no ON_ERROR_STOP, which is how a person would run it by hand
# after reading the directory listing.
#
# An earlier version of that file put the guard in its own DO block and the
# ALTER TABLE in the next statement. RAISE EXCEPTION aborts only its own
# statement, so psql went on and turned the trigger off anyway, and committed it.
# Everything is one DO block now. This is what holds that.
#
# Needs docker and nothing else. Leaves nothing behind.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
NAME="oro-migration-guard-$$"
FAILURES=0

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=guard-test \
  -e POSTGRES_DB=oro postgres:18 >/dev/null
printf 'waiting for postgres'
i=0
until docker exec "$NAME" psql -U postgres -d oro -c 'SELECT 1' >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then echo " timed out"; exit 1; fi
  printf '.'; sleep 1
done
echo " ready"

for f in "$ROOT"/db/migrations/*.sql "$ROOT"/db/seed/*.sql; do
  docker exec -i "$NAME" psql -v ON_ERROR_STOP=1 -q -U postgres -d oro < "$f"
done

# No ON_ERROR_STOP on purpose. With it, psql stops at the first error and the
# ALTER is never reached, which is what made an earlier hand check of this look
# like it passed while the defect was still there.
OUT="$(docker exec -i "$NAME" psql -q -U postgres -d oro \
        < "$ROOT/tools/migration/022_roles.sql" 2>&1 || true)"
echo "$OUT" | sed 's/^/  /'

if echo "$OUT" | grep -qF "inside the migration transaction"; then
  echo "  ok    it refused"
else
  echo "  FAIL  it did not refuse. It said: $OUT" >&2
  FAILURES=$((FAILURES + 1))
fi

STATE="$(docker exec "$NAME" psql -U postgres -d oro -At -c \
  "SELECT tgenabled FROM pg_trigger WHERE tgrelid = 'member_roles'::regclass AND tgname = 'role_grant_rules'")"
if [ "$STATE" = "O" ]; then
  echo "  ok    role_grant_rules is still enabled"
else
  echo "  FAIL  role_grant_rules is '$STATE', not 'O'. The trigger was left off" >&2
  FAILURES=$((FAILURES + 1))
fi

# And nothing was written, because the whole DO block went back.
ROWS="$(docker exec "$NAME" psql -U postgres -d oro -At -c "SELECT count(*) FROM member_roles")"
if [ "$ROWS" = "0" ]; then
  echo "  ok    no role was granted"
else
  echo "  FAIL  $ROWS role row(s) were written by a step that refused to run" >&2
  FAILURES=$((FAILURES + 1))
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "$FAILURES check(s) failed" >&2
  exit 1
fi
echo "the role step cannot leave the trigger off"
