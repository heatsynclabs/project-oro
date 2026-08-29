# Backups of the members database

Two commands and a drill. `make backup` writes an archive of the `oro` database
outside this working tree, `make restore FILE=...` puts one back, and
`tools/backup/tests/run.sh` proves the pair by backing a database up, destroying
it, restoring it, and checking that what came back is the same database.

Rule 12 of `CLAUDE.md` puts one thing above every phase of this project: a
verified, restorable backup of the production members database, proven onto a
staging copy. `docs/plan/order-of-operations.md` phase 0 item 3 asks for the
timer, the offsite copy and the drill, and says that a backup nobody has
restored is a hypothesis.

What is here is the local half, and it proves the mechanism rather than the
lab's data. Two things named in that plan are not built, and the last section of
this file says what each would take.

## How to run it

```
make backup
```

Two files land in `$ORO_BACKUP_DIR`, which defaults to `$HOME/oro-backups`:

```
oro-20260828T204500Z.dump        the database, pg_dump custom format
oro-20260828T204500Z.roles.sql   the roles the database's grants name
```

The directory is created mode 700 and both files mode 600. A path inside this
repository is refused rather than written and ignored, because an archive of the
members database is member data and `.gitignore` is one `git add -f` away from
not covering it.

The second file exists because a role belongs to the Postgres cluster rather
than to one database, so a database archive does not carry it.
`db/migrations/004_security.sql` creates `oro_api` and `door_reader`. No policy
names either of them, and none of the forty three policies in `db/migrations`
names any role at all: they default to `PUBLIC`. What needs the roles is the
grants. Lines 144 to 147 and 173 to 174 of that file grant to `oro_api`, line
160 grants `SELECT ON cards` to `door_reader`, and line 172 makes `door_reader`
own a function. A restore into a cluster that has never heard of them fails on
the first `GRANT`, so the restore checks for them first, reading the grants out
of the archive rather than reading the file beside it. A roles file carried over
from a different cluster names its own roles and passes a check of itself.

The roles file is written with `--no-role-passwords`, so no backup is also a
credential store.

```
make restore FILE=$HOME/oro-backups/oro-20260828T204500Z.dump
```

Into an empty database that is the whole command, and it is also the whole
command when the `oro` database itself has been dropped: `pg_dump` was not given
`--create`, so the archive carries the contents of a database and not the
database, and the restore creates an empty one before it starts. Over a database
that still holds members it refuses, and prints the command that goes ahead:

```
make restore FILE=... OVERWRITE=12-members
```

The count in that flag has to match the number of members in the database being
replaced. A yes or no flag would survive being copied out of a runbook or pulled
back out of a shell history, and this does not: against any other database it
refuses again and prints that database's own count. `make` reads it only when it
was typed on the command line. An `OVERWRITE` exported into a shell is refused
with a message saying so, because a confirmation nobody can see in the command
they ran is not a confirmation.

The archive goes into the database container on `/dev/shm`, which is a tmpfs,
and the shell that runs `pg_restore` removes it whether `pg_restore` worked or
not. Rule 13 of `CLAUDE.md` is the reason for both: a copy of the archive is a
copy of the lab's membership, and a copy removed only by a trap in `restore.sh`
survives a `kill -9`, a dropped ssh session and a reboot. On a tmpfs it is in
memory rather than on a disk, and removing it is the job of a process the
operator's terminal cannot kill. Docker gives a container 64MB of `/dev/shm` by
default, so an archive larger than what is free there is refused with the line
to add to `compose.yaml` rather than a copy half written.

A restore that is stopped part way stops. `docker exec` does not pass a signal
to the process it started, so `restore.sh` names the connection `pg_restore`
makes and, on ctrl-c or a `kill` or a dropped ssh session, terminates that
backend. The archive runs inside one transaction, so what the operator gets back
is the database they had. `kill -9` is the exception, because nothing catches
it, and the restore then runs on to the end inside the container.

`docs/runbooks/restore-the-members-database.md` is the version to follow at 2am,
with the expected output at every step.

## How to test it

```
tools/backup/tests/run.sh
```

