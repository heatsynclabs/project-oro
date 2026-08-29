#!/bin/sh
# Run every test the door service has.
#
#   services/door/tests/run.sh
#
# Needs python3 and nothing else. Exit code is the number of files that failed.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"

failed=0
for file in test_domain.py test_wire.py test_device.py \
            test_device_privileged_mode.py test_socket_transport.py \
            test_conformance_fake.py; do
  printf '%-32s ' "$file"
  if output="$(python3 "$HERE/$file" 2>&1)"; then
    echo "$output" | tail -n 1
  else
    echo
    echo "$output"
    failed=$((failed + 1))
  fi
done

if [ "$failed" -eq 0 ]; then
  echo
  echo "every door test passed"
else
  echo
  echo "$failed test file(s) failed"
fi
exit "$failed"
