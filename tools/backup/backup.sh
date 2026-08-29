#!/bin/sh
# Take a backup of the oro database out of the running stack.
#
#   tools/backup/backup.sh          what make backup runs
#
# Two files land in the backup directory, both named after the moment the
# backup was taken:
#
#   oro-20260828T204500Z.dump        the database, pg_dump custom format
#   oro-20260828T204500Z.roles.sql   the roles the database's grants name
#
# The second file exists because roles live in the cluster rather than in the
# database, so a database archive does not carry them. db/migrations/004_security.sql
# creates oro_api and door_reader, every row level security policy names one of
# them, and a restore into a cluster that has never heard of them fails on the
# first GRANT. It is written with --no-role-passwords, so it carries no hash for
# any role: the identity service's password comes from .env by way of
# db/init/001_identity_role.sql, and putting a copy of it in every backup would
# make each one a credential store as well as a member list.
#
# Where the files land, and how to change it:
#
#   ORO_BACKUP_DIR    default $HOME/oro-backups. Never inside this repository:
#                     an archive of the members database is member data, and
#                     rule 13 of CLAUDE.md says that never gets committed. A
#                     path inside the working tree is refused rather than
#                     ignored, because .gitignore is one `git add -f` away.
#   ORO_DB_CONTAINER  the container to read from. The default is the db service
#                     of the compose stack in this directory. The drill in
#                     tools/backup/tests/run.sh sets it to a throwaway
#                     container, so the drill exercises this script rather than
#                     a copy of it.
#
# Needs docker. The database publishes no port, on purpose, so the route in is
# a command inside the container, the same route make psql takes.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"

# compose.yaml sets POSTGRES_DB to oro, and the image's superuser is postgres.
# A connection made inside the container is trusted, which is why nothing here
# holds a password.
DATABASE=oro
SUPERUSER=postgres

DIRECTORY="${ORO_BACKUP_DIR:-$HOME/oro-backups}"
case "$DIRECTORY" in /*) ;; *) DIRECTORY="$PWD/$DIRECTORY" ;; esac

inside_the_repository() {
  case "$1" in
    "$ROOT"|"$ROOT"/*) return 0 ;;
    *) return 1 ;;
  esac
}

if inside_the_repository "$DIRECTORY"; then
  echo "backup.sh: $DIRECTORY is inside $ROOT, and no backup is written there." >&2
  echo "A dump of the members database is member data. Set ORO_BACKUP_DIR to a" >&2
  echo "path outside the working tree, or leave it unset for \$HOME/oro-backups." >&2
  exit 1
fi

CONTAINER="${ORO_DB_CONTAINER:-}"
if [ -z "$CONTAINER" ]; then
  CONTAINER="$(cd "$ROOT" && docker compose ps --quiet db 2>/dev/null || true)"
fi
if [ -z "$CONTAINER" ]; then
  echo "backup.sh: no database container is running, so nothing was backed up." >&2
  echo "Start the stack with make up and run this again. If the database runs" >&2
  echo "somewhere else, name its container in ORO_DB_CONTAINER." >&2
  exit 1
fi
# Messages name the container the way a person does. docker compose ps answers
# with 64 characters of hex, which tells a reader at 2am nothing about which
# stack they are looking at.
SHOWN="$(docker inspect --format '{{.Name}}' "$CONTAINER" 2>/dev/null | sed 's|^/||')"
if [ -z "$SHOWN" ]; then SHOWN="$CONTAINER"; fi

if ! docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc 'SELECT 1' >/dev/null 2>&1; then
  echo "backup.sh: the container $SHOWN is there but the $DATABASE database" >&2
  echo "did not answer, so nothing was backed up. make logs shows what the" >&2
  echo "database printed. Nothing was written." >&2
  exit 1
fi

# Every file this script creates, for the whole of this shell.
umask 077
mkdir -p "$DIRECTORY"
DIRECTORY="$(cd "$DIRECTORY" && pwd -P)"
if inside_the_repository "$DIRECTORY"; then
  echo "backup.sh: $DIRECTORY resolves inside $ROOT. Nothing was written there." >&2
  exit 1
fi
chmod 700 "$DIRECTORY"

TAKEN_AT="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$DIRECTORY/oro-$TAKEN_AT.dump"
ROLES="$DIRECTORY/oro-$TAKEN_AT.roles.sql"

# Written under another name and renamed at the end. A dump that was
# interrupted halfway is a file of the right shape and the wrong length, and
# the next person to reach for the newest archive would find it.
PARTIAL="$ARCHIVE.partial"
cleanup() { rm -f "$PARTIAL" "$PARTIAL.error" "$PARTIAL.toc" "$ROLES.partial"; }
trap cleanup EXIT

echo "reading the $DATABASE database out of container $SHOWN"
if ! docker exec -i "$CONTAINER" pg_dump -U "$SUPERUSER" -d "$DATABASE" \
     --format=custom > "$PARTIAL" 2>"$PARTIAL.error"; then
  cat "$PARTIAL.error" >&2
  rm -f "$PARTIAL.error"
  echo "backup.sh: pg_dump did not finish, and the error above says why." >&2
  echo "No archive was written. Nothing in the database was changed: pg_dump" >&2
  echo "only reads." >&2
  exit 1
fi
rm -f "$PARTIAL.error"

# Read back before the file is given its real name, because an archive nobody
# can open is not a backup and the cheapest moment to find that out is now.
# A throwaway container rather than the database's own, so this touches nothing
# that is serving the lab, and the archive goes in on a pipe so no copy of it is
# left on a filesystem anybody keeps.
if ! docker run -i --rm postgres:18 \
     sh -c 'cat > /tmp/verify.dump && pg_restore --list /tmp/verify.dump' \
     < "$PARTIAL" > "$PARTIAL.toc" 2>&1; then
  cat "$PARTIAL.toc" >&2
  rm -f "$PARTIAL.toc"
  echo "backup.sh: the archive that was just written cannot be read back, so it" >&2
  echo "was thrown away rather than kept. Read the error above, then run this" >&2
  echo "again. Nothing in the database was changed." >&2
  exit 1
fi

mv "$PARTIAL" "$ARCHIVE"
chmod 600 "$ARCHIVE"

if ! docker exec "$CONTAINER" pg_dumpall -U "$SUPERUSER" \
     --roles-only --no-role-passwords > "$ROLES.partial" 2>"$PARTIAL.error"; then
  cat "$PARTIAL.error" >&2
  echo "backup.sh: the database archive was written to $ARCHIVE, and the roles" >&2
  echo "beside it were not. A restore into a cluster that already has oro_api" >&2
  echo "and door_reader will work; one into an empty cluster will fail on the" >&2
  echo "first GRANT. Read the error above and run this again." >&2
  exit 1
fi
mv "$ROLES.partial" "$ROLES"
chmod 600 "$ROLES"

ENTRIES="$(grep -c '^[0-9]' "$PARTIAL.toc" || true)"
rm -f "$PARTIAL.toc"

echo "wrote $ARCHIVE"
echo "     $(wc -c < "$ARCHIVE" | tr -d ' ') bytes, $ENTRIES entries, read back before it was named"
echo "wrote $ROLES"
echo "     $(grep -c '^CREATE ROLE' "$ROLES" || true) roles, no passwords"
echo
echo "Restore it with: make restore FILE=$ARCHIVE"
echo "A backup nobody has restored is a hypothesis. The drill that restores one"
echo "is tools/backup/tests/run.sh, and docs/runbooks/restore-the-members-database.md"
echo "is what to follow at 2am."
