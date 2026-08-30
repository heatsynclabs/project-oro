# ADR 0014: restoring without touching a disk

- **Status:** proposed
- **Date:** 2026-08-29
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in it yet, and this record is not complete until a build lead signs it. It also touches that section's Secret custody row, because one option below hands the database password to a second process. That table names roles, not individual secrets.

## Context

`tools/backup/restore.sh` puts an archive back into the `oro` database inside
the `db` container. That archive is every member's name, address, phone number
and card, so wherever the restore leaves a working copy is a copy of the lab's
membership sitting somewhere until something removes it. Rule 13 of `CLAUDE.md`
is the whole reason this file has the shape it has: member data belongs to the
member, it does not get copied onto laptops, and it does not get left on a disk
nobody is watching.

An earlier version of this record opened by saying a copy has to exist, because
`pg_restore` seeks inside an archive and cannot read one on a pipe. That is
false. Re-measured on 2026-08-29 in `postgres:18`, `pg_restore` 18.6, with
`restore.sh`'s own flags and the archive arriving only over `docker exec -i`:

```
pg_restore -U postgres -d "dbname=dst user=postgres application_name=..." \
  --clean --if-exists --single-transaction < b.dump
```

Exit 0, and all 5000 rows came back. Inside the container `/proc/self/fd/0` was
a pipe, so the archive was never on a filesystem there.

Two narrower things are true, and something near them is what the first
measurement caught. Naming `/dev/stdin` as a file argument fails with
`pg_restore: error: did not find magic string in file header`, because a file
argument is opened and seeked rather than read forward. Asking for `-j` fails
with `pg_restore: error: parallel restore from standard input is not
supported`. The message the earlier version quoted, `could not read from input
file: end of file`, came back from neither, nor from an empty stdin, which
answers `input file is too short (read 0, expected 5)`. What produced it cannot
be recovered from what was written down, because the record kept the output and
not the command. `tools/backup/tests/run.sh` prints that same message on every
run, from an archive with its tail cut off. Neither limit stops the command
above.

The second half of this record is what happens when somebody stops a restore.
`docker exec` does not forward a signal to the process it started. Measured on
2026-08-29 against Docker 28.0.4: a `docker exec` client killed with SIGTERM
left `sh -c sleep 45` and its child still running in the container. An earlier
version of this script went on restoring and committing after the operator's
terminal had stopped printing, which is the failure `HANDOFF.md` section 2
records in the backup row.

These are one decision rather than two. A restore that keeps running after it
was stopped is also a restore whose copy of the members database nobody is left
to remove, so where the copy lands and what a stop does have to be answered
together.

## Options considered: where the archive lands

Priced by what each leaves of the members database at rest, and by which process
removes it.

### Option A: a bind mount from the host

- **What it is:** `$ORO_BACKUP_DIR` bound into the `db` service so `pg_restore`
  reads the archive where `backup.sh` already wrote it.
- **At rest:** nothing new. The archive is the file it already was, mode 600 in
  a mode 700 directory.
- **Cost:** a bind lives in `compose.yaml` and is therefore mounted for the life
  of the stack rather than for the length of a restore, which puts the whole
  backup history inside a long running container. It also cannot follow the
  operator: `restore.sh` takes a path as an argument and `ORO_BACKUP_DIR`
  is settable, so the mount would have to cover wherever the archives happen to
  be that night.

### Option B: `docker cp` into the container filesystem

- **At rest:** a full copy on the container's writable layer, which is on a
  disk, until a second command removes it.
- **Cost:** that removal is exactly the step a stopped restore skips, so the
  ordinary case of somebody changing their mind leaves the membership behind.
  It also rules itself out of the tmpfs answers below. `docker cp` reads the
  container filesystem and a tmpfs is not part of it: measured on 2026-08-29,
  copying out of `/dev/shm` answered `Could not find the file
  /dev/shm/probe.txt in container` while `docker exec cat` printed it.
  `HANDOFF.md` section 7 carries the same measurement from 2026-08-28, where it
  cost an hour on the identity bootstrap token.

### Option C: stream it on stdin and keep no copy

- **At rest:** nothing at all, which is why this was the first thing tried.
- **Cost:** `-j`, and nothing else this script can use. Parallel restore from
  standard input is refused, and `-j` is refused alongside
  `--single-transaction` in any case: `pg_restore: error: cannot specify both
  --single-transaction and multiple jobs`, measured on 2026-08-29 from a file,
  so the pipe is not what costs it. That single transaction is the whole of how
  a stopped restore rolls back, so parallelism was never on offer here.
