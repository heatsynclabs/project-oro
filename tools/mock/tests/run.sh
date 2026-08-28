#!/bin/sh
# Start the mock, prove it serves the contract, take it down.
#
#   tools/mock/tests/run.sh
#
# Needs docker and python3. Leaves nothing behind. Exit code is 1 if any check
# failed.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
. "$ROOT/tools/mock/image.sh"

# Its own port and its own container name, so a mock somebody left running from
# make mock does not collide with this and does not get killed by it.
PORT=4019
NAME="oro-mock-test-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --rm --name "$NAME" \
  --platform "$ORO_MOCK_PLATFORM" \
  -p "127.0.0.1:$PORT:4010" \
  -v "$ROOT/docs/api:/spec:ro" \
  "$ORO_MOCK_IMAGE" \
  mock --host 0.0.0.0 --port 4010 --multiprocess false "/spec/$ORO_MOCK_DOCUMENT" >/dev/null

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
    echo "docker logs $NAME says what it printed, and it is still running until"
    echo "this script exits."
    docker logs "$NAME" 2>&1 | tail -20
    exit 1
  fi
  printf '.'
  sleep 1
done
echo " ready"
echo

ORO_MOCK_URL="http://127.0.0.1:$PORT" python3 "$ROOT/tools/mock/tests/check_contract.py"
