#!/bin/sh
# The generated half of ATTRIBUTIONS.md, which rule 9 of CLAUDE.md asks for.
#
#   tools/attributions/run.sh            rewrite the region between the markers
#   tools/attributions/run.sh --check    print what would change, write nothing
#
# For each lockfile it builds the image that lock installs into and reads every
# installed package's own metadata out of it, so the licence in each row comes
# from the package rather than from an index summary or from somebody's memory.
# Everything outside the two marker comments in that file is hand written and is
# not touched.
#
# Needs docker, python3 and the network, because building an image installs from
# PyPI. So do the members API suite and the import boundary gate, so that is not
# what keeps this out of make check. What keeps it out is that it rewrites a
# tracked file, and that --check compares the date the metadata was read, which
# moves on its own. Run it when a lockfile changes, in the same sitting that
# recompiles the lock. ADR 0012 carries the reasoning.
#
# Exit code is 1 if the generator refused, or if --check found a difference.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# The generator's own suite first, because a generator that has only ever been
# run on the two correct locks in this repository proves nothing. Each check
# plants one defect in a throwaway lock and requires it to be reported.
python3 "$ROOT/tools/attributions/test_attributions.py"
echo

# And that SOURCES names every lockfile git tracks. That list was two entries
# long while three locks existed, and this reported the page correct over a
# whole image it had never read.
python3 "$ROOT/tools/attributions/test_sources.py"
echo

python3 "$ROOT/tools/attributions/generate.py" "$@"
