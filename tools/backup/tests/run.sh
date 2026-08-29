#!/bin/sh
# The restore drill.
#
#   tools/backup/tests/run.sh
#
# Rule 12 of CLAUDE.md puts a verified, restorable backup above every phase, and
# docs/plan/order-of-operations.md phase 0 item 3 says a backup nobody has
# restored is a hypothesis. This is the check that turns the hypothesis into a
# fact, and it is the reason tools/backup exists at all.
#
# What it proves is the mechanism. It does not prove anything about the lab's
# own data: the rows here are the invented members in tools/migration/fixtures,
# carried through the real import. A verified restore of production onto a
# staging copy is phase 0 item 5, it needs a shell on the lab's server, and no
# script in this repository can stand in for it.
#
# Both directions are checked. The restore has to bring the database back
# exactly, down to the slot each card sits at, and it has to refuse loudly
# rather than leave a half restored database when the archive is damaged or
# when the database it is pointed at still holds members.
#
# Needs docker and nothing else. Two throwaway containers on no published port,
# a temporary directory for the archives, and it removes all of it.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TESTS="$ROOT/tools/backup/tests"
SOURCE="oro-backup-drill-source-$$"
RESTORED="oro-backup-drill-restored-$$"
WORK="$(mktemp -d)"
BACKUPS="$WORK/backups"
FAILURES=0

