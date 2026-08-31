#!/bin/sh
# The members portal, driven by a real browser.
#
#   tools/browser-checks/run.sh
#
# Everything else in this repository that looks at the portal reads the document
# Caddy serves. This opens it in chromium, lets the page's own script run, and
# checks what a person would see. It also writes a screenshot, because a red
# browser check with no picture sends the reader back to reproduce it by hand.
#
# It checks a stack that is already up. It starts nothing and stops nothing, so
# a portal somebody is looking at is neither disturbed nor restarted:
#
#   make development                  # the stack, if it is not already running
#   ./tools/browser-checks/run.sh
#
#   ORO_PORTAL_URL   default http://localhost:8080. A laptop serves plain HTTP
#                    on ORO_HTTP_PORT, so this carries the port your own .env
#                    chose.
#   ORO_SHOT_DIR     where the screenshots land. Default $HOME/oro-screenshots,
#                    and never inside this repository: every suite here leaves
#                    the working tree as it found it, and the prose and ceiling
#                    gates read git ls-files, so a stray file in the tree is one
#                    git add away from being linted as source.
#
# There is no published image with both a browser and the driver in it, so this
# builds one from tools/browser-checks/Dockerfile over the base image Microsoft
# publishes for the purpose. docs/decisions/0015-a-browser-driver.md says what
# was priced against it.
#
# Needs docker. Exit code is 1 if any check failed.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/tools/browser-checks"

# Tagged with the driver version in requirements.in, so a bump to that file
# builds a new image rather than reusing the old one under the same name.
IMAGE="oro-browser-checks:1.62.0"

URL="${ORO_PORTAL_URL:-http://localhost:8080}"

SHOT_DIR="${ORO_SHOT_DIR:-$HOME/oro-screenshots}"
case "$SHOT_DIR" in /*) ;; *) SHOT_DIR="$PWD/$SHOT_DIR" ;; esac
case "$SHOT_DIR" in
  "$ROOT"|"$ROOT"/*)
    echo "run.sh: $SHOT_DIR is inside $ROOT, and no screenshot is written there." >&2
    echo "Every suite here leaves the working tree as it found it. Set" >&2
    echo "ORO_SHOT_DIR to a path outside it, or leave it unset for" >&2
    echo "\$HOME/oro-screenshots." >&2
    exit 1 ;;
esac
mkdir -p "$SHOT_DIR"

# Say what is about to be checked before checking it. A run that ends on a
# connection refused should name the address it was refused from.
echo "Driving $URL with chromium. Screenshots land in $SHOT_DIR"
echo

docker build --quiet --tag "$IMAGE" "$HERE" >/dev/null

# --add-host, because the browser runs in a container and the portal runs on the
# machine that started it. The rule that gets a request all the way to Caddy
# with the right Host header on it is in harness.py, which has the measurement.
#
# --shm-size, because chromium puts its renderer shared memory on /dev/shm and
# Docker's default there is 64MB. The same reasoning sets shm_size on the
# database service in compose.yaml.
#
# --user, so the screenshot belongs to the person who asked for it rather than
# to root. The checks are mounted read only; the screenshot directory is the one
# writable thing in the container.
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  --shm-size=1gb \
  --user "$(id -u):$(id -g)" \
  -v "$HERE:/io:ro" \
  -v "$SHOT_DIR:/shots" \
  -e ORO_PORTAL_URL="$URL" \
  -e ORO_SHOT_DIR="$SHOT_DIR" \
  -w /io "$IMAGE" \
  python3 check_first_view.py
