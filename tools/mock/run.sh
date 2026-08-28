#!/bin/sh
# Serve docs/api/members-v1.yaml as a mock members API.
#
#   tools/mock/run.sh [port]
#
# Needs docker and nothing else. Runs in the foreground; Ctrl-C stops it and
# removes the container. Paths are served without the /v1 prefix, so /me rather
# than /v1/me. ADR 0002 explains that and what the mock does not do.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/tools/mock/image.sh"
PORT="${1:-4010}"

echo "serving docs/api/$ORO_MOCK_DOCUMENT on http://127.0.0.1:$PORT"
echo "try: curl -s -H 'Authorization: Bearer any-string' http://127.0.0.1:$PORT/me"
echo

# --multiprocess false because the default forks the server off the CLI and
# reads cluster.isPrimary on a Node version where it is undefined, so the
# pinned image exits 1 with a TypeError before it serves anything.
#
# Static examples rather than --dynamic. Dynamic generation answers /me with a
# 500 on this document, because json-schema-faker walks the Member reference
# inside Member forever, and where it does answer it invents lorem ipsum and
# properties the schema never declared. Static returns the examples written in
# the document, which is what a portal wants to build against.
exec docker run --rm --name "oro-mock-$PORT" \
  --platform "$ORO_MOCK_PLATFORM" \
  -p "127.0.0.1:$PORT:4010" \
  -v "$ROOT/docs/api:/spec:ro" \
  "$ORO_MOCK_IMAGE" \
  mock --host 0.0.0.0 --port 4010 --multiprocess false "/spec/$ORO_MOCK_DOCUMENT"
