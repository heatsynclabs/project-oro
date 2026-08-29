#!/bin/sh
# Restore the oro database from an archive that tools/backup/backup.sh wrote.
#
#   tools/backup/restore.sh ARCHIVE
#   tools/backup/restore.sh ARCHIVE --overwrite 12-members
#
# The second form is the one that replaces a database somebody is using. A
# restore into a database that already holds members is refused until the caller
# names how many members they are about to destroy, and the number has to match
# what is in the database right now. That shape is deliberate: a line copied out
# of the runbook, or pulled back out of a shell history a week later, refuses
# against a database holding a different number of people, and the only way to
# get the number is to read the refusal this script prints. A plain yes or no
# flag would survive both.
#
# Restoring into an empty database needs no confirmation, because there is
# nothing there to lose. A cluster where the oro database has been dropped needs
# none either: this creates it empty first. pg_dump was not given --create, so
# the archive carries the contents of a database and not the database itself.
#
# Stopping it part way. ctrl-c, kill, and a dropped ssh session all stop the
# restore and leave the database where it was. docker exec does not pass a
# signal to the process it started, so a killed script on its own would leave
# pg_restore running inside the container and committing. What happens instead
# is that this names its pg_restore connection and, on a signal, terminates that
# backend. The archive runs inside one transaction, so terminating it puts the
# database back where it started. SIGKILL is the one nothing can catch: a
# restore ended with kill -9 runs on to the end inside the container, and the
# way to find out what it did is to read the member count back.
#
#   ORO_DB_CONTAINER  the container to restore into. The default is the db
#                     service of the compose stack in this directory. The drill
#                     in tools/backup/tests/run.sh sets it to a throwaway
#                     container, so the drill exercises this script rather than
#                     a copy of it.
#
# Needs docker. Exit code is 1 if anything was refused, and a refusal leaves the
# database exactly as it was.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"

# compose.yaml sets POSTGRES_DB to oro, and the image's superuser is postgres.
DATABASE=oro
SUPERUSER=postgres

ARCHIVE=""
OVERWRITE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --overwrite)
      OVERWRITE="$2"
      shift ;;
    -*)
      echo "restore.sh: unknown option '$1'. The header of this file lists them." >&2
      exit 1 ;;
    *)
      ARCHIVE="$1" ;;
  esac
  shift
done

if [ -z "$ARCHIVE" ]; then
  echo "restore.sh: name the archive to restore." >&2
  echo "  make restore FILE=\$HOME/oro-backups/oro-20260828T204500Z.dump" >&2
  echo "The newest one is the last line of: ls -l \$HOME/oro-backups" >&2
  exit 1
fi
if [ ! -f "$ARCHIVE" ]; then
  echo "restore.sh: there is no file at $ARCHIVE, so nothing was restored." >&2
  echo "Nothing was changed." >&2
  exit 1
fi

CONTAINER="${ORO_DB_CONTAINER:-}"
if [ -z "$CONTAINER" ]; then
  CONTAINER="$(cd "$ROOT" && docker compose ps --quiet db 2>/dev/null || true)"
fi
if [ -z "$CONTAINER" ]; then
  echo "restore.sh: no database container is running, so nothing was restored." >&2
  echo "Start the stack with make up and run this again. If the database runs" >&2
  echo "somewhere else, name its container in ORO_DB_CONTAINER." >&2
  echo "Nothing was changed." >&2
  exit 1
fi

# Messages name the container the way a person does. docker compose ps answers
# with 64 characters of hex, which tells a reader at 2am nothing about which
# stack they are looking at.
SHOWN="$(docker inspect --format '{{.Name}}' "$CONTAINER" 2>/dev/null | sed 's|^/||')"
if [ -z "$SHOWN" ]; then SHOWN="$CONTAINER"; fi

WORK="$(mktemp -d)"
# The archive goes onto the container's /dev/shm, which is a tmpfs. A copy of
# the members database on a container filesystem is member data on a disk
# nobody is watching, and rule 13 of CLAUDE.md is why it does not go there. The
# name carries this script's process id so two restores cannot collide.
INSIDE="/dev/shm/oro-restore-$$.dump"
# The name pg_restore's connection carries, so a signal can find that backend
# again. Postgres shows it in pg_stat_activity.application_name.
RESTORE_TAG="oro-restore-$$"

