#!/bin/sh
# The file and function ceilings in rule 6 of CLAUDE.md, all five of them.
#
#   tools/ceilings/run.sh
#
# Two tools, because no single one measures all five, which is the finding
# docs/decisions/0005-file-and-function-ceilings.md records.
#
#   ruff        cyclomatic complexity, parameter count, nesting depth
#   this repo   a source file over 300 lines, a function over 50
#
# Needs docker and python3. Exit code is 1 if anything is over a ceiling.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Pinned by digest as well as by tag. ruff 0.16.5, released 2026-08-27, digest
# read from ghcr.io on 2026-08-28. That digest is the image index and carries
# linux/amd64 and linux/arm64, so a laptop and a runner both get a native image.
#
# The container rather than a pip install, because every other tool this
# repository runs arrives the same way and a volunteer already needs docker for
# the database suite. Nothing is installed on the machine running this.
RUFF="ghcr.io/astral-sh/ruff:0.16.5@sha256:8355b79edf35788aef97ac9b1ff3b758604a5d67963ead617c45c72e1d92871f"

# Read only, and --no-cache, so this cannot leave a cache directory in the
# working tree owned by a user nobody expected.
docker run --rm -v "$ROOT:/io:ro" -w /io "$RUFF" \
  check --no-cache --config ruff.toml . || {
  echo "" >&2
  echo "Rule 6 of CLAUDE.md. A function past one of these ceilings is two" >&2
  echo "functions. ruff.toml holds the numbers and nothing else." >&2
  exit 1
}

# The checker's own suite first, because a gate that has only ever been green
# proves nothing. Each of these puts one violation in a throwaway repository and
# asserts the checker reports it and exits 1.
python3 "$ROOT/tools/ceilings/test_ceilings.py"
echo

python3 "$ROOT/tools/ceilings/check_ceilings.py"
