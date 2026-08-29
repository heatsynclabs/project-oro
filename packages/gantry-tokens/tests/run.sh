#!/bin/sh
# Run every check the token layer has.
#
#   packages/gantry-tokens/tests/run.sh
#
# Needs python3 and nothing else. Exit code is the number of steps that failed.

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VALIDATOR="$ROOT/validator"

failed=0
for file in test_contrast.py test_cascade.py test_check_contrast.py test_grounds.py; do
  printf '%-24s ' "$file"
  if output="$(python3 "$VALIDATOR/$file" 2>&1)"; then
    echo "$output" | tail -n 1
  else
    echo
    echo "$output"
    failed=$((failed + 1))
  fi
done

# The suite above proves the checker works. This runs it for real, over the
# token layer this package ships, which is the thing CI is actually protecting.
printf '%-24s ' "the token layer"
if output="$(python3 "$VALIDATOR/check_contrast.py" 2>&1)"; then
  echo "$output" | tail -n 1
else
  echo
  echo "$output"
  failed=$((failed + 1))
fi

if [ "$failed" -eq 0 ]; then
  echo
  echo "every gantry-tokens check passed"
else
  echo
  echo "$failed check(s) failed"
fi
exit "$failed"