members_in_the_database() {
  table="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
           "SELECT coalesce(to_regclass('public.members')::text, '')" 2>/dev/null || true)"
  if [ -z "$table" ]; then
    echo "no members table"
    return
  fi
  count="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
           'SELECT count(*) FROM members' 2>/dev/null || true)"
  if [ -z "$count" ]; then
    echo "a members table it would not read"
  else
    echo "$count member rows"
  fi
}

cleanup() {
  docker exec "$CONTAINER" rm -f "$INSIDE" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

stopped() {
  ended="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
    "SELECT count(*) FROM (SELECT pg_terminate_backend(pid) FROM pg_stat_activity
      WHERE application_name = '$RESTORE_TAG') ended" 2>/dev/null || echo 0)"
  echo >&2
  if [ "$ended" = "0" ]; then
    echo "restore.sh: stopped part way, before the restore itself had started." >&2
  else
    echo "restore.sh: stopped part way, and the restore went with it. pg_restore" >&2
    echo "ran the archive inside one transaction and that transaction was" >&2
    echo "terminated, so nothing it had done was kept." >&2
  fi
  echo "The $DATABASE database in container $SHOWN holds $(members_in_the_database)." >&2
  exit 1
}
trap stopped INT TERM HUP

# Before anything else, and before the database is touched at all. An archive
# that cannot be opened is the failure this whole gate exists to catch, and a
# throwaway container reads it without going anywhere near the database that is
# serving the lab.
if ! docker run -i --rm postgres:18 \
     sh -c 'cat > /tmp/verify.dump && pg_restore --list /tmp/verify.dump' \
     < "$ARCHIVE" > "$WORK/toc" 2>&1; then
  cat "$WORK/toc" >&2
  echo "restore.sh: $ARCHIVE is not an archive this can restore, and the error" >&2
  echo "above says why. Nothing was changed." >&2
  echo "Try the archive taken before it. If none of them read back, the backups" >&2
  echo "have been failing for as long as they have been unreadable, which is the" >&2
  echo "thing to say out loud before anybody tries anything else." >&2
  exit 1
fi
echo "$ARCHIVE reads back, $(grep -c '^[0-9]' "$WORK/toc" || true) entries"

# The runbook opens with the database being gone, and that is the case where
# there is nothing for pg_restore to connect to. Creating it empty destroys
# nothing, and it is the whole of what --create would have carried.
PRESENT="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d postgres -tAc \
           "SELECT count(*) FROM pg_database WHERE datname = '$DATABASE'" \
           2>"$WORK/cluster.err" || true)"
if [ -z "$PRESENT" ]; then
  cat "$WORK/cluster.err" >&2
  echo "restore.sh: container $SHOWN is running and its Postgres did not answer," >&2
  echo "so nothing was restored. make logs shows what the database printed, and" >&2
  echo "a cluster that will not start is a different problem from a lost" >&2
  echo "database. Nothing was changed." >&2
  exit 1
fi
if [ "$PRESENT" = "0" ]; then
  docker exec "$CONTAINER" createdb -U "$SUPERUSER" "$DATABASE"
  echo "there was no $DATABASE database in container $SHOWN, so an empty one was created"
fi

HELD="$(members_in_the_database)"
case "$HELD" in
  *" member rows") HOLDS="${HELD% member rows}" ;;
  *) HOLDS=0 ;;
esac

if [ "$HOLDS" -gt 0 ] && [ "$OVERWRITE" != "$HOLDS-members" ]; then
  echo >&2
  echo "restore.sh: this database already holds $HOLDS member rows, and restoring" >&2
  echo "over it would replace every one of them. Nothing was changed." >&2
  echo "It is the $DATABASE database in container $SHOWN." >&2
  echo >&2
  if [ -n "$OVERWRITE" ]; then
    echo "You said $OVERWRITE, and this database holds $HOLDS members. Those are two" >&2
    echo "different databases. Check which container you are pointed at before" >&2
    echo "you change the number." >&2
    echo >&2
  fi
  echo "If replacing them is what you want, say so by naming the count:" >&2
  echo >&2
  echo "  make restore FILE=$ARCHIVE OVERWRITE=$HOLDS-members" >&2
  echo >&2
  echo "The count is part of the command so that this one refuses against any" >&2
  echo "database except the one you just read about." >&2
  exit 1
