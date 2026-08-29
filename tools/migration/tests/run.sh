#!/bin/sh
# Prove the legacy import: what it carries, and every refusal it makes.
#
#   tools/migration/tests/run.sh
#
# A migration that carries the data is half the claim. The other half is that it
# refuses to start while anything in the legacy data still needs a person's
# decision, because docs/plan/data-model.md section 6.2 says it names offending
# rows rather than truncating, renumbering or skipping them.
#
# Every refusal here is checked by its own text as well as by its exit code. A
# broken script that exits nonzero looks exactly like a working refusal from the
# outside, so a case that only counted the exit code would go on passing after
# the refusal it was written for stopped existing.
#
# The migration prints a report of what it did not carry. That report is read
# here rather than piped away, because a report nobody checks is a report that
# quietly stops being true.
#
# Needs docker and nothing else. Leaves nothing behind.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TESTS="$ROOT/tools/migration/tests"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FAILURES=0

case_header() { echo; echo "== $1"; }

must_say() {  # must_say FILE "text that has to appear"
  if grep -qF "$2" "$1"; then
    echo "  ok    $2"
  else
    echo "  FAIL  never said: $2" >&2
    FAILURES=$((FAILURES + 1))
  fi
}

migrated() {  # migrated OUTFILE [run.sh options], true when run.sh was happy
  out="$1"; shift
  if "$ROOT/tools/migration/run.sh" "$@" > "$out" 2>&1; then return 0; fi
  cat "$out" >&2
  return 1
}

ran() {  # ran OUTFILE [run.sh options], records a failure and carries on
  if migrated "$@"; then return 0; fi
  echo "  FAIL  run.sh was not happy with this case" >&2
  FAILURES=$((FAILURES + 1))
  return 1
}

case_header "The fixture as it comes, which has to be refused"
if ran "$WORK/undecided.out" --undecided; then
  cat "$WORK/undecided.out"
  must_say "$WORK/undecided.out" "cards outside slots 10 to 199"
  must_say "$WORK/undecided.out" "members carrying the legacy instructor flag"
  must_say "$WORK/undecided.out" "members with a payee"
  must_say "$WORK/undecided.out" "no row in legacy.waiver_documents"
fi

case_header "The same fixture with the decisions made"
if ran "$WORK/decided.out"; then
  cat "$WORK/decided.out"
  must_say "$WORK/decided.out" "preflight: nothing in the legacy data needs a decision"
  must_say "$WORK/decided.out" "member 1 (Ada Invented) now holds admin, granted by nobody"
  must_say "$WORK/decided.out" "member 2 (Six Char) now holds accountant, granted by nobody"
  must_say "$WORK/decided.out" "that timestamp is when this import ran"
  must_say "$WORK/decided.out" "waivers: 1 row(s) carried"
  must_say "$WORK/decided.out" "not carried, twelve columns of the forty:"
  must_say "$WORK/decided.out" "the instructor flag and a payee are the other two of the fourteen"
  must_say "$WORK/decided.out" "1 member(s) were oriented by somebody"
  must_say "$WORK/decided.out" "verify: 12 member(s) and 5 card(s)"
  must_say "$WORK/decided.out" "verify: 2 role(s) and 1 waiver(s) carried"
  must_say "$WORK/decided.out" "role 1 -> admin, approval none"
  must_say "$WORK/decided.out" "oriented 3 -> 2025-11-01 23:01:57.497538 UTC"
  must_say "$WORK/decided.out" "waiver 1 -> signed 2025-07-24"
  must_say "$WORK/decided.out" "kept in google-form"
fi

case_header "One instructor left, and nothing else to decide"
if ran "$WORK/instructor.out" --also "$TESTS/an-instructor.sql" \
     --refusal "members carrying the legacy instructor flag"; then
  cat "$WORK/instructor.out"
  must_say "$WORK/instructor.out" "user 2 (Six Char)"
  must_say "$WORK/instructor.out" "which certifications"
fi

case_header "One payee left, and nothing else to decide"
if ran "$WORK/payee.out" --also "$TESTS/a-payee.sql" \
     --refusal "members with a payee, somebody paying on their behalf"; then
  cat "$WORK/payee.out"
  must_say "$WORK/payee.out" "user 3 (Non Ascii)"
  must_say "$WORK/payee.out" "There is no column for that anywhere in this schema"
fi

case_header "A waiver whose document nobody has placed"
if ran "$WORK/waiver.out" --also "$TESTS/a-waiver-nobody-can-find.sql" \
     --refusal "no row in legacy.waiver_documents"; then
  cat "$WORK/waiver.out"
  must_say "$WORK/waiver.out" "user 1 (Ada Invented)"
  must_say "$WORK/waiver.out" "never the document"
