#!/bin/sh
# The layer arrows in rule 5 of CLAUDE.md, over the Python in services/.
#
#   tools/import-boundaries/run.sh
#
# import-linter reads a real import graph, so the module that crosses a line
# does not have to be the one anybody opened. contracts.ini holds the contracts,
# the reason for each, and how wide that graph reaches.
#
# There is no published import-linter image, so this builds the one it needs
# from tools/import-boundaries/Dockerfile. The base image is pinned by digest
# and the packages are pinned with hashes, and after the first build docker has
# it cached and this costs a second.
# docs/decisions/0011-import-linter-arrives.md says what was priced against it.
#
# Needs docker and python3. Exit code is 1 if any contract is broken.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/tools/import-boundaries"

# Tagged with the import-linter version in requirements.in, so a bump to that
# file builds a new image rather than reusing the old one under the same name.
IMAGE="oro-import-boundaries:2.14"

docker build --quiet --tag "$IMAGE" "$HERE" >/dev/null

# The gate's own suite first, because a gate that has only ever been green
# proves nothing. It plants one import in a throwaway tree at a time, including
# two that cross a line one import deep, and requires each to be reported.
python3 "$HERE/test_import_boundaries.py" "$IMAGE"
echo

# Then the width of the graph, over the real tree. import-linter follows nothing
# outside the packages contracts.ini declares, so a module outside all of them is
# a hole a chain can pass through unreported. This refuses one. The two
# directories are the same two the docker run below puts on PYTHONPATH.
python3 "$HERE/check_root_packages.py" "$HERE/contracts.ini" \
  "$ROOT/services" "$ROOT/services/api"
echo

# Read only, so a run cannot leave anything in the working tree. --no-cache for
# the same reason: import-linter otherwise writes .import_linter_cache at the
# working directory, which is the repository root, measured on 2026-08-29 with a
# writable mount. With the mount read only and the cache left on it stops on
# "Read-only file system (os error 30)".
#
# Both parents on PYTHONPATH, because the two packages sit at different depths:
# services/door is the package `door`, and services/api/app is the package
# `app`. contracts.ini says more about that.
docker run --rm -v "$ROOT:/io:ro" -w /io \
  -e PYTHONPATH=/io/services:/io/services/api "$IMAGE" \
  lint-imports --config tools/import-boundaries/contracts.ini --no-cache --no-logo || {
  echo "" >&2
  echo "Rule 5 of CLAUDE.md. The arrows point one way, and the message above" >&2
  echo "names the import that went the other way. tools/import-boundaries/contracts.ini" >&2
  echo "carries the reason for the contract that broke." >&2
  exit 1
}
