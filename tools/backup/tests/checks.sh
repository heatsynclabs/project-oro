# The assertions the restore drill makes, and the two waits it needs. Sourced,
# not run:
#
#   . "$TESTS/checks.sh"
#
# It lives in its own file because tools/backup/tests/run.sh is the story of one
# drill from end to end and rule 6 of CLAUDE.md caps a file at 300 lines. What
# is here is the vocabulary that story is told in. Nothing in it knows anything
# about backups.
#
# The caller sets FAILURES to 0 before sourcing, and reads it afterwards. bad()
# is the only thing that changes it.

step() { echo; echo "== $1"; }
ok()   { echo "  ok    $1"; }
bad()  { echo "  FAIL  $1" >&2; FAILURES=$((FAILURES + 1)); }

must_say() {  # must_say FILE "text that has to appear"
  if grep -qF "$2" "$1"; then ok "said: $2"; else bad "never said: $2"; fi
}

must_not_say() {  # must_not_say FILE "text that must not appear"
  if grep -qF "$2" "$1"; then bad "said: $2"; else ok "never said: $2"; fi
}

# psql -tA and nothing else, so the output is data rather than a table drawing.
snapshot() {  # snapshot CONTAINER FILE
  docker exec -i "$1" psql -U postgres -d oro -tA -q -v ON_ERROR_STOP=1 \
    < "$TESTS/what_must_match.sql" > "$2"
}

unchanged() {  # unchanged CONTAINER FILE_TAKEN_BEFORE
  snapshot "$1" "$WORK/now.txt"
  if diff -u "$2" "$WORK/now.txt" > "$WORK/now.diff"; then
    ok "the database is exactly as it was before that attempt"
  else
    bad "the database changed during an attempt that should not have changed it"
    cat "$WORK/now.diff" >&2
  fi
}

members_in() {  # members_in CONTAINER
  docker exec "$1" psql -U postgres -d oro -tAc 'SELECT count(*) FROM members'
}

# The image runs a temporary server during initdb and then restarts it, so a
# single successful query can be answered by a server that is about to
# disappear. Two in a row, the way db/tests/run.sh waits. HANDOFF.md section 7,
# "pg_isready lies".
wait_for_postgres() {  # wait_for_postgres CONTAINER
  printf '  waiting for postgres'
  tries=0
  answered=0
  while [ "$answered" -lt 2 ]; do
    if docker exec "$1" psql -U postgres -d oro -tAc 'SELECT 1' >/dev/null 2>&1; then
      answered=$((answered + 1))
    else
      answered=0
    fi
    tries=$((tries + 1))
    if [ "$tries" -gt 90 ]; then echo " timed out"; exit 1; fi
    printf '.'
    sleep 1
  done
  echo " ready"
}

# Waits for a restore that may or may not still be running inside the container.
# Nothing on the host can see pg_restore there, so what gets watched is the
# connection it makes, which restore.sh names.
wait_for_the_restore_to_leave() {  # wait_for_the_restore_to_leave CONTAINER
  tries=0
  while [ "$(docker exec "$1" psql -U postgres -d oro -tAc \
             "SELECT count(*) FROM pg_stat_activity
               WHERE application_name LIKE 'oro-restore-%'")" != "0" ]; do
    tries=$((tries + 1))
    if [ "$tries" -gt 60 ]; then
      bad "a restore connection was still open a minute after it should have gone"
      return
    fi
    sleep 1
  done
}
