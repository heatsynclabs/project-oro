# Restore the members database

Follow this when the `oro` database is gone, or when what is in it is wrong and
an older copy is better. It assumes you did not build any of this.

Read these three things before step 1.

**The door is not waiting on you.** Physical cards open the door through the
legacy application, which this project does not touch until phase 5. Nothing in
this runbook makes the door work and nothing in it can stop the door working.
If somebody is locked out right now, that is a different problem and this is not
it.

**This restores one database and not the other.** The archive holds `oro`, which
is members, cards, roles and waivers. Passwords live in the `identity` database
beside it, which the identity service owns and which no command here reads or
writes. A restore brings the member rows back. It does not bring anybody's
password back.

**A restore replaces.** Every row now in `oro` is gone afterwards, and what
takes its place is what the archive holds. If the current database has anything
in it that the archive does not, stop and take a backup of the current one
first, at step 3.

---

## 1. Find the archives

```
ls -l $HOME/oro-backups
```

Expected: a pair of files for each backup, newest last.

```
-rw-------  1 you  staff  130404 Aug 28 21:52 oro-20260829T045220Z.dump
-rw-------  1 you  staff     778 Aug 28 21:52 oro-20260829T045220Z.roles.sql
```

The name is the moment the backup was taken, in UTC. The `.roles.sql` beside
each archive is part of it: it carries the database roles that the archive's
grants name, and the restore looks for it next to the archive by name. Move them
together or not at all.

If the directory is empty or missing, whoever set this host up pointed
`ORO_BACKUP_DIR` somewhere else. `grep ORO_BACKUP_DIR` in the crontab, the
systemd unit, or the shell profile of the account that takes the backups.

## 2. Check the stack is up

```
make ps
```

Expected: a line for `db` reading `Up` and `(healthy)`. The restore talks to the
database inside that container, so nothing works until this does.

If `db` is not there, `make up` first. If it comes up unhealthy, read
`db/init/001_identity_role.sql` and the note under `make up` in the `Makefile`
before doing anything else, because a database volume older than that file
cannot start.

## 3. Take a backup of what is there now

Do this even when you are sure the current database is worthless. It costs a few
seconds and it is the only way back if the archive from step 1 turns out to be
the wrong one.

```
make backup
```

Expected:

```
reading the oro database out of container oro-db-1
wrote /Users/you/oro-backups/oro-20260829T045220Z.dump
     130404 bytes, 305 entries, read back before it was named
wrote /Users/you/oro-backups/oro-20260829T045220Z.roles.sql
     3 roles, no passwords
```

Those numbers came from a database of twelve invented members, so yours will not
match them. What matters is that both lines say `wrote`, and that the first says
`read back before it was named`.
That phrase means the archive was opened again after it was written, so it is a
file somebody can restore rather than a file of the right size.

If `make backup` fails because the database will not answer, the current
database is already gone and there is nothing to save. Write down the error and
carry on to step 4.

## 4. Restore

Name the archive from step 1, with its full path.

```
make restore FILE=$HOME/oro-backups/oro-20260829T045220Z.dump
```

Expected, on a database with nothing in it:

```
/Users/you/oro-backups/oro-20260829T045220Z.dump reads back, 305 entries
/Users/you/oro-backups/oro-20260829T045220Z.roles.sql applied, every role it names is in the cluster
restoring into the oro database in container oro-db-1
restored: 12 members and 5 cards
and every card the legacy import carried is at the slot it had
```

The counts are the drill's, not the lab's. Check them against what you expect
the lab to have. A restore that reports far fewer members than the lab has is a
restore of the wrong archive, and step 3 is how you get back.

The last line is the one to read twice. A slot is an address in the door
controller's memory, so a card at a different slot is a member with somebody
else's door permission.

## 5. If it refuses because the database holds members

This is the ordinary case when the database is not empty. It looks like this,
and nothing has been changed when it appears:

```
restore.sh: this database already holds 12 member rows, and restoring
over it would replace every one of them. Nothing was changed.
It is the oro database in container oro-db-1.

If replacing them is what you want, say so by naming the count:

  make restore FILE=/Users/you/oro-backups/oro-20260829T045220Z.dump OVERWRITE=12-members
```

Read the count it names. If that is the database you meant to replace, run the
command it printed, exactly as printed. If the count is not what you expected,
you are pointed at a database you did not mean to touch, and the thing to change
is which stack you are in rather than the number.

## 6. Check what came back

```
make psql
```

Then, at the `oro=#` prompt:

```
SELECT count(*) FROM members;
SELECT legacy_id, controller_slot, tag_number FROM cards ORDER BY legacy_id;
\q
```

Expected: a member count that matches what the lab has, and a card list where
`controller_slot` equals `legacy_id` on every row that has a `legacy_id`. A card
issued after the migration has no `legacy_id`, and its slot is whatever the
admin who issued it chose.

## 7. When the restore refuses the archive

```
pg_restore: error: could not read from input file: end of file
restore.sh: ... is not an archive this can restore, and the error
above says why. Nothing was changed.
```

The archive is damaged or was never finished. The database has not been touched.
Go back to step 1 and use the archive before it.

If every archive you try reads back the same way, stop restoring and say so out
loud to whoever is awake. Backups that cannot be read have been failing for as
long as they have been unreadable, and that is a bigger problem than tonight's.

```
restore.sh: these roles are named by the archive's grants and are not
in this cluster: oro_api door_reader
```

The `.roles.sql` file is missing from beside the archive, or it was not carried
with it. Find it in `$HOME/oro-backups` under the same timestamp, put it back
next to the archive, and run step 4 again. The restore was not attempted, so
nothing has changed.

## 8. When you are done

Say in the lab's channel what you restored, which archive you used, and what the
member and card counts came out as. The next person needs to know the database
is not the one it was this morning.

---

## What this runbook does not cover

Backups are not on a timer yet and there is no offsite copy, so every archive is
on this one machine. `tools/backup/README.md` says what each of those would
take. Restoring the lab's production database onto a staging copy has not been
done, because nobody has a shell on that server yet, and until it happens the
first real restore will be the first one anybody has watched.
