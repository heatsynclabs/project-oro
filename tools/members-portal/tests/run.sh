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
#   ORO_PORTAL_URL=http://localhost:8080 ORO_MOCK_URL=http://localhost:4010 \
#     python3 tools/members-portal/tests/check_portal.py
#
# A laptop serves plain HTTP on the port in ORO_HTTP_PORT, so that URL carries
# the port your own .env set, and ORO_MOCK_PORT is the second one. The contract
# mock is reached on its own port rather than through /v1, which the members API
# took on 2026-08-30.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

PROJECT="oro-portal-test-$$"
export ORO_HOSTNAME=localhost
export ORO_TLS=internal
export ORO_HTTP_PORT=8082
# Required by compose.yaml, and nothing listens on it here: a laptop serves
# plain HTTP and opens no TLS listener at all.
export ORO_HTTPS_PORT=8445
export ORO_IDENTITY_PORT=8186
# Its own, because the default is shared and a stack started by make development
# is already holding it.
export ORO_MOCK_PORT=4012
export ORO_MAIL_PORT=8027
export ORO_MOCK_URL="http://localhost:4012"
# Invented, used by nothing, and removed with the volumes when this exits.
# compose.yaml interpolates the whole file, so the identity values have to be
# set even though this suite never starts that service.
export ORO_DB_PASSWORD="throwaway-$$"
export ORO_IDENTITY_DB_PASSWORD="throwaway-identity-$$"
# compose.yaml includes compose.api.yaml, which interpolates this whether or
# not the members API is one of the services this suite starts.
export ORO_API_DB_PASSWORD="throwawayapi$$"
export ORO_IDENTITY_MASTERKEY="throwaway-master-key-0123456789a"
export ORO_IDENTITY_ADMIN_USERNAME="fixture-admin"
export ORO_IDENTITY_ADMIN_PASSWORD="Fixture-Handover-1!"

# Two shapes: the deployment alone, and the deployment plus what a laptop adds.
compose()     { docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" "$@"; }
compose_dev() { compose -f "$ROOT/compose.development.yaml" "$@"; }

# Down through the override, so this reaches the mock as well.
cleanup() { compose_dev down --volumes >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Bringing up the development stack on port $ORO_HTTP_PORT"
# The members API is named because it holds /v1 now, which the portal reads, and
# naming it starts the schema step and the identity service it depends on. That
# is most of what this takes: the identity service seeds an instance on first
# start. Before 2026-08-30 the mock held /v1 and three services were enough.
compose_dev up --detach --wait --wait-timeout 300 db caddy mock api >/dev/null || {
  echo "The stack did not come up, so nothing was checked. The error above says why." >&2
  exit 1
}
echo

# Four suites, all against this one stack. check_portal.py is the page against
# the contract underneath it, check_appearance.py is the page itself,
# check_sign_in.py is what it does about signing in, and check_profile.py is
# what it lets a member change. Split because one file holding them runs past
# the 300 line ceiling in rule 6.
#
# set -e is on, so run each without letting a red one stop the others: a reader
# who broke two wants to see both.
set +e
FAILED=0
for SUITE in check_portal check_appearance check_sign_in check_profile; do
  ORO_PORTAL_URL="http://$ORO_HOSTNAME:$ORO_HTTP_PORT" ORO_PORTAL_PROJECT="$PROJECT" \
    ORO_MOCK_URL="$ORO_MOCK_URL" \
    python3 "$ROOT/tools/members-portal/tests/$SUITE.py" || FAILED=1
  echo
done
exit "$FAILED"
