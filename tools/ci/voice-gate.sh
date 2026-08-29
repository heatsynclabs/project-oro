#!/bin/sh
# Run the prose gate over the files a change touched.
#
#   tools/ci/voice-gate.sh                 every tracked file
#   tools/ci/voice-gate.sh origin/main     only what differs from that ref
#
# Two modes because a pull request should be judged on what it changed, while a
# push to the trunk has nothing to compare against and is worth checking whole.
# Exit code is the gate's own: nonzero when it found an error.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GATE="$ROOT/tools/voice-check/voice_check.py"
BASE="$1"

if [ -n "$BASE" ]; then
  if ! git -C "$ROOT" rev-parse --verify --quiet "$BASE" >/dev/null; then
    echo "voice-gate: cannot resolve base ref '$BASE'." >&2
    echo "Fetch it, or run with no argument to check every tracked file." >&2
    exit 1
  fi
  FILES=$(git -C "$ROOT" diff --name-only --diff-filter=ACM "$BASE"...HEAD)
else
  FILES=$(git -C "$ROOT" ls-files)
fi

# Naming a file tells the gate to check it whatever its suffix, so the filter has
# to happen here. The list is read out of the gate rather than written twice: a
# copy of it drifted the first time this script ran, and every shell script went
# unchecked while the output still said clean.
PATTERN=$(cd "$ROOT/tools/voice-check" && python3 -c 'from voice_check import CHECKED_SUFFIXES; print("(" + "|".join(sorted(s[1:] for s in CHECKED_SUFFIXES)) + ")$")')

FILES=$(printf '%s\n' "$FILES" | grep -E "\.$PATTERN" || true)

if [ -z "$FILES" ]; then
  echo "voice-gate: no prose or code files changed."
  exit 0
fi

cd "$ROOT"
# A deleted or renamed path would make the gate report a missing file rather
# than a violation, and a missing file is not a finding. Pass only what is there.
EXISTING=""
for f in $FILES; do
  [ -f "$f" ] && EXISTING="$EXISTING $f"
done
[ -z "$EXISTING" ] && { echo "voice-gate: nothing to check."; exit 0; }

# shellcheck disable=SC2086
exec python3 "$GATE" $EXISTING
