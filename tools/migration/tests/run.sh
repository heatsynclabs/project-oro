#!/bin/sh
# Prove the legacy import both ways.
#
#   tools/migration/tests/run.sh
#
# A migration that carries the data is half the claim. The other half is that it
# refuses to start while anything in the legacy data still needs a person's
# decision, because docs/plan/data-model.md section 6.2 says it names offending
# rows rather than truncating, renumbering or skipping them.
#
# Needs docker and nothing else. Leaves nothing behind.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

echo "The fixture as it comes, which has to be refused"
"$ROOT/tools/migration/run.sh" --undecided | tail -8
echo

echo "The same fixture with the decisions made"
"$ROOT/tools/migration/run.sh" | tail -20
