#!/bin/sh
# Seat the first three admins against a real stack, and prove what that leaves.
#
#   tools/bootstrap/tests/run.sh
#
# Needs docker and python3. Runs as its own compose project on its own ports and
# supplies its own values for everything compose reads, so a stack somebody is
# already running is neither read nor touched, and no .env has to exist. Leaves
# nothing behind. Exit code is 1 if any check failed.
#
# Five parts, in this order because each one needs the one before it:
#
#   the first run           three people who are on neither system yet
#   check_seats.py          what the identity service and the database now hold
#   the second run          the same three again, which must change nothing
#   the fourth admin        refused, and refused by the database
#   check_first_sign_in.py  one admin all the way through the hosted screens
#
# The last one is last because it changes a password, and every check before it
# reads the handover password the first run printed.
#
# Every refusal is checked by its own text as well as by its exit code. A broken
# command that exits nonzero looks exactly like a working refusal from outside.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TESTS="$ROOT/tools/bootstrap/tests"

PROJECT="oro-bootstrap-test-$$"
export ORO_HOSTNAME=localhost
export ORO_TLS=internal
export ORO_HTTP_PORT=8092
export ORO_HTTPS_PORT=8492
export ORO_IDENTITY_PORT=8192
# Nothing here starts the mock, and compose still reads the variable.
export ORO_MOCK_PORT=4092
# Invented, used by nothing outside this run, and removed with the volumes when
# it exits. Rule 13: nothing here resembles a credential anybody holds.
export ORO_DB_PASSWORD="throwaway-$$"
export ORO_IDENTITY_DB_PASSWORD="throwaway-identity-$$"
# compose.yaml includes compose.api.yaml, which interpolates this whether or
# not the members API is one of the services this suite starts.
export ORO_API_DB_PASSWORD="throwawayapi$$"
# Exactly 32 bytes, which is what the service requires and all it requires.
export ORO_IDENTITY_MASTERKEY="throwaway-master-key-0123456789a"
export ORO_IDENTITY_ADMIN_USERNAME="fixture-admin"
export ORO_IDENTITY_ADMIN_PASSWORD="Fixture-Handover-1!"

# Invented people. Rule 13, and the .invalid suffix cannot be registered by
# anybody. The third has one word where a name goes, because plenty of people
# have one and a command that splits a name in two has to survive it.
ONE="Wren Kestrel <wren@example.invalid>"
TWO="Ida Bramble <ida@example.invalid>"
THREE="Solder <solder@example.invalid>"
FOUR="Fourth Person <fourth@example.invalid>"
export ORO_BOOTSTRAP_PEOPLE="$ONE
$TWO
$THREE"

WORK="$(mktemp -d)"
FAILURES=0