- This option is already how both scripts read an archive back: it goes in on a
  pipe to a throwaway `postgres:18` container, which writes it to its own `/tmp`
  and dies with `--rm` a second later. Even that `/tmp` write is habit rather
  than need. `pg_restore --list` reading straight off the pipe exits 0. So does
  the `--schema-only --file=-` read that `roles_the_archive_needs.sh` makes.
  Both measured the same day.

### Option D: a tmpfs mount of its own on the `db` service

- **At rest:** memory, cleared when the container stops.
- **Cost:** a second memory backed mount beside the one every container already
  has, sized in `compose.yaml` the same way, existing on the service that serves
  the lab purely for the benefit of one script that runs a few times a year.

### Option E: `pg_restore` in a throwaway container over the compose network

- **At rest:** the writable layer of a container that Docker removes when the
  run ends, so nothing outlives the attempt even after a `kill -9`.
- **Cost:** the database password. The image's `pg_hba.conf`, read on
  2026-08-29, is `trust` for the local socket and for loopback and
  `scram-sha-256` for every other host, so a connection from another container
  is authenticated. `backup.sh` and `restore.sh` hold no password today because
  they run their commands inside the container, and rule 13 gives each secret
  that matters exactly one holder process. This option adds a second holder to
  save a copy that Option F already avoids.

### Option F: the container's own `/dev/shm`

- **At rest:** memory. Every container already has this mount and Postgres
  already uses it for parallel query workers, so nothing is added to
  `compose.yaml` except a size.
- **Cost:** the default is small. Measured on 2026-08-29, `df -Pk /dev/shm`
  inside `postgres:18` reports 65536 blocks of 1K, and the same image started
  with `--shm-size 256m` reports 262144. Postgres is also using some of it, so
  the space is shared.

## Options considered: what a stop does

### Option A: nothing beyond the `EXIT` trap that removes the copy

- **What it costs:** this is the version that failed. The trap fires on the
  host, the restore is a process in the container, and `docker exec` does not
  reach it. The operator sees their terminal stop and the database changes
  anyway.

### Option B: run `pg_restore` in the foreground and trap the signal

- **What was checked:** a POSIX shell runs a trap for a signal it caught only
  after the foreground command returns. Measured on 2026-08-29 with a five line
  script: `SIGTERM` was sent at second 2 of a 20 second `sleep`, and the trap's
  own line printed at second 20, in the same second the sleep finished.
- **What it costs:** for a restore, "after the foreground command returns" is
  after the restore has committed, so the handler runs too late to mean
  anything.

### Option C: name the connection and terminate that backend

- **What it is:** `pg_restore` connects with
  `application_name=oro-restore-<pid>`, the restore runs in the background and
  the script waits on it, and the handler for `INT`, `TERM` and `HUP` calls
  `pg_terminate_backend` over every backend carrying that name.
- **Why it works:** the archive is applied with `--single-transaction`, so
  ending the backend rolls the transaction back and the operator gets the
  database they had. `tools/backup/tests/what_a_restore_changes.sh` holds it
  there: it deletes rows, starts a restore, kills it part way, waits for the
  restore's connection to leave, and requires that the deleted rows are still
  gone.
- **What it costs:** it only catches signals a process can catch.

### Option D: something that also survives `kill -9`

- **What would be needed:** a watcher inside the container, since nothing on the
  host survives its own death. A sidecar or a supervising process that notices
  the client has gone and ends the backend for it.
- **What it costs:** a second long running thing beside the database, written
  here, to cover a case an operator has to go out of their way to produce. Rule
  8 says the bespoke code in this system should be the door service and nothing
  else.

## Decision

**Option F for the copy, and Option C for the stop.** The archive is streamed
into the container on stdin and written to `/dev/shm`, which is a tmpfs, and the
shell inside the container removes it after `pg_restore` returns whatever
`pg_restore` made of it. A catchable signal terminates the named backend, which
rolls the single transaction back.

Rule 13 eliminated Options B and E first, and that part still holds. One leaves
a file on a disk, the other hands the superuser password to a second process.
Between the two answers that keep the copy in memory, `/dev/shm` is the one that
adds no mount to a service that serves the lab.

