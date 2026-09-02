# What is actually on hsl-web

Step 1 of `docs/runbooks/deploy-beside-the-legacy-system.md` says to run a list
of read only commands and write the answers down, and until now it did not say
where. Here. Nothing in this file changes anything on that machine.

Read on **2026-08-31** and **2026-09-01**, as root over ssh. Every line below
came back from a command rather than from a document, and where a number is
quoted it is the number that machine printed. Three secrets came back with it
and none is written here: see the last section.

The headline is that this host cannot run the stack this project builds, and
that is not a detail of the runbook. It is a decision nobody has taken yet.

---

## The machine

```
CentOS release 6.8 (Final)
Linux hsl-web.hsl.dn42 2.6.32-642.15.1.el6.i686 i686 i386
```

Thirty two bit, on a 2017 kernel. CentOS 6 stopped receiving updates in
November 2020.

| Thing | Answer |
|---|---|
| Architecture | `i686`, so 32 bit |
| Kernel | 2.6.32 |
| Distribution | CentOS 6.8, out of support |
| Docker | Absent, and not installable. Docker needs `x86_64` and kernel 3.10 or newer, and this host is neither |
| Disk, `/` | 9.1G, 88% used, **1.1G free** |
| Disk, `/srv` | 139G, 98% used, **3.3G free** |
| Memory | 2908 MB total, 244 MB free, 3812 MB swap |

## What serves the members site

Apache with Phusion Passenger, not nginx.

```
apache  Passenger RackApp: /srv/web/members.heatsynclabs.org
root    /usr/sbin/httpd
```

| Thing | Answer |
|---|---|
| Web server | `httpd`, holding `:::80` and `:::443` |
| Application server | Passenger, in process |
| Checkout | `/srv/web/members.heatsynclabs.org` |
| Site configuration | `/etc/httpd/conf.d/members.heatsynclabs.org.conf` and `ssl.conf` |
| Rails | 3.2.8 |
| Devise | 2.2.7 |

`/etc/httpd/` holds three configuration directories: `conf.d`, `conf.d.bak` and
`conf.d.20250411`. Only `conf.d` is the live one. Somebody should say what the
other two are before anything touches that server.

## The database

```
PostgreSQL 8.4.20 on i386-redhat-linux-gnu, 32-bit
```

**8.4, not 9.6.** It reached end of life in July 2014.

| Database | Size |
|---|---|
| `members` | **520 MB** |
| `members_vac_test` | 185 MB |
| `members_development` | 6032 kB |
| `members_test` | 5192 kB |

`members` is the one. Nobody has said what `members_vac_test` is, and 185 MB of
it is sitting on a disk with 1.1G free.

## What phase 2 turns on, and it is good news

The two values read off the file this machine actually runs, rather than off the
sources this project was given:

```
82:  config.stretches = Rails.env.test? ? 1 : 10
85:  # config.pepper = "..."
```

**No pepper, and cost 10 in production.** That is what
[ADR 0004](../decisions/0004-identity-service.md) assumed and said still wanted
confirming, and it is confirmed. The lab's password hashes can be imported as
they are.

Two things to carry forward from that line rather than from the summary of it.
Cost is 10 everywhere except the test environment, which uses 1, so a row
written by a test run carries a different prefix. Phase 2 already asks for the
distribution of cost prefixes to be reported before anybody signs in, and that
is the reason.

And there is a pepper value present, commented out. `rails generate
devise:install` writes that line commented with a random value, so the most
likely reading is that it is the generator's default and was never active. It
is worth settling rather than assuming, because a hash written while a pepper
was active cannot be told from one written without it:

```
cd /srv/web/members.heatsynclabs.org && git log -p --follow config/initializers/devise.rb | grep -n pepper
```

If that line was ever live and then commented out, the members whose hashes were
written in that window already cannot sign in to the legacy application either,
because Devise applies the pepper on the way in as well as on the way out. So
they would have reset their password years ago, and any peppered hash still in
that table belongs to somebody who has not signed in since. It does not block
the import and it is worth knowing the size of.

