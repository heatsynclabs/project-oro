#!/bin/sh
# Start the mock, prove it serves the contract, take it down.
#
#   tools/mock/tests/run.sh
#
# Needs docker and python3. Leaves nothing behind. Exit code is 1 if any check
# failed.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
# Its own project and its own port, so a mock left running by make development
# neither collides with this nor gets taken down by it. The image and its digest
# live in compose.development.yaml and nowhere else, so this starts the same
# container a laptop does rather than a second copy of the pin.
PROJECT="oro-mock-test-$$"
PORT=4019
export ORO_MOCK_PORT="$PORT"
# compose.yaml interpolates the whole file, so these have to be set even though
# nothing here starts the database or Caddy. Invented, and removed on exit.
export ORO_HOSTNAME=localhost ORO_TLS=internal
export ORO_HTTP_PORT=8083 ORO_HTTPS_PORT=8446 ORO_IDENTITY_PORT=8187
export ORO_DB_PASSWORD="throwaway-$$"
export ORO_IDENTITY_DB_PASSWORD="throwaway-identity-$$"
export ORO_IDENTITY_MASTERKEY="throwaway-master-key-0123456789a"
export ORO_IDENTITY_ADMIN_USERNAME="fixture-admin"
export ORO_IDENTITY_ADMIN_PASSWORD="Fixture-Handover-1!"

compose() { docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" \
                           -f "$ROOT/compose.development.yaml" "$@"; }

cleanup() { compose down --volumes >/dev/null 2>&1 || true; }
trap cleanup EXIT

compose up --detach --wait --wait-timeout 180 mock >/dev/null || {
  echo "The mock did not come up, so nothing was checked." >&2
  compose logs mock 2>&1 | tail -20 >&2
  exit 1
}

# Parsing the document takes a couple of seconds, and longer under the
# emulation an arm64 host runs this image with. Poll rather than sleep, because
# a fixed sleep is either slow or flaky and eventually both.
printf 'waiting for the mock'
i=0
until curl -fs -o /dev/null "http://127.0.0.1:$PORT/me" -H 'Authorization: Bearer wait'; do
  i=$((i+1))
  if [ "$i" -gt 90 ]; then
    echo " timed out"
    echo "The mock did not answer within 90 seconds, so nothing was checked."
    echo "Its log follows, and it is still running until this script exits."
    compose logs mock 2>&1 | tail -20
    exit 1
  fi
  printf '.'
  sleep 1
done
echo " ready"
echo

ORO_MOCK_URL="http://127.0.0.1:$PORT" python3 "$ROOT/tools/mock/tests/check_contract.py"