**That argument only ever ran because Option C of the first list had been ruled
out, and it should not have been.** It is an argument about where a copy goes,
reached from a premise that a copy is needed. On the corrected measurement that
option wins on this record's own test: nothing at rest at all beats something in
memory. The
re-pricing found nothing in `tools/backup/` that the copy buys.
`roles_the_archive_needs.sh` opens the host file itself, in a throwaway
container of its own, and never sees the copy. Nothing reads the archive twice
inside the database container, asks its size there, or wants a file argument.
The free space check measures the archive against `/dev/shm` because that is
where the copy goes, so what it guards is the copy rather than the restore, and
with no copy there is nothing left for it to guard. The `kill -9` residue below
exists only to serve the copy. So does the part of the `shm_size` line in
`compose.yaml` that the restore drove, which is the 256 rather than the line: a
database container wants more than the Docker default of 64MB on its own terms,
and the comment beside it says so.

Option F is what `tools/backup/restore.sh` does today, and this record says so
because rule 10 asks a document to describe the code that exists. It is not what
this record would choose now. Changing the mechanism changes the restore path,
which `HANDOFF.md` section 2 puts under the first gate of rule 12, so it wants
its own diff, its own run of `tools/backup/tests/run.sh` and its own reader,
rather than riding in on a correction to prose.

Two things remove the copy and neither one covers the other's case. The shell
inside the container runs `rm -f` on the copy once `pg_restore` returns,
whatever `pg_restore` made of it, so the copy is not waiting on `restore.sh`
living long enough to clean up after itself. On the host, `cleanup()` on an
`EXIT` trap runs `docker exec ... rm -f` on the same path and then removes the
script's own temporary directory. The container shell's `rm` is what still runs
when the host script is killed outright. The `EXIT` trap is what covers the
path where the container shell never reaches its `rm`.

That path is one line. The copy is written with `cat > "$1" || exit 1`, so a
write that fails ends the shell above the `rm`, and what is left behind is as
much of the archive as fitted. Reproduced on 2026-08-29 in `postgres:18` run
with `--shm-size 1m`, feeding that same shell four million bytes: `cat: write
error: No space left on device`, status 1, and a 1048576 byte piece of the
archive on `/dev/shm` at mode 600. The `EXIT` trap in `restore.sh` is what takes
it away.

**`kill -9` is a real limit and it is written down rather than fixed.** A
restore ended that way runs on inside the container and probably commits. The
host's `EXIT` trap does not run, so the container shell's own `rm` is the only
removal left, and it reaches it unless the write of the copy was what failed.
That combination, a `kill -9` during a write that filled `/dev/shm`, leaves a
piece of the archive there until the container stops, which is the one thing a
tmpfs gives for free. Nothing in this repository catches `kill -9`, because
nothing can. It is recorded in the header of `restore.sh`, in
`tools/backup/README.md`, and in step 8 of
`docs/runbooks/restore-the-members-database.md`, which sends the operator to
read the member count back rather than guess.

`compose.yaml` now sets `shm_size: 256mb` on the `db` service. Docker's default
of 64MB is small for a database container on its own terms, and a restore reads
the free space there and refuses an archive that does not fit into it rather
than starting a write it cannot finish. The comment beside that line states the
assumption it rests on, that a custom format dump of the production database is
under 256MB, along with the command that confirms it and what happens if it is
wrong.

## The condition that would flip this

**It is met.** The condition was always whether `pg_restore` reads an archive on
a pipe, because that is the only thing the streaming option was rejected for,
and it does. The measurement is in the Context. What follows is what the flip is
worth,
measured on 2026-08-29 in `postgres:18` against an 8,238,131 byte archive of
300,000 rows fed over `docker exec -i`:

- Nothing killed: exit 0, 300,000 rows, three seconds end to end.
- The host client killed with `kill -9` a second and a half in: the stream is
  cut where the client died, `pg_restore` never reaches the end of the archive,
  and the single transaction rolls back. The database was left holding the five
  rows it held before, and no backend carrying the restore's `application_name`
  was left behind.

The second line is what makes this worth doing rather than merely tidy. Under
Option F a `kill -9` leaves a whole copy sitting on `/dev/shm`, and `pg_restore`
reads it to the end and commits, which is the limit the section above records
and does not fix. Streaming does not catch the signal either. It does not need
to: the operator's kill takes the restore with it, because the process that died
is the one feeding it.

That property has a floor and the floor should be stated. An archive small
enough to sit whole in the kernel's pipe buffers is handed over before it is
read, so killing the client afterwards changes nothing. The same test with a
21,296 byte archive, and `pg_restore` held back four seconds so the client would
certainly be dead first, committed all 5000 rows. A custom format dump of the
members database is far above that floor.