fi

case_header "An admin who left, whose flag nobody cleared"
if ran "$WORK/departed.out" --also "$TESTS/a-departed-admin.sql" \
     --refusal "members who hold a role flag and have an exit_reason"; then
  cat "$WORK/departed.out"
  must_say "$WORK/departed.out" "user 1 (Ada Invented), admin, left saying"
  must_say "$WORK/departed.out" "grant a live role to somebody who left"
fi

case_header "A waiver document placed against somebody who never signed"
if ran "$WORK/stray.out" --also "$TESTS/a-stray-waiver-document.sql" \
     --refusal "rows in legacy.waiver_documents for members who never signed"; then
  cat "$WORK/stray.out"
  must_say "$WORK/stray.out" "user 5"
  must_say "$WORK/stray.out" "the user_id is wrong"
fi

# The legacy waiver column is `timestamp without time zone` and signed_at is
# `timestamptz`, so the zone the naive value is read in decides the instant that
# lands. America/Phoenix is the lab's own zone and the one most likely to be set
# on a machine somebody runs this from. 024_waivers.sql pins the read to UTC,
# and this is what proves it: with the pin removed the date moves seven hours
# and every assertion inside the migration still agrees with itself, because
# both sides of the verify cast the same way.
case_header "The same import in the lab's own time zone, where the date must not move"
if ran "$WORK/phoenix.out" --timezone America/Phoenix; then
  cat "$WORK/phoenix.out"
  must_say "$WORK/phoenix.out" "waiver 1 -> signed 2025-07-24 23:01:57.49312 UTC"
  must_say "$WORK/phoenix.out" "oriented 3 -> 2025-11-01 23:01:57.497538 UTC"
  must_say "$WORK/phoenix.out" "card issued 10 -> 2026-08-28 23:01:57.505817 UTC"
  must_say "$WORK/phoenix.out" "verify: 2 role(s) and 1 waiver(s) carried"
fi

# The disable in 022_roles.sql is the whole of the exception data-model.md
# section 6.1 authorises, and the committed fixture has one admin against a
# quota of three, so it never reaches the refusal that makes the disable
# necessary. These two cases are the same import past the quota, with the
# disable and without it.
case_header "More admins than the bootstrap quota, with the trigger disabled"
if ran "$WORK/quota.out" --also "$TESTS/more-admins-than-the-quota.sql"; then
  cat "$WORK/quota.out"
  must_say "$WORK/quota.out" "member 101 (Second Admin) now holds admin"
  must_say "$WORK/quota.out" "member 104 (Fifth Admin) now holds admin"
  must_say "$WORK/quota.out" "the two approver rule armed itself"
  must_say "$WORK/quota.out" "verify: 6 role(s) and 1 waiver(s) carried"
fi

ALTERS=$(grep -c '^ *ALTER TABLE member_roles' "$ROOT/tools/migration/022_roles.sql" || true)
sed '/^ *ALTER TABLE member_roles .*TRIGGER role_grant_rules;$/d' \
  "$ROOT/tools/migration/022_roles.sql" > "$WORK/roles-without-the-disable.sql"
STRIPPED=$(grep -c '^ *ALTER TABLE member_roles' "$WORK/roles-without-the-disable.sql" || true)

case_header "The same import with the trigger left on, which has to be refused"
if [ "$ALTERS" != "2" ] || [ "$STRIPPED" != "0" ]; then
  # Without this the case still passes while proving nothing, because a copy
  # identical to the original would be running the disable after all.
  echo "  FAIL  022_roles.sql no longer has the two ALTER TABLE lines this case removes" >&2
  FAILURES=$((FAILURES + 1))
elif ran "$WORK/quota-no-disable.out" --also "$TESTS/more-admins-than-the-quota.sql" \
       --roles "$WORK/roles-without-the-disable.sql" \
       --refusal "Granting admin needs an approval from a second admin."; then
  cat "$WORK/quota-no-disable.out"
  must_say "$WORK/quota-no-disable.out" "seat 3 of 3"
  must_say "$WORK/quota-no-disable.out" "enforce_role_grant_rules"
fi

case_header "The role step run on its own, which must not turn the trigger off"
if ! "$TESTS/check_the_guard.sh" > "$WORK/guard.out" 2>&1; then
  cat "$WORK/guard.out" >&2
  echo "  FAIL  the role step left the trigger off when run alone" >&2
  FAILURES=$((FAILURES + 1))
else
  grep -E '^  ok|^the role step' "$WORK/guard.out"
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "$FAILURES check(s) failed" >&2
  exit 1
fi
echo "every case passed, and every refusal was refused for the reason it names"
