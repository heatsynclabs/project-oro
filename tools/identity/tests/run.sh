#!/bin/sh
# Bring up the identity service, prove it can hold the lab's existing
# passwords, take it down.
#
#   tools/identity/tests/run.sh
#
# Needs docker and python3. Runs as its own compose project on its own ports and
# supplies its own values for everything compose reads, so a stack somebody is
# already running is neither read nor touched, and no .env has to exist. Leaves
# nothing behind. Exit code is 1 if any check failed.
#
# Two suites. check_identity.py is part (a) of the phase 2 password proof:
# hashes the lab already holds, imported and signed in with. check_configuration.py
# is what configure.py registered, and one whole sign in through the hosted
# screens ending in a refresh token that rotates.
#
# Part (b) of the password proof is ten real members signing in to staging with
# the password they already use. It needs the production hashes and volunteers,
# and no script stands in for it.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

PROJECT="oro-identity-test-$$"
export ORO_HOSTNAME=localhost
export ORO_TLS=internal
export ORO_HTTP_PORT=8084
export ORO_HTTPS_PORT=8447
export ORO_IDENTITY_PORT=8184
# Nothing here starts the mock, and compose still reads the variable.
export ORO_MOCK_PORT=4013
# Invented, used by nothing outside this run, and removed with the volumes when
# it exits. Rule 13: nothing here resembles a credential anybody holds.
export ORO_DB_PASSWORD="throwaway-$$"
export ORO_IDENTITY_DB_PASSWORD="throwaway-identity-$$"
# Exactly 32 bytes, which is what the service requires and all it requires.
export ORO_IDENTITY_MASTERKEY="throwaway-master-key-0123456789a"
export ORO_IDENTITY_ADMIN_USERNAME="fixture-admin"
export ORO_IDENTITY_ADMIN_PASSWORD="Fixture-Handover-1!"

compose() { docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" \
                           -f "$ROOT/compose.development.yaml" "$@"; }

cleanup() { compose down --volumes >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Only the two services this needs. Caddy and the mock have nothing to do with
# a password, and starting them would make this suite wait on them.
echo "Bringing up the identity service on port $ORO_IDENTITY_PORT"
compose up --detach --wait --wait-timeout 300 db identity >/dev/null || {
  echo "The identity service did not come up, so nothing was checked." >&2
  compose logs identity 2>&1 | tail -30 >&2
  exit 1
}
echo

# The bootstrap token sits in a named volume, out of the working tree where a
# later git add could reach it. docker cp is the only way to read it: the image
# is distroless and has no shell to run cat in.
#
# docker cp writes a tar stream, so it stays in a pipe. Holding it in a shell
# variable first looks tidier and silently truncates it at the first NUL byte,
# which is how an earlier version of this file reported a healthy service as
# having no token at all.
#
# Its own error goes to a file rather than to /dev/null, because a failed copy
# and a file that was never written are different faults and the reader is
# entitled to know which one happened.
COPY_ERROR=$(mktemp)
TOKEN=$(compose cp identity:/bootstrap/pat - 2>"$COPY_ERROR" | tar -xO 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  echo "No bootstrap token, so nothing was checked. docker said:" >&2
  cat "$COPY_ERROR" >&2
  rm -f "$COPY_ERROR"
  echo "" >&2
  echo "That file is written once, by the first setup, and only when the" >&2
  echo "identity database is new. This suite starts a throwaway stack every" >&2
  echo "time, so nothing here should ever have run a setup before. The last" >&2
  echo "twenty lines of the service's own log:" >&2
  compose logs identity 2>&1 | tail -20 >&2
  exit 1
fi
rm -f "$COPY_ERROR"

export ORO_IDENTITY_URL="http://$ORO_HOSTNAME:$ORO_IDENTITY_PORT"
export ORO_IDENTITY_TOKEN="$TOKEN"
# The origin a member's browser would be on. Nothing is listening there during
# this run and nothing needs to be: what is checked is that the identity
# service sends a browser back to it carrying a code.
export ORO_MEMBERS_ORIGIN="http://$ORO_HOSTNAME:8080"

echo "Registering the project, the clients and the branding"
python3 "$ROOT/tools/identity/configure.py" \
  --members-origin "$ORO_MEMBERS_ORIGIN" \
  --admin-origin "http://$ORO_HOSTNAME:8081" \
  --door-origin "http://$ORO_HOSTNAME:8082" >/dev/null || {
  echo "The configuration step failed, so nothing was checked." >&2
  python3 "$ROOT/tools/identity/configure.py" \
    --members-origin "$ORO_MEMBERS_ORIGIN" \
    --admin-origin "http://$ORO_HOSTNAME:8081" \
    --door-origin "http://$ORO_HOSTNAME:8082" >&2
  exit 1
}
# Twice, because a configuration step nobody dares re-run is a configuration
# step that stops being run, and this is the only place that would notice.
python3 "$ROOT/tools/identity/configure.py" \
  --members-origin "$ORO_MEMBERS_ORIGIN" \
  --admin-origin "http://$ORO_HOSTNAME:8081" \
  --door-origin "http://$ORO_HOSTNAME:8082" >/dev/null || {
  echo "The configuration step is not idempotent: the second run failed." >&2
  exit 1
}
echo

python3 "$ROOT/tools/identity/tests/check_identity.py" || FAILED=1
echo
python3 "$ROOT/tools/identity/tests/check_configuration.py" || FAILED=1
exit "${FAILED:-0}"
