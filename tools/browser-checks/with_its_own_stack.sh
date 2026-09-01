#!/bin/sh
# The browser checks, against a stack this script brings up and takes down.
#
#   tools/browser-checks/with_its_own_stack.sh
#
# run.sh beside this one drives a stack somebody else started, deliberately, so
# a portal a person is looking at is neither restarted nor disturbed. That is
# the right shape for a laptop and it is the reason those checks were in no
# workflow, and it cost a day: the landing page arrived after the check that
# reads it, the check went red against a portal that was working correctly, and
# nothing was running it often enough to notice.
#
# So this is the shape CI needs. Its own compose project on its own ports, with
# every value supplied here, which is what every other suite in this repository
# does and why two of them can run on one machine at once.
#
# Not in make check, and that is a choice rather than an oversight. This builds
# an image carrying three browsers, and make check already runs thirteen suites
# that start containers. A laptop runs make development once and then run.sh as
# often as it likes, which is cheaper for a person and the same check.
#
# Needs docker. Exit code is 1 if any check failed.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

PROJECT="oro-browser-checks-$$"

# Ports nothing else in this repository uses, so this and any other suite can
# run at the same time. Read out of every other run.sh on 2026-08-31.
export ORO_HOSTNAME=localhost
export ORO_TLS=internal
export ORO_HTTP_PORT=8098
export ORO_HTTPS_PORT=8498
export ORO_IDENTITY_PORT=8198
export ORO_MOCK_PORT=4098
export ORO_MAIL_PORT=8038

# Invented, used by nothing outside this run, and removed with the volumes when
# it exits. Rule 13: nothing here resembles a credential anybody holds.
export ORO_DB_PASSWORD="throwaway-$$"
export ORO_API_DB_PASSWORD="throwawayapi$$"
export ORO_IDENTITY_DB_PASSWORD="throwaway-identity-$$"
# Exactly 32 bytes, which is what the identity service requires and all it
# requires.
export ORO_IDENTITY_MASTERKEY="throwaway-master-key-0123456789a"
export ORO_IDENTITY_ADMIN_USERNAME="fixture-admin"
export ORO_IDENTITY_ADMIN_PASSWORD="Fixture-Handover-1!"
# The catcher on the compose network, which is the value a laptop uses. Nothing
# here registers anybody, and compose reads the variable either way.
export ORO_MAIL_HOST="mail:1025"

compose() { docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" \
                           -f "$ORO_OVERRIDE" "$@"; }
ORO_OVERRIDE="$ROOT/compose.development.yaml"

cleanup() { compose down --volumes >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Bringing up the development stack on port $ORO_HTTP_PORT"
# The same 300 seconds make development allows, and for the same reason: the
# identity service applies its own schema and seeds an instance before it
# answers anything.
compose up --detach --wait --wait-timeout 300 >/dev/null || {
  echo "The stack did not come up, so nothing was checked." >&2
  compose logs 2>&1 | tail -40 >&2
  exit 1
}
echo

# The portal has no client id on a stack nobody configured, which is the state
# a signed out arrival is checked in. check_first_view.py asserts the landing
# and no view, and neither depends on a registered client.
ORO_PORTAL_URL="http://localhost:$ORO_HTTP_PORT" \
ORO_SHOT_DIR="${ORO_SHOT_DIR:-$HOME/oro-screenshots}" \
  "$ROOT/tools/browser-checks/run.sh"