## The time zone, also confirmed

```
30:    config.time_zone = 'America/Phoenix'
```

Nothing in `config/application.rb` sets `config.active_record.default_timezone`,
so it is `:utc` and Rails 3.2 stores UTC. The import reads every naive timestamp
`AT TIME ZONE 'UTC'` on exactly that basis, and `HANDOFF.md` section 7 records
what happens to seven columns when it does not.

## Mail

The lab already has a working sender, which answers most of step 8 of the deploy
runbook.

| What step 8 asks for | What hsl-web is using |
|---|---|
| The host and its port | `smtp.gmail.com`, port 465, which is implicit TLS rather than the STARTTLS of 587 |
| The user | A Google mailbox on `heatsynclabs.org`, with an app password |
| The address messages come from | The same mailbox |
| Whether it accepts replies | Unknown. Nobody has asked |

Whether the new system should send through that mailbox is a decision rather
than a reading. It is one credential shared by two systems, and Zitadel's SMTP
configuration takes a `tls` boolean whose meaning against port 465 has not been
measured.

## Things nobody asked for and everybody should know

**The door controller's address and password are in
`/srv/web/members.heatsynclabs.org/config/config.yml`**, in plain text, for all
three environments. Anything that can reach that address and holds that value
opens the building. That is a fact about the system this project replaces, not
about this project, and it is the reason
[ADR 0004](../decisions/0004-identity-service.md) and `CLAUDE.md` rule 13 put
the controller password behind exactly one holder process.

**Postgres and MySQL both listen on every interface**, `*:5432` and `*:3306`,
rather than on loopback. The members database is reachable from the network.

**`config/s3.yml` sits beside `config.yml` and `database.yml`.** Nobody has
opened it. If it holds keys for an object store, that is a third credential on
that host and it is in the configuration archive with the other two.

## The backup, taken on 2026-09-01

It was taken. This is the first copy of the lab's members database this project
has ever held, and the first evidence anybody has that one can be taken at all.

Nothing was written to a disk on hsl-web. Everything was staged in `/dev/shm`,
which is a 1.5G tmpfs and was completely empty, then copied off and cleared.
`df` on `/` and `/srv` read the same before and after, 1.1G and 3.3G free.

| Artifact | Size | What it is |
|---|---|---|
| `members-*.dump` | 36 MiB | `pg_dump --format=custom members`. The restorable one |
| `whole-cluster-*.sql.gz` | 62 MiB | `pg_dumpall` gzipped. Every database and every role, in plain SQL, which restores into any Postgres |
| `globals-*.sql` | 802 B | The roles alone, with an md5 hash per login role |
| `app-config-*.tar.gz` | 13 KiB | The application's whole `config` directory |
| `httpd-*.tar.gz` | 47 KiB | Apache, all three of its configuration directories |
| `tls-*.tar.gz` | 847 KiB | The certificate and its private key |
| `manifest-*.txt` | 527 B | A row count per table, read in the same sitting |

A 520 MB database compresses to 38,143,322 bytes, which settles the assumption
`compose.yaml` states where it sets `shm_size`. That number is 256MB and the
archive is a seventh of it. Sizes here are what the files measure rather than
what `du -h` rounded them to on the far side, which said 37M for the one that is
36 MiB.

**Two open questions closed by taking it.**

`pg_restore` 14.18 reads the archive `pg_dump` 8.4.20 wrote. Its header says
`Dump Version: 1.11-0` and `TOC Entries: 149`, 16 of them table data. Nobody had
established that this would work, and it is not a given: the same `pg_restore`
refuses an archive from `pg_dump` 18 with `unsupported version (1.16) in file
header`, outright and immediately. So the window has a hard edge, 1.11 is inside
it and 1.16 is outside, and `pg_restore --list` is how anybody checks in a
second.