compose() { docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" \
                           -f "$ROOT/compose.development.yaml" "$@"; }

cleanup() { compose down --volumes >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT

# The command reaches the database the way make psql does, through the psql
# inside the container, because compose.yaml publishes no port for it. This is
# that command pointed at the throwaway project above.
export ORO_PSQL="docker compose -p $PROJECT -f $ROOT/compose.yaml exec -T db psql -U postgres -d oro"

case_header() { echo; echo "== $1"; }

must_say() {  # must_say FILE "text that has to appear"
  if grep -qF "$2" "$1"; then
    echo "  ok    $2"
  else
    echo "  FAIL  never said: $2" >&2
    FAILURES=$((FAILURES + 1))
  fi
}

must_not_say() {  # must_not_say FILE "text that must not appear"
  if grep -qF "$2" "$1"; then
    echo "  FAIL  said: $2" >&2
    FAILURES=$((FAILURES + 1))
  else
    echo "  ok    never said: $2"
  fi
}

fingerprint() {  # everything the command could have written, in one string
  echo "SELECT coalesce(md5(string_agg(row, '|' ORDER BY row)), 'nothing') FROM (
          SELECT m.email || m.name || coalesce(m.identity_subject, '') AS row
            FROM members m
          UNION ALL
          SELECT r.member_id::text || r.role_id || r.granted_at::text
                 || coalesce(r.approval_id::text, 'none')
                 || coalesce(r.revoked_at::text, 'live')
            FROM member_roles r) AS everything;" \
    | $ORO_PSQL -tAq -v ON_ERROR_STOP=1
}

seat() {  # seat REPORT TRANSCRIPT [--admin "..."]..., true when the command was happy
  #
  # The report is what a person would redirect into a file, and it is checked on
  # its own so that a password appearing in it fails. REPORT.all is the report
  # and the terminal together, which is what a person actually reads, and it is
  # where a refusal is looked for: refusals go to the error stream.
  report="$1"; transcript="$2"; shift 2
  status=0
  python3 "$TESTS/on_a_terminal.py" "$transcript" "$report" \
    "$ROOT/tools/bootstrap/seat_admins.py" "$@" || status=$?
  cat "$report" "$transcript" > "$report.all"
  return "$status"
}

echo "Bringing up the database and the identity service on port $ORO_IDENTITY_PORT"
compose up --detach --wait --wait-timeout 300 db identity >/dev/null || {
  echo "The stack did not come up, so nothing was checked." >&2
  compose logs identity 2>&1 | tail -30 >&2
  exit 1
}

# The stack's own database is empty by design, which is what make up says and
# means. The schema has to be applied before anything can be seated into it.
for f in "$ROOT"/db/migrations/*.sql "$ROOT"/db/seed/*.sql; do
  $ORO_PSQL -v ON_ERROR_STOP=1 -q < "$f" >/dev/null || {
    echo "$(basename "$f") did not apply, so nothing was checked." >&2
    exit 1
  }
done
echo "the schema and the seed data are applied"

# docker cp writes a tar stream, so it stays in a pipe. Holding it in a shell
# variable first truncates it at the first NUL byte.
TOKEN=$(compose cp identity:/bootstrap/pat - 2>/dev/null | tar -xO || true)
if [ -z "$TOKEN" ]; then
  echo "No bootstrap token, so nothing was checked. The identity service said:" >&2
  compose logs identity 2>&1 | tail -20 >&2
  exit 1
fi
export ORO_IDENTITY_URL="http://$ORO_HOSTNAME:$ORO_IDENTITY_PORT"
export ORO_IDENTITY_TOKEN="$TOKEN"
export ORO_MEMBERS_ORIGIN="http://$ORO_HOSTNAME:$ORO_HTTP_PORT"

# Only check_first_sign_in.py needs this, and it needs the members portal to be
# a registered client before an authorization request means anything.
#
# --no-portal-config, because this stack dies with the suite. Without it the
# file apps/members/identity.json is left naming a service on a port nothing
# answers on any more, and a portal somebody has open on this machine reads it.
python3 "$ROOT/tools/identity/configure.py" \
  --members-origin "$ORO_MEMBERS_ORIGIN" \
  --admin-origin "http://$ORO_HOSTNAME:8093" \
  --door-origin "http://$ORO_HOSTNAME:8094" --no-portal-config >/dev/null || {
  echo "The identity service could not be configured, so nothing was checked." >&2
  exit 1
}
echo "the members portal is registered"

case_header "Three people, none of whom is on either system yet"
if seat "$WORK/first.out" "$WORK/first.tty" \
     --admin "$ONE" --admin "$TWO" --admin "$THREE"; then
  cat "$WORK/first.out"
  must_say "$WORK/first.out" "wren@example.invalid"
  must_say "$WORK/first.out" "identity account   created"
  must_say "$WORK/first.out" "member row         created"
  must_say "$WORK/first.out" "admin role         granted"
  must_say "$WORK/first.out" "3 of 3 bootstrap admin grants are used"
  must_say "$WORK/first.out" "The two approver rule is armed"
else
  echo "  FAIL  the command did not seat three people" >&2
  cat "$WORK/first.out" "$WORK/first.tty" >&2
  FAILURES=$((FAILURES + 1))
fi

# Rule 13. The report is the thing a person redirects into a file to keep, and a
# password in it is a password that outlives the handover.
case_header "The handover passwords, which the report must not carry"
must_say "$WORK/first.tty" "first sign in password:"
must_not_say "$WORK/first.out" "first sign in password:"

case_header "What the two systems now hold"
# The passwords are read back out of the terminal the first run wrote them to,
# because nothing else in this repository has them and nothing should.
export ORO_BOOTSTRAP_TRANSCRIPT="$WORK/first.tty"
python3 "$TESTS/check_seats.py" || FAILURES=$((FAILURES + 1))

BEFORE="$(fingerprint)"
case_header "The same three people again, which must change nothing"
if seat "$WORK/second.out" "$WORK/second.tty" \
     --admin "$ONE" --admin "$TWO" --admin "$THREE"; then
  cat "$WORK/second.out"
  must_say "$WORK/second.out" "identity account   already there"
  must_say "$WORK/second.out" "member row         already there"
  must_say "$WORK/second.out" "admin role         already held"
  must_say "$WORK/second.out" "Nothing changed."
  # A second handover password would mean the command had reset somebody's
  # password, and the person may already have chosen their own by then.
  must_not_say "$WORK/second.tty" "first sign in password:"
else
  echo "  FAIL  the second run was not happy" >&2
  cat "$WORK/second.out" "$WORK/second.tty" >&2
  FAILURES=$((FAILURES + 1))
fi
AFTER="$(fingerprint)"
if [ "$BEFORE" = "$AFTER" ]; then
  echo "  ok    the database is byte for byte what it was"
else
  echo "  FAIL  the second run changed the database" >&2
  FAILURES=$((FAILURES + 1))
fi

case_header "A fourth admin, which the database refuses"
if seat "$WORK/fourth.out" "$WORK/fourth.tty" --admin "$FOUR"; then
  echo "  FAIL  a fourth admin was seated, so the escape is not a quota" >&2
  cat "$WORK/fourth.out" >&2
  FAILURES=$((FAILURES + 1))
else
  cat "$WORK/fourth.out.all"
  # The database's own words, out of db/migrations/013_bootstrap_three_admins.sql.
  must_say "$WORK/fourth.out.all" "Granting admin needs an approval from a second admin."
  must_say "$WORK/fourth.out.all" "3 of 3 bootstrap admin grants are used"
  must_say "$WORK/fourth.out.all" "fourth@example.invalid"
fi

# The refusal has to come from the database rather than from a count in the
# command. A copy of the rule in the command would pass the case above while
# proving nothing, and would go on passing after the database rule changed.
case_header "The command carries no copy of the rule it was refused by"
if grep -rn "approval from a second admin" "$ROOT/tools/bootstrap"/*.py; then
  echo "  FAIL  the command holds its own copy of the two approver rule" >&2
  FAILURES=$((FAILURES + 1))
else
  echo "  ok    nothing in the command knows what the rule says"
fi

case_header "A refused seat writes nothing to the database"
LEFT="$(echo "SELECT count(*) FROM members WHERE email = 'fourth@example.invalid';" \
        | $ORO_PSQL -tAq -v ON_ERROR_STOP=1)"
if [ "$LEFT" = "0" ]; then
  echo "  ok    no member row was left behind for the fourth"
else
  echo "  FAIL  the fourth left $LEFT member row(s) behind" >&2
  FAILURES=$((FAILURES + 1))
fi

case_header "A name is required, and it is refused before anything is created"
if seat "$WORK/nameless.out" "$WORK/nameless.tty" --admin "nameless@example.invalid"; then
  echo "  FAIL  an address with no name was accepted" >&2
  FAILURES=$((FAILURES + 1))
else
  cat "$WORK/nameless.out.all"
  must_say "$WORK/nameless.out.all" "needs a name as well as an address"
fi
NAMELESS="$(echo "SELECT count(*) FROM members WHERE email = 'nameless@example.invalid';" \
            | $ORO_PSQL -tAq -v ON_ERROR_STOP=1)"
if [ "$NAMELESS" = "0" ]; then
  echo "  ok    nothing was created before the refusal"
else
  echo "  FAIL  a member row exists for an argument that was refused" >&2
  FAILURES=$((FAILURES + 1))
fi

case_header "With no terminal to hand a password over on, nothing is created"
if "$ROOT/tools/bootstrap/seat_admins.py" --admin "No Terminal <none@example.invalid>" \
     > "$WORK/noterminal.out" 2>&1 < /dev/null; then
  echo "  FAIL  it ran with nowhere to print a handover password" >&2
  FAILURES=$((FAILURES + 1))
else
  cat "$WORK/noterminal.out"
  must_say "$WORK/noterminal.out" "no terminal"
fi

case_header "One admin, all the way through the screens a member uses"
python3 "$TESTS/check_first_sign_in.py" || FAILURES=$((FAILURES + 1))

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "$FAILURES check(s) failed" >&2
  exit 1
fi
echo "three admins are seated, the fourth was refused by the database, and the"
echo "two approver rule is armed"
