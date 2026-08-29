#!/bin/sh
# What a restore changes, and what it must not.
#
#   tools/backup/tests/what_a_restore_changes.sh CONTAINER ARCHIVE WORKDIR
#
# The second half of the drill in run.sh. Read that one first: it calls this.
# The split is rule 6 of CLAUDE.md, which caps a file at 300 lines, and the two
# halves turned out to ask different questions anyway. run.sh asks one thing,
# which is whether an archive can be restored at all. This one asks whether a
# restore happens only when somebody asked for it, and whether what it changes
# is what the archive says and nothing else.
#
# It is handed a container holding a restored database and the archive that
# database came from, and it leaves both as it found them.
#
# Exit code is 1 if any check failed.

set -e
RESTORED="$1"
ARCHIVE="$2"
WORK="$3"
if [ -z "$RESTORED" ] || [ -z "$ARCHIVE" ] || [ -z "$WORK" ]; then
  echo "what_a_restore_changes.sh: name the container, the archive and a work" >&2
  echo "directory. tools/backup/tests/run.sh is what calls this." >&2
  exit 1
fi
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TESTS="$ROOT/tools/backup/tests"
ROLES="${ARCHIVE%.dump}.roles.sql"
FAILURES=0

. "$TESTS/checks.sh"

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
unchanged "$RESTORED" "$WORK/populated.txt"

step "The same restore with the wrong number of members named"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$ARCHIVE" \
     --overwrite "$((HOLDS + 1))-members" > "$WORK/wrongcount.out" 2>&1; then
  bad "a count that does not match the database was accepted"
else
  ok "refused, because the count names a database this is not"
fi
must_say "$WORK/wrongcount.out" "holds $HOLDS member"
unchanged "$RESTORED" "$WORK/populated.txt"

step "The database, damaged so that a restore has something to put back"
# A restore of this archive into the database this archive came from writes the
# rows it already holds, so it passes whether it ran or not. Taking rows out
# first is what makes the restore below prove it did something.
docker exec "$RESTORED" psql -U postgres -d oro -c 'DELETE FROM member_roles' >/dev/null
snapshot "$RESTORED" "$WORK/damaged.txt"
if diff "$WORK/populated.txt" "$WORK/damaged.txt" > "$WORK/damage.diff"; then
  bad "deleting every member_roles row changed nothing the comparison can see"
else
  ok "the comparison sees the damage: $(grep -c '^<' "$WORK/damage.diff") line(s) gone"
fi

step "A restore stopped part way, which has to leave the damage alone"
# docker exec does not pass a signal to the process it started, so a killed
# restore.sh used to leave pg_restore running in the container and committing.
# The database was then not what the person who hit ctrl-c believed it was.
#
# The lock is what makes this a test rather than a race. pg_restore's first
# statement drops a policy on members, which needs a lock no open transaction
# against members will give up, so the restore is reliably part way through.
docker exec -d "$RESTORED" psql -U postgres -d oro \
  -c "BEGIN; SELECT count(*) FROM members; SELECT pg_sleep(40); COMMIT;" >/dev/null
sleep 2
ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$ARCHIVE" \
  --overwrite "$HOLDS-members" > "$WORK/stopped.out" 2>&1 &
STOPPING=$!
sleep 6
kill -TERM "$STOPPING" 2>/dev/null || true
if wait "$STOPPING"; then
  bad "a restore that was killed reported that it had finished"
else
  ok "the kill was reported as a stop"
fi
sed 's/^/  | /' "$WORK/stopped.out"
must_say "$WORK/stopped.out" "stopped part way, and the restore went with it"
must_not_say "$WORK/stopped.out" "restored: $HOLDS members"
# Letting the lock go is the moment a restore that had not really been stopped
# would carry on and commit.
docker exec "$RESTORED" psql -U postgres -d oro -tAc \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
    WHERE query LIKE 'BEGIN; SELECT count(*) FROM members%'" >/dev/null
wait_for_the_restore_to_leave "$RESTORED"
sleep 2
unchanged "$RESTORED" "$WORK/damaged.txt"

step "And the same restore with the count named correctly"
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$ARCHIVE" \
     --overwrite "$HOLDS-members" > "$WORK/overwrite.out" 2>&1; then
  ok "it went ahead when the caller said what they were destroying"
else
  bad "a restore that named the count correctly was still refused"
  cat "$WORK/overwrite.out" >&2
fi
must_say "$WORK/overwrite.out" "restored: $HOLDS members"
snapshot "$RESTORED" "$WORK/repaired.txt"
if diff -u "$WORK/populated.txt" "$WORK/repaired.txt" > "$WORK/repaired.diff"; then
  ok "and the rows deleted before it ran are back, so the restore wrote something"
else
  bad "the restore ran and what came back is not what the archive holds"
  cat "$WORK/repaired.diff" >&2
fi

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
unchanged "$RESTORED" "$WORK/populated.txt"

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
unchanged "$RESTORED" "$WORK/populated.txt"

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
unchanged "$RESTORED" "$WORK/populated.txt"

step "The oro database dropped outright, which is where the runbook opens"
# pg_dump was not given --create, so the archive carries the contents of a
# database and not the database. Without the empty one restore.sh makes first,
# this is the case the tooling could not handle.
docker exec "$RESTORED" psql -U postgres -d postgres \
  -c 'DROP DATABASE oro WITH (FORCE)' >/dev/null
GONE="$(docker exec "$RESTORED" psql -U postgres -d postgres -tAc \
        "SELECT count(*) FROM pg_database WHERE datname = 'oro'")"
if [ "$GONE" = "0" ]; then ok "the database is gone, not just the rows in it"
else bad "the database is still there, so this proves nothing"; fi
if ORO_DB_CONTAINER="$RESTORED" "$ROOT/tools/backup/restore.sh" "$ARCHIVE" \
     > "$WORK/recreated.out" 2>&1; then
  ok "it restored anyway"
else
  bad "an archive would not restore into a cluster whose database had been dropped"
  cat "$WORK/recreated.out" >&2
fi
sed 's/^/  | /' "$WORK/recreated.out"
must_say "$WORK/recreated.out" "so an empty one was created"
unchanged "$RESTORED" "$WORK/populated.txt"


if [ "$FAILURES" -gt 0 ]; then
  echo
  echo "$FAILURES check(s) failed in what a restore changes" >&2
  exit 1
fi