And there are no member uploaded files. The whole application is 73 MB, of which
`public` is 3.2 MB, `.git` is 12 MB and `log` is 55 MB. Nothing under it holds
member uploads, so nothing is missing from the backup on that account. `/srv`
itself is 128 GB used, and the application is 73 MB of that, so something else on
that volume accounts for 127 GB and nobody has said what.

## What the members database holds

Read on 2026-09-01, in the same sitting as the dump, one count per table.

| Table | Rows | Table | Rows |
|---|---|---|---|
| `users` | 1061 | `door_logs` | 2868091 |
| `cards` | 64 | `mac_logs` | 191967 |
| `payments` | 8291 | `macs` | 4277 |
| `paypal_csvs` | 11825 | `contracts` | 318 |
| `user_certifications` | 415 | `resources` | 165 |
| `certifications` | 10 | `resource_categories` | 27 |
| `toolshare_users` | 27 | `ipns` | 103 |
| `settings` | 6 | `schema_migrations` | 52 |

1061 members and 64 cards. Those two numbers are what phase 2 and phase 3 are
actually sized against, and until now every estimate in this repository was
written without them.

`door_logs` at 2.87 million rows is the one to think about before the migration
runs: it is two orders of magnitude larger than anything else here, and
`docs/plan/order-of-operations.md` phase 3 lists door events as still not
migrated.

## Where the backup is, and what is wrong with that

One copy, in a plain directory on a laptop, on a disk with **FileVault off**.
Checked on 2026-09-01. Time Machine has no destination configured and the
directory is not one iCloud Drive syncs, so the plaintext has not propagated
anywhere, and a lost laptop hands over 1061 members' password hashes, addresses,
phone numbers and emergency contacts, along with the door controller password.

The script that took it lives on that same laptop and is not in this repository
either, so the only working backup procedure the lab has is one copy of one file
on one machine. Both of those want fixing and neither is fixed.

## What this blocks

**The deploy runbook assumes Docker on hsl-web and there is no way to get it.**
Step 3 installs it, and steps 5 through 11 all run containers. On a 32 bit
CentOS 6 kernel none of that is available, and there is no repository to upgrade
from. So the stack runs somewhere else: the lab's R610, a new virtual machine,
or a rented box. `docs/plan/architecture.md` already requires the stack to be
portable across exactly those, so nothing about the architecture changes. What
changes is that a machine has to be found and named, and that is a person's
decision in the shape `docs/plan/people-and-custody.md` describes.

**Gate one of rule 12 cannot be met on this host either.** A backup is takeable
with `pg_dump`, which is on the machine. Reading it back is not: step 2 restores
into a throwaway container, this host has no containers, and there is not room
on `/` for a second 520 MB copy inside the running Postgres. So the backup can
be taken today and the restore that makes it a backup rather than a file waits
on the same decision.

One measured detail for whoever does that restore: the oldest official Postgres
image on Docker Hub is 9.1, checked on 2026-08-31, so an 8.4 archive cannot be
read back into its own major version from an image. A much newer `pg_restore`
reading an 8.4 archive is the only route, and it wants proving before anybody
relies on it.

## The two secrets that came back with this

Neither is written down here, and neither should be written into this
repository.

1. **The Gmail app password** for the mailbox above. It was read out of
   `config/config.yml` and shown on a terminal, so treat it as exposed. It is
   revocable in a couple of minutes from the Google account it belongs to, and
   replacing it costs one line in that file.

2. **The door controller password.** Also in `config/config.yml`, also exposed.
   This one does not get rotated on impulse: the same value lives in the
   controller, and changing one side without the other stops the door. It is a
   thing to change on a day when somebody is standing at the controller, and
   rule 12 puts the door above every phase of this project.
3. **Whatever `config/s3.yml` holds**, which nobody has opened. Read it before
   deciding it does not matter. It is in the configuration archive either way.
