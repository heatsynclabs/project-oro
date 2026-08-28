#!/bin/sh
# Bring up the development stack, prove the members portal against it, take it
# down.
#
#   tools/members-portal/tests/run.sh
#
# Needs docker, curl and python3. Runs as its own compose project on its own
# ports and supplies its own values for everything compose reads, so a stack
# somebody is already running is neither read nor touched, and no .env has to
# exist. Leaves nothing behind. Exit code is 1 if any check failed.
#
# To check a stack you already have up instead, skip this script:
#
#   ORO_PORTAL_URL=http://localhost:8080 python3 tools/members-portal/tests/check_portal.py
#
# The development profile serves plain HTTP on the port in ORO_HTTP_PORT, so
# that URL carries the port your own .env set.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

# The mock image pin lives in tools/mock/image.sh and only there.
. "$ROOT/tools/mock/image.sh"
export ORO_MOCK_IMAGE ORO_MOCK_PLATFORM ORO_MOCK_DOCUMENT

PROJECT="oro-portal-test-$$"
export ORO_HOSTNAME=localhost
export ORO_TLS=internal
export ORO_HTTP_PORT=8082
# Required by compose.yaml, and nothing listens on it here: the development
# profile serves plain HTTP and opens no TLS listener at all.
export ORO_HTTPS_PORT=8445
# Invented, used by nothing, and removed with the volume when this exits.
export ORO_DB_PASSWORD="throwaway-$$"

compose() { docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" "$@"; }

# The wildcard reaches services in a profile. A plain down does not, and leaves
# the mock running with the network still in use.
cleanup() { COMPOSE_PROFILES='*' compose down --volumes >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Bringing up the development stack on port $ORO_HTTP_PORT"
COMPOSE_PROFILES=development compose up --detach --wait --wait-timeout 180 >/dev/null || {
  echo "The stack did not come up, so nothing was checked. The error above says why." >&2
  exit 1
}
echo

# The project name goes with the URL, because one check reads the logs of this
# stack to prove the command the page sends a reader to reaches the mock.
ORO_PORTAL_URL="http://$ORO_HOSTNAME:$ORO_HTTP_PORT" ORO_PORTAL_PROJECT="$PROJECT" \
  python3 "$ROOT/tools/members-portal/tests/check_portal.py"