cleanup() {
  docker rm -f "$SOURCE" "$RESTORED" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

step() { echo; echo "== $1"; }
ok()   { echo "  ok    $1"; }
bad()  { echo "  FAIL  $1" >&2; FAILURES=$((FAILURES + 1)); }

# psql -tA and nothing else, so the output is data rather than a table drawing.
snapshot() {  # snapshot CONTAINER FILE
  docker exec -i "$1" psql -U postgres -d oro -tA -q -v ON_ERROR_STOP=1 \
    < "$TESTS/what_must_match.sql" > "$2"
}

members_in() {  # members_in CONTAINER
  docker exec "$1" psql -U postgres -d oro -tAc 'SELECT count(*) FROM members'
}

must_say() {  # must_say FILE "text that has to appear"
  if grep -qF "$2" "$1"; then ok "said: $2"; else bad "never said: $2"; fi
}

unchanged() {  # unchanged FILE_TAKEN_BEFORE, against the restored container now
  snapshot "$RESTORED" "$WORK/now.txt"
  if diff -u "$1" "$WORK/now.txt" > "$WORK/now.diff"; then
    ok "the database is exactly as it was before that attempt"
  else
    bad "the database changed during an attempt that was refused"
    cat "$WORK/now.diff" >&2
  fi
}

step "A database shaped like the day of the migration"
"$TESTS/load_a_migrated_database.sh" "$SOURCE"
snapshot "$SOURCE" "$WORK/before.txt"
must_say "$WORK/before.txt" "table public.members 12 rows"
must_say "$WORK/before.txt" "table public.cards 5 rows"
must_say "$WORK/before.txt" "database role oro_api"
echo "  $(wc -l < "$WORK/before.txt" | tr -d ' ') lines of things that must come back"

step "A backup, taken by the command make backup runs"
ORO_DB_CONTAINER="$SOURCE" ORO_BACKUP_DIR="$BACKUPS" "$ROOT/tools/backup/backup.sh"
ARCHIVE="$(ls "$BACKUPS"/oro-*.dump 2>/dev/null | tail -1)"
ROLES="${ARCHIVE%.dump}.roles.sql"
if [ -s "$ARCHIVE" ]; then ok "the archive is $ARCHIVE"; else bad "no archive was written"; exit 1; fi
if [ -s "$ROLES" ]; then ok "the roles beside it are $ROLES"; else bad "no roles file was written"; fi
# Rule 13. An archive of the members database is member data, and a file
# somebody else on the machine can read is a copy of the lab's membership.
MODE="$(ls -l "$ARCHIVE" | cut -c1-10)"
if [ "$MODE" = "-rw-------" ]; then ok "readable only by the person who took it"
else bad "the archive is $MODE, and only the owner may read it"; fi
if grep -qi 'password' "$ROLES"; then bad "the roles file carries a password hash"
else ok "the roles file carries no password"; fi

step "The database, destroyed"
docker rm -f "$SOURCE" >/dev/null
if docker inspect "$SOURCE" >/dev/null 2>&1; then bad "the source container is still there"
else ok "the container and its cluster are gone, so there is nothing to restore from but the archive"; fi

step "A new database with nothing in it"
docker run -d --rm --name "$RESTORED" -e POSTGRES_PASSWORD=drill \
  -e POSTGRES_DB=oro postgres:18 >/dev/null
printf '  waiting for postgres'
i=0
seen=0
while [ "$seen" -lt 2 ]; do
  if docker exec "$RESTORED" psql -U postgres -d oro -tAc 'SELECT 1' >/dev/null 2>&1; then
    seen=$((seen + 1))
  else
    seen=0
  fi
  i=$((i + 1))
  if [ "$i" -gt 90 ]; then echo " timed out"; exit 1; fi
  printf '.'
  sleep 1
done
echo " ready"
EMPTY="$(docker exec "$RESTORED" psql -U postgres -d oro -tAc "SELECT coalesce(to_regclass('public.members')::text, 'no members table')")"
if [ "$EMPTY" = "no members table" ]; then ok "no members table, so nothing here can pass by accident"
else bad "the new database already holds $EMPTY"; fi
NOROLE="$(docker exec "$RESTORED" psql -U postgres -d oro -tAc "SELECT count(*) FROM pg_roles WHERE rolname = 'oro_api'")"
if [ "$NOROLE" = "0" ]; then ok "and no oro_api role, which is the half a database archive does not carry"
else bad "the new cluster already has an oro_api role"; fi

step "Restored from the archive"
ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$ARCHIVE"

step "The same database came back"
snapshot "$RESTORED" "$WORK/after.txt"
if diff -u "$WORK/before.txt" "$WORK/after.txt" > "$WORK/fidelity.diff"; then
  ok "every line matches: row counts, card slots, roles, sequences and policies"
  grep '^card ' "$WORK/after.txt" | sed 's/^/  /'
else
  bad "the restored database is not the one that was backed up"
  cat "$WORK/fidelity.diff" >&2
fi

step "Every assertion the migration makes, made again against the restore"
# 030_verify.sql is the file that already knows what must not move. Running it
# here rather than writing a second list of assertions means the two cannot
# drift apart. Its output is NOTICE, which psql writes to stderr.
if docker exec -i "$RESTORED" psql -v ON_ERROR_STOP=1 -q -U postgres -d oro \
     < "$ROOT/tools/migration/030_verify.sql" > "$WORK/verify.out" 2>&1; then
  must_say "$WORK/verify.out" "every card at the slot it had"
  must_say "$WORK/verify.out" "verify: 2 role(s) and 1 waiver(s) carried"
else
  bad "030_verify.sql refuses the restored database"
  cat "$WORK/verify.out" >&2
fi

step "A restore over a database that holds members, which has to be refused"
snapshot "$RESTORED" "$WORK/populated.txt"
HOLDS="$(members_in "$RESTORED")"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$ARCHIVE" \
     > "$WORK/refused.out" 2>&1; then
  bad "it restored over $HOLDS members without being asked twice"
else
  ok "refused"
fi
sed 's/^/  | /' "$WORK/refused.out"
must_say "$WORK/refused.out" "already holds $HOLDS member"
must_say "$WORK/refused.out" "Nothing was changed"
must_say "$WORK/refused.out" "OVERWRITE=$HOLDS-members"
unchanged "$WORK/populated.txt"

step "The same restore with the wrong number of members named"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$ARCHIVE" \
     --overwrite "$((HOLDS + 1))-members" > "$WORK/wrongcount.out" 2>&1; then
  bad "a count that does not match the database was accepted"
else
  ok "refused, because the count names a database this is not"
fi
must_say "$WORK/wrongcount.out" "holds $HOLDS member"
unchanged "$WORK/populated.txt"

step "And the same restore with the count named correctly"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$ARCHIVE" \
     --overwrite "$HOLDS-members" > "$WORK/overwrite.out" 2>&1; then
  ok "it went ahead when the caller said what they were destroying"
else
  bad "a restore that named the count correctly was still refused"
  cat "$WORK/overwrite.out" >&2
fi
unchanged "$WORK/populated.txt"

step "An archive with its tail cut off, which has to be refused"
CUT="$WORK/cut-in-half.dump"
BYTES="$(wc -c < "$ARCHIVE" | tr -d ' ')"
head -c "$((BYTES / 2))" "$ARCHIVE" > "$CUT"
cp "$ROLES" "${CUT%.dump}.roles.sql"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$CUT" \
     --overwrite "$HOLDS-members" > "$WORK/cut.out" 2>&1; then
  bad "half an archive restored, which means half a database"
else
  ok "refused"
fi
sed 's/^/  | /' "$WORK/cut.out"
must_say "$WORK/cut.out" "Nothing was changed"
unchanged "$WORK/populated.txt"

# The cut above stops short of the archive's own table of contents, so it is
# refused before the database is touched. This one keeps the table of contents
# and loses the end of the data, which is the shape a disk that filled up
# leaves behind. Either layer may catch it: the read back, or the transaction
# the restore runs inside. What the drill asserts is the part that matters
# either way, which is that it was refused and that the database did not move.
step "An archive with only its last bytes cut off"
NEARLY="$WORK/nearly-whole.dump"
head -c "$((BYTES * 99 / 100))" "$ARCHIVE" > "$NEARLY"
cp "$ROLES" "${NEARLY%.dump}.roles.sql"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$NEARLY" \
     --overwrite "$HOLDS-members" > "$WORK/nearly.out" 2>&1; then
  bad "an archive missing its last bytes restored anyway"
else
  ok "refused"
fi
if grep -q "is not an archive this can restore" "$WORK/nearly.out"; then
  echo "  caught by the read back, before the database was touched"
else
  echo "  caught by the transaction the restore runs inside, and rolled back"
fi
must_say "$WORK/nearly.out" "Nothing was changed"
unchanged "$WORK/populated.txt"

step "A file that is not an archive at all"
NOTADUMP="$WORK/not-an-archive.dump"
echo "this is a text file somebody renamed" > "$NOTADUMP"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$NOTADUMP" \
     --overwrite "$HOLDS-members" > "$WORK/notadump.out" 2>&1; then
  bad "a text file was accepted as a backup"
else
  ok "refused"
fi
must_say "$WORK/notadump.out" "Nothing was changed"
unchanged "$WORK/populated.txt"

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "$FAILURES check(s) failed" >&2
  exit 1
fi
echo "the drill passed: a database was backed up, destroyed, restored, and came"
echo "back with every card at the slot it had"
