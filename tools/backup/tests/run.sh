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
# rather than leave a half restored database when the archive is damaged, when
# the cluster is missing the roles the archive's grants name, when the database
# it is pointed at still holds members, or when somebody stops it part way.
#
# The assertions themselves are in checks.sh beside this file, and the second
# half of the drill, everything about what a restore does and does not change,
# is in what_a_restore_changes.sh.
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

. "$TESTS/checks.sh"

step "A confirmation that was never typed"
# The count that arms a restore is meant to be visible in the command somebody
# ran. make imports the environment into its own variables, so without the
# origin test in the Makefile an exported OVERWRITE would arm every later
# restore in that shell. make -n prints the recipe and runs none of it, so
# nothing here goes near a database.
TYPED="$(cd "$ROOT" && make -n restore FILE=/no/such/archive.dump \
         OVERWRITE=12-members 2>&1 | grep 'restore.sh' || true)"
EXPORTED="$(cd "$ROOT" && OVERWRITE=12-members make -n restore \
            FILE=/no/such/archive.dump 2>&1 | grep 'restore.sh' || true)"
case "$TYPED" in
  *--overwrite*) ok "a count typed on the command line reaches restore.sh" ;;
  *) bad "a count typed on the command line never reached restore.sh" ;;
esac
case "$EXPORTED" in
  *--overwrite*) bad "an exported OVERWRITE armed a restore nobody confirmed" ;;
  *) ok "an exported OVERWRITE does not arm anything" ;;
esac

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
wait_for_postgres "$RESTORED"
EMPTY="$(docker exec "$RESTORED" psql -U postgres -d oro -tAc "SELECT coalesce(to_regclass('public.members')::text, 'no members table')")"
if [ "$EMPTY" = "no members table" ]; then ok "no members table, so nothing here can pass by accident"
else bad "the new database already holds $EMPTY"; fi
NOROLE="$(docker exec "$RESTORED" psql -U postgres -d oro -tAc "SELECT count(*) FROM pg_roles WHERE rolname = 'oro_api'")"
if [ "$NOROLE" = "0" ]; then ok "and no oro_api role, which is the half a database archive does not carry"
else bad "the new cluster already has an oro_api role"; fi

step "The archive with its roles file left behind, which has to be refused"
# No policy in db/migrations names a role. What needs oro_api and door_reader is
# the grants in 004_security.sql, and they are inside the archive, so the check
# reads the archive rather than the file beside it.
LEFTBEHIND="$WORK/roles-file-left-behind.dump"
cp "$ARCHIVE" "$LEFTBEHIND"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$LEFTBEHIND" \
     > "$WORK/leftbehind.out" 2>&1; then
  bad "an archive restored into a cluster without the roles its grants name"
else
  ok "refused"
fi
sed 's/^/  | /' "$WORK/leftbehind.out"
must_say "$WORK/leftbehind.out" "cluster: door_reader oro_api"
must_say "$WORK/leftbehind.out" "Nothing was changed"

step "And with a roles file belonging to a different cluster"
OTHER="$WORK/from-another-cluster.dump"
cp "$ARCHIVE" "$OTHER"
echo "CREATE ROLE drill_unrelated_role;" > "${OTHER%.dump}.roles.sql"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$OTHER" \
     > "$WORK/othercluster.out" 2>&1; then
  bad "a roles file that creates the wrong roles was accepted"
else
  ok "refused, because the roles it created are not the roles the archive needs"
fi
must_say "$WORK/othercluster.out" "cluster: door_reader oro_api"
STILL="$(docker exec "$RESTORED" psql -U postgres -d oro -tAc "SELECT coalesce(to_regclass('public.members')::text, 'no members table')")"
if [ "$STILL" = "no members table" ]; then ok "and neither attempt touched the database"
else bad "the database holds a $STILL after two attempts that were refused"; fi

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

if ! "$TESTS/what_a_restore_changes.sh" "$RESTORED" "$ARCHIVE" "$WORK"; then
  bad "what a restore changes reported failures, listed above"
fi
echo
if [ "$FAILURES" -gt 0 ]; then
  echo "$FAILURES check(s) failed" >&2
  exit 1
fi
echo "the drill passed: a database was backed up, destroyed, restored, and came"
echo "back with every card at the slot it had"
