#!/bin/sh
# Every name a Python module uses has to exist.
#
#   tools/names/run.sh
#
# This gate exists because of one bug it would have caught. clients.py was split
# out of configure.py and took a use of _GENERATED_INSTEAD with it, leaving the
# definition behind. The branch that reads it runs only against an instance an
# older version of the tool configured, which is the deployment case and the one
# no suite reaches, so `make identity-configure` died on a NameError on the one
# machine that mattered and was green on every other.
#
# ruff reads this with F821, out of pyflakes. The same pinned image the ceilings
# gate uses, with --isolated so ruff.toml does not apply: that file says in its
# own first line that it holds rule 6's numbers and nothing else, and it should
# go on being true.
#
# Not import-linter. That reads services/ and answers a different question,
# which is whether an import points the wrong way. This one is whether a name
# resolves at all, and the file it caught is in tools/.
#
# Needs docker and python3. Exit code is 1 if a name does not resolve.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# The same digest tools/ceilings/run.sh pins, for the same reasons, and it is
# already in the local cache by the time this runs.
RUFF="ghcr.io/astral-sh/ruff:0.16.5@sha256:8355b79edf35788aef97ac9b1ff3b758604a5d67963ead617c45c72e1d92871f"

# F821  a name that is used and never defined
# F811  a name defined twice, where the second definition silently wins
# F822  a name exported through __all__ that the module does not have
NAMES="F821,F811,F822"

# The gate's own suite first, because a gate that has only ever been green
# proves nothing. Each check plants one broken name in a throwaway tree and
# requires this to report it and exit 1.
python3 "$ROOT/tools/names/test_names.py" "$RUFF" "$NAMES"
echo

docker run --rm -v "$ROOT:/io:ro" -w /io "$RUFF" \
  check --no-cache --isolated --select "$NAMES" . || {
  echo "" >&2
  echo "A name above does not resolve. Nothing runs the line that reads it," >&2
  echo "or the suite would be red, so the machine that finds this is a" >&2
  echo "deployment. Rules 3 and 7 of CLAUDE.md." >&2
  exit 1
}
