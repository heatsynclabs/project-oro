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
# nothing there to lose.
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
INSIDE="/tmp/oro-restore-$$.dump"
cleanup() {
  # The copy inside the container is the lab's member data on a filesystem
  # nobody is watching, so it goes whether this run worked or not.
  docker exec "$CONTAINER" rm -f "$INSIDE" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

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

# to_regclass answers null rather than raising, so this works on a database with
# no schema in it at all, which is what a restore onto a new machine finds.
TABLE="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
         "SELECT coalesce(to_regclass('public.members')::text, '')")"
HOLDS=0
if [ -n "$TABLE" ]; then
  HOLDS="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
           'SELECT count(*) FROM members')"
fi

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

# The roles a database archive cannot carry, written beside it by backup.sh.
# Applied before the archive, because the archive's first GRANT names one.
ROLES="${ARCHIVE%.dump}.roles.sql"
if [ -f "$ROLES" ]; then
  # Not ON_ERROR_STOP. Every role that already exists reports an error here and
  # that is the ordinary case: a cluster that has been up for a minute already
  # has postgres. What matters is the state afterwards, which is checked rather
  # than assumed.
  docker exec -i "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -q \
    < "$ROLES" > "$WORK/roles.out" 2>&1 || true
  MISSING=""
  for role in $(sed -n 's/^CREATE ROLE \([A-Za-z0-9_]*\);$/\1/p' "$ROLES"); do
    found="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
             "SELECT count(*) FROM pg_roles WHERE rolname = '$role'")"
    if [ "$found" = "0" ]; then MISSING="$MISSING $role"; fi
  done
  if [ -n "$MISSING" ]; then
    cat "$WORK/roles.out" >&2
    echo "restore.sh: these roles are named by the archive's grants and are not" >&2
    echo "in this cluster:$MISSING" >&2
    echo "The restore was not attempted, because it would fail partway through" >&2
    echo "the first GRANT. Nothing was changed." >&2
    exit 1
  fi
  echo "$ROLES applied, every role it names is in the cluster"
else
  echo "no roles file beside the archive, so the cluster keeps the roles it has"
fi

# pg_restore has to seek within the archive, so it cannot read one on a pipe.
# Measured on 2026-08-28: pg_restore 18.6 reading /dev/stdin answers "could not
# read from input file: end of file". So the file goes in, and the trap above
# takes it out again.
docker cp "$ARCHIVE" "$CONTAINER:$INSIDE" >/dev/null

echo "restoring into the $DATABASE database in container $SHOWN"
# --single-transaction is what makes a failure safe: the whole archive lands or
# none of it does, so a restore that dies halfway leaves the database it started
# with rather than half of two. --clean --if-exists is what lets it replace a
# database that already holds something.
if ! docker exec "$CONTAINER" pg_restore -U "$SUPERUSER" -d "$DATABASE" \
     --clean --if-exists --single-transaction "$INSIDE" > "$WORK/restore.out" 2>&1; then
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
