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

PROJECT="oro-portal-test-$$"
export ORO_HOSTNAME=localhost
export ORO_TLS=internal
export ORO_HTTP_PORT=8082
# Required by compose.yaml, and nothing listens on it here: the development
# profile serves plain HTTP and opens no TLS listener at all.
export ORO_HTTPS_PORT=8445
# Invented, used by nothing, and removed with the volume when this exits.
export ORO_DB_PASSWORD="throwaway-$$"

# Two shapes: the deployment alone, and the deployment plus what a laptop adds.
compose()     { docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" "$@"; }
compose_dev() { compose -f "$ROOT/compose.development.yaml" "$@"; }

# Down through the override, so this reaches the mock as well.
cleanup() { compose_dev down --volumes >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Bringing up the development stack on port $ORO_HTTP_PORT"
compose_dev up --detach --wait --wait-timeout 180 >/dev/null || {
  echo "The stack did not come up, so nothing was checked. The error above says why." >&2
  exit 1
}
echo

# The project name goes with the URL, because one check reads the logs of this
# stack to prove the command the page sends a reader to reaches the mock.
ORO_PORTAL_URL="http://$ORO_HOSTNAME:$ORO_HTTP_PORT" ORO_PORTAL_PROJECT="$PROJECT" \
  python3 "$ROOT/tools/members-portal/tests/check_portal.py"