What the flip costs, priced before somebody takes it. `--clean` holds an
exclusive lock on every object it drops, and streaming holds those locks across
the transfer as well as the restore, where the copy finishes the transfer first.
Over a local `docker exec` both are the same few seconds. A host read that fails
part way would also fail inside the transaction rather than before it opens,
which rolls back either way and reads worse in the output.

Taking it means `restore.sh` passes no file argument and feeds `pg_restore` on
stdin. The `/dev/shm` path and the container shell's own `rm` go. The free space
refusal goes with them, and so does the `shm_size: 512m` line it prints, leaving
`compose.yaml` to keep `shm_size` for Postgres's own sake at whatever number
Postgres wants. The check that the copy is really gone belongs in the drill,
which already holds a restore part way by taking a lock the first statement
needs: while that lock is held, `ls /dev/shm` in the container has to show no
archive. Today it shows one, because `cat > "$1"` finishes before `pg_restore`
opens.

If the copy stays, the older condition stands underneath it. A custom format
dump of the production database that needs enough of `/dev/shm` that Postgres
cannot get the shared memory it wants alongside it makes Option D correct: a
tmpfs mount of its own, sized for the restore, so the two are not competing for
one number. Check that by running `pg_dump -Fc` on hsl-web, reading the size,
and comparing it against what the host running the stack can give a container.

## Consequences

- A restore now depends on a line in `compose.yaml`. A stack brought up from a
  checkout older than that line has the 64MB of `/dev/shm` measured under
  Option F above, against the 256MB the line gives it.

  ```
  ASSUMPTION: a custom format dump of the production members database is over
  64MB, so a stack on the Docker default refuses it.
  CONFIRM BY: pg_dump -Fc on hsl-web and read the size of the file, which is
  the same command the comment beside shm_size in compose.yaml asks for.
  BLAST RADIUS: whether a stack on the default can restore at all. The refusal
  names what to do either way, so nobody is left guessing.
  ```

- The refusal names the file, the service and a line to add, and the line it
  names is `shm_size: 512m` while this record and `compose.yaml` both say
  `256mb`. They should not differ. An operator who does what the refusal says
  ends up with a stack that does not match the decision written here, and the
  next person to read `compose.yaml` finds a number nobody chose. The line that
  prints it is the `echo "  shm_size: 512m"` in the space refusal in
  `tools/backup/restore.sh`, line 231 as this record is written.
- The refusal happens before `pg_restore` runs, so no row is replaced and no
  table is dropped. It does not happen before the database is touched. By the
  time the space is checked, `restore.sh` has created the `oro` database if it
  was missing, and `tools/backup/roles_the_archive_needs.sh` has applied the
  roles file beside the archive to the cluster. A refusal on space leaves both
  of those behind.
- The copy is in memory, so it is readable by root on the host and by anything
  that can enter the container while the restore runs. It is not readable after
  the container stops, and that is the property being bought.
- Stopping a restore is safe to do and the runbook says so plainly. What it is
  not is instant: the backend has to be terminated and its lock released before
  the database answers normally again, which is why the drill waits for the
  restore's connection to leave before it compares anything.
- Reversing either half is small. The copy's location is one variable in
  `restore.sh` and the size line in `compose.yaml`. The signal handling is one
  trap and the background `wait`, and the test that would catch a reversal
  already exists.
- The `shm_size: 512m` the refusal prints is downstream of a rejection that
  should not have happened. So are the 256MB assumption block and the free space
  check that runs only after the database has already been created. Whoever
  takes the flip above deletes them rather than repairing them, so repairing
  them first is work with a short life. What is worth doing either way is the
  correction to the comment beside `shm_size` in `compose.yaml`, which tells a
  reader that `restore.sh` refuses before it touches the database. It does not.

## What was borrowed

Nothing. No code or design is taken from another project here. The measurements
are of `postgres:18` and Docker 28.0.4, both run unmodified.

## Open questions

- Whether `/dev/shm` on the lab's server behaves the way it does on the machine
  these were measured on. Every measurement here is Docker 28.0.4 on macOS,
  where the containers run inside a Linux virtual machine, and a Linux host
  gives its containers shared memory out of the same pool the database is
  competing for. Resolve by running the drill once on hsl-web.
- What a restore does when `/dev/shm` fills part way through rather than being
  too small at the start. The check compares the archive against free space
  before it begins, and nothing watches that space afterwards. Resolve by
  starting a restore and filling `/dev/shm` from a second shell.
- Whether Postgres's own use of `/dev/shm` grows during a restore of a large
  archive, which would make the space check optimistic by however much. Resolve
  by reading `df` inside the container while a restore of a production sized
  archive runs.
