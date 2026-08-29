#!/bin/sh
# Put the roles an archive's grants name into a cluster, and refuse if any of
# them is still missing afterwards.
#
#   tools/backup/roles_the_archive_needs.sh ARCHIVE CONTAINER
#
# Roles belong to a Postgres cluster rather than to one database, so a database
# archive cannot carry them, and a restore into a cluster that has never heard
# of them fails on the first GRANT. backup.sh writes them to a file beside the
# archive for that reason, under the same timestamp.
#
# What gets checked is what the ARCHIVE names, not what the file names. No
# policy in db/migrations names a role: every one of them defaults to PUBLIC.
# What needs the roles is the grants. db/migrations/004_security.sql lines 144
# to 147 and 173 to 174 grant to oro_api, line 160 grants to door_reader, and
# line 172 makes door_reader own a function. Checking that the roles the file
# names exist passes a roles file taken from a different cluster, because such a
# file names its own roles, creates them, and leaves the ones the grants name
# missing.
#
# Needs docker. Exit code is 1 when a role is missing, and at that point nothing
# has been restored.

set -e

ARCHIVE="$1"
CONTAINER="$2"
if [ -z "$ARCHIVE" ] || [ -z "$CONTAINER" ]; then
  echo "roles_the_archive_needs.sh: name the archive and the container." >&2
  echo "tools/backup/restore.sh is what calls this." >&2
  exit 1
fi

# compose.yaml sets POSTGRES_DB to oro, and the image's superuser is postgres.
DATABASE=oro
SUPERUSER=postgres

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ROLES="${ARCHIVE%.dump}.roles.sql"
if [ -f "$ROLES" ]; then
  # Not ON_ERROR_STOP. Every role that already exists reports an error here and
  # that is the ordinary case: a cluster that has been up for a minute already
  # has postgres. What matters is the state afterwards, which is read out of the
  # archive below rather than out of this file.
  docker exec -i "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -q \
    < "$ROLES" > "$WORK/roles.out" 2>&1 || true
  echo "$ROLES applied"
else
  echo "no roles file beside the archive"
fi

# A throwaway container, so nothing here touches the database serving the lab.
docker run -i --rm postgres:18 \
  sh -c 'cat > /tmp/archive.dump && pg_restore --schema-only --file=- /tmp/archive.dump' \
  < "$ARCHIVE" > "$WORK/schema.sql" 2>"$WORK/schema.err" || true
# pg_dump writes one GRANT and one OWNER TO per line. PUBLIC is not a role and
# is never created.
sed -n -e 's/^GRANT .* TO \(.*\);$/\1/p' -e 's/^ALTER .* OWNER TO \(.*\);$/\1/p' \
    "$WORK/schema.sql" \
  | tr ',' '\n' | sed 's/^ *//; s/ *$//; s/^"//; s/"$//' \
  | grep -v '^PUBLIC$' | sort -u > "$WORK/needed"

MISSING=""
while read -r role; do
  [ -n "$role" ] || continue
  found="$(docker exec "$CONTAINER" psql -U "$SUPERUSER" -d "$DATABASE" -tAc \
           "SELECT count(*) FROM pg_roles WHERE rolname = '$role'" 2>/dev/null || echo 0)"
  if [ "$found" = "0" ]; then MISSING="$MISSING $role"; fi
done < "$WORK/needed"

if [ -n "$MISSING" ]; then
  echo >&2
  echo "restore.sh: this archive grants privileges to roles that are not in this" >&2
  echo "cluster:$MISSING" >&2
  echo "The restore was not attempted, because it would fail on the first GRANT." >&2
  echo "Nothing was changed." >&2
  echo >&2
  if [ -f "$ROLES" ]; then
    echo "$ROLES was applied and those roles are still not here, so it belongs to" >&2
    echo "a different cluster. What psql made of it:" >&2
    sed 's/^/  /' "$WORK/roles.out" >&2
  else
    echo "There is no roles file beside the archive. backup.sh writes one under" >&2
    echo "the same timestamp, and the restore looks for it here:" >&2
    echo "  $ROLES" >&2
    echo "Find it in the backup directory, put it back next to the archive, and" >&2
    echo "run the restore again." >&2
  fi
  exit 1
fi

echo "the archive's grants name $(wc -l < "$WORK/needed" | tr -d ' ') role(s), and this cluster has all of them"
