#!/bin/sh
# The citations in the contract review notes land where they say they do.
#
#   tools/citations/run.sh
#
# Twelve self checks over a throwaway pair of files first, then the real
# document. The self checks go first for the same reason they do in the identity
# suite: a fault in the checker should be reported before it is used to judge
# anything.
#
# Needs python3 and nothing else. Exit code is 1 if any check failed.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/tools/citations"

failed=0

printf '%-24s ' "the checker itself"
if output="$(python3 "$HERE/test_citations.py" 2>&1)"; then
  echo "$output" | tail -n 1
else
  echo
  echo "$output"
  failed=$((failed + 1))
fi

echo
if python3 "$HERE/check_citations.py"; then
  :
else
  failed=$((failed + 1))
fi

echo
if [ "$failed" -eq 0 ]; then
  echo "every citation check passed"
else
  echo "$failed citation check(s) failed"
fi
exit "$failed"