The drill, and it is the reason this directory exists. It starts a throwaway
Postgres, loads the ORO schema and runs the real legacy import into it, takes a
backup with the same script `make backup` runs, and then removes the container
so the cluster is gone. What is left is the archive. It starts a new container,
restores into it, and compares the result against what it saw before. Faithful
here means every table's row count, every card's slot and tag, every live role,
every sequence value, every policy, and the roles the archive's grants name.
Every one of those lists is sorted to a primary key, because two rows a sort
leaves tied come back from a restore in either order and the comparison is made
line by line. It then runs
`tools/migration/030_verify.sql` against the restored database, so the
assertions the migration already makes are the assertions the restore has to
survive, and the two cannot drift apart.

The other half of the drill is in `what_a_restore_changes.sh`, which run.sh
calls. It restores over a database that holds members and requires a refusal,
gives the wrong count and requires another, and then deletes rows so that the
restore which does go ahead has something to put back. That matters: a restore
of an archive into the database the archive came from writes the rows already
there, so a check on the exit code alone passes whether the restore ran or not.
Between the damage and the repair it starts a restore, kills it part way, and
requires that the deleted rows are still gone once the restore's own lock has
cleared. Then it feeds the restore an archive cut in half, an archive missing
its last bytes, and a text file somebody renamed, and finally drops the `oro`
database outright and restores into a cluster that no longer has one. After
every refusal it takes the comparison again and requires that nothing moved.

Before any of that, back in `run.sh`, the archive is offered to a cluster that
has never heard of `oro_api` or `door_reader`, once with the roles file left
behind and once with a roles file belonging to a different cluster, and both
have to be refused before the database is touched. The confirmation is checked
too: `make -n` shows that a count typed on the command line reaches `restore.sh`
and that one exported into the environment does not.

Measured on 2026-08-28: an archive cut in half is refused when it is read back,
before the database is opened at all, and one missing only its last bytes gets
past that and is rolled back by the transaction the restore runs inside. Both
leave the database exactly as it was.

The suite is a check on itself as well. With `--exclude-table-data=cards` added
to the `pg_dump` line, so that the backup silently loses the card table, the
drill goes red twice: the comparison reports `table public.cards 5 rows` against
`0 rows` and the five slot lines missing, and `030_verify.sql` refuses the
restored database with `5 legacy card(s) did not arrive`.

## What it depends on

Docker, and nothing else. Every Postgres command runs inside a container.

- `postgres:18`, the image `compose.yaml` runs, for `pg_dump`, `pg_dumpall`,
  `pg_restore` and `psql`. Reading an archive back uses a throwaway container of
  that image so nothing touches the database that is serving the lab.
- The `db` service of the compose stack in this directory, found with
  `docker compose ps --quiet db`. The database publishes no port on purpose, so
  the route in is a command inside the container, which is the route `make psql`
  takes. `ORO_DB_CONTAINER` names a different container, and the drill uses it
  to point these scripts at its own.
- `db/migrations`, `db/seed` and `tools/migration` for the drill only. It builds
  its database by running the real import over the invented fixture in
  `tools/migration/fixtures`.

## What is not built

**No timer.** Nothing runs `make backup` on a schedule. That is a line in a
crontab or a systemd timer on whatever host the stack ends up on, and the host
is not decided. Whoever sets it up should point `ORO_BACKUP_DIR` at a path with
room and prune old archives there, because nothing here deletes anything.

**No offsite copy.** `docs/plan/order-of-operations.md` names restic to an S3
compatible endpoint, and `docs/plan/architecture.md` section 3 requires the
endpoint be nameable in a variable rather than tied to one provider account. It
needs a bucket with credentials, and a named person holding them, per
`docs/plan/people-and-custody.md`. None of those exist yet, so restic is not a
dependency of this repository and there is no ADR choosing it: writing one now
would be pricing a decision nobody can act on. When the credentials exist, rule
8 wants three alternatives priced before the tool lands.

Until then the archives sit on one machine, which means a fire in the lab takes
the backups with the server.

**No proof against the lab's own data.** Phase 0 item 5 is a verified restore of
the production database onto a staging copy, and it is blocked on a shell on the
lab's server. The drill proves that the mechanism works. It says nothing about
what the lab's rows do when they meet it, and the first restore of the real
database will find things the fixture cannot.