fi

# Roles belong to the cluster rather than to one database, so the archive cannot
# carry them. That script applies the file beside the archive and then checks
# the cluster against what the archive's own grants name, and it refuses before
# the database is touched.
if ! "$ROOT/tools/backup/roles_the_archive_needs.sh" "$ARCHIVE" "$CONTAINER"; then
  exit 1
fi

# pg_restore has to seek within the archive, so it cannot read one on a pipe.
# Measured on 2026-08-28: pg_restore 18.6 reading /dev/stdin answers "could not
# read from input file: end of file". So a copy goes in, onto the tmpfs, and the
# shell that runs pg_restore removes it whatever pg_restore made of it. That
# removal does not depend on this script living long enough to do it.
BYTES="$(wc -c < "$ARCHIVE" | tr -d ' ')"
FREE="$(docker exec "$CONTAINER" df -Pk /dev/shm | awk 'NR == 2 { printf "%d\n", $4 * 1024 }')"
if [ "$BYTES" -ge "$FREE" ]; then
  echo "restore.sh: the archive is $BYTES bytes and container $SHOWN has $FREE" >&2
  echo "bytes free on /dev/shm, where the restore puts its copy so that no copy" >&2
  echo "of the members database is left on a disk. Nothing was changed." >&2
  echo "Docker gives a container 64MB of /dev/shm and Postgres uses some of it." >&2
  echo "Give the db service more, in compose.yaml under the db service:" >&2
  echo "  shm_size: 512m" >&2
  echo "then make down, make up, and run this again." >&2
  exit 1
fi

echo "restoring into the $DATABASE database in container $SHOWN"
# --single-transaction is what makes a failure safe: the whole archive lands or
# none of it does, so a restore that dies halfway leaves the database it started
# with rather than half of two. --clean --if-exists is what lets it replace a
# database that already holds something.
#
# In the background and waited for, rather than in the foreground. A shell
# waiting on a foreground command runs a trap only once that command returns,
# which for this one is after the restore has committed, and the trap is the
# whole mechanism that makes ctrl-c mean what it says.
docker exec -i "$CONTAINER" sh -c '
      umask 077
      cat > "$1" || exit 1
      pg_restore -d "$2" --clean --if-exists --single-transaction "$1"
      status=$?
      rm -f "$1"
      exit $status
    ' restore-in-container "$INSIDE" \
      "dbname=$DATABASE user=$SUPERUSER application_name=$RESTORE_TAG" \
      < "$ARCHIVE" > "$WORK/restore.out" 2>&1 &
RESTORE_CLIENT=$!
if ! wait "$RESTORE_CLIENT"; then
  cat "$WORK/restore.out" >&2
  echo "restore.sh: the restore was refused and rolled back, and the error above" >&2
  echo "says why. Nothing was changed: pg_restore ran the whole archive inside" >&2
  echo "one transaction, so the database still holds every row it held before." >&2
  exit 1
fi
cat "$WORK/restore.out"

TABLE="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
         "SELECT coalesce(to_regclass('public.members')::text, '')")"
if [ -z "$TABLE" ]; then
  echo "restored, and this archive holds no members table. That is what a backup"
  echo "of a stack nobody has migrated into looks like. Check you restored the"
  echo "archive you meant to."
  exit 0
fi

MEMBERS="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
           'SELECT count(*) FROM members')"
CARDS="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
         'SELECT count(*) FROM cards')"
# Only the cards the legacy import carried. A card issued after cutover has no
# legacy row to sit against, and its slot comes from whoever issued it.
MOVED="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
         'SELECT count(*) FROM cards
           WHERE legacy_id IS NOT NULL AND controller_slot IS DISTINCT FROM legacy_id')"

echo "restored: $MEMBERS members and $CARDS cards"
if [ "$MOVED" != "0" ]; then
  echo >&2
  echo "restore.sh: $MOVED card(s) are not at the slot their legacy row had. The" >&2
  echo "restore itself finished, so this came out of the archive that way. A slot" >&2
  echo "is an EEPROM address on the door controller, so do not reconcile the door" >&2
  echo "against this database until somebody has read tools/migration/030_verify.sql" >&2
  echo "and worked out which cards moved and when." >&2
  exit 1
fi
echo "and every card the legacy import carried is at the slot it had"
