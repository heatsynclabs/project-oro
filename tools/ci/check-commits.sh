#!/bin/sh
# Check every commit message in a range against the gate the commit hook runs.
#
#   tools/ci/check-commits.sh BASE [HEAD]
#
# Rule 1 of CLAUDE.md has a local hook in .githooks/commit-msg, and a local hook
# is advisory: it can be skipped with --no-verify, and it is simply absent on a
# clone where nobody ran the one line that installs it. This is the copy that
# cannot be skipped. Without it the rule is a suggestion.
#
# Exit code is the number of commits that failed.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GATE="$ROOT/tools/voice-check/voice_check.py"
BASE="$1"
TIP="${2:-HEAD}"

if [ -z "$BASE" ]; then
  echo "usage: tools/ci/check-commits.sh BASE [HEAD]" >&2
  exit 2
fi

for ref in "$BASE" "$TIP"; do
  if ! git -C "$ROOT" rev-parse --verify --quiet "$ref" >/dev/null; then
    echo "check-commits: cannot resolve '$ref'. Fetch the full history." >&2
    exit 2
  fi
done

COMMITS=$(git -C "$ROOT" rev-list "$BASE".."$TIP")
if [ -z "$COMMITS" ]; then
  echo "check-commits: no commits between $BASE and $TIP."
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fails=0
count=0
for sha in $COMMITS; do
  count=$((count+1))
  git -C "$ROOT" log -1 --format=%B "$sha" > "$WORK/msg"
  if ! python3 "$GATE" --commit-msg "$WORK/msg" --quiet; then
    echo "  in commit $(git -C "$ROOT" log -1 --format='%h %s' "$sha")" >&2
    fails=$((fails+1))
  fi
done

if [ "$fails" -eq 0 ]; then
  echo "check-commits: $count commit message(s) clean."
else
  echo "check-commits: $fails of $count commit message(s) failed." >&2
  echo "Rule 1 and rule 11 of CLAUDE.md. Reword them with an interactive" >&2
  echo "rebase, or reset and commit again with the hook installed:" >&2
  echo "  git config core.hooksPath .githooks" >&2
fi
exit "$fails"
