# Deploy beside the legacy system

Follow this to put Project ORO next to the members application it will replace,
and to take the first real backup of the members database. It assumes you did
not build any of this, and that you have ssh as root on hsl-web.

**Steps 3 onward cannot run on hsl-web, and that is now measured rather than
suspected.** That host is 32 bit CentOS 6.8 on a 2.6.32 kernel, so Docker is not
merely absent, it is not installable, and every step from 3 to 11 runs
containers. Steps 1 and 2 do not, and they are the two that matter first: the
survey and the backup. Everything after them waits on a machine that can run the
stack, which is a decision nobody has taken.
`docs/plan/hsl-web-survey.md` has the readings and what each one costs. Read the
rest of this document as written for that machine once it exists, with the
legacy application still on hsl-web.

Read these five things before step 1.

**The door is not waiting on you, and nothing here can stop it.** A physical
card is matched against a table in the Arduino's own memory with no network
involved, and the legacy Rails application is the only thing that writes that
table. Neither is touched anywhere in this document. If the door stops working
while you are following this, it stopped for some other reason, and this is not
the runbook for it. Rule 12 of `CLAUDE.md` puts that above every phase, so if
you find yourself about to type something that could reach the controller or
the legacy application's card screens, stop instead.

**hsl-web has been seen once, on 2026-08-31.** Seven things this document used
to guess at have answers below, and three of them came back differently from the
guess. Run step 1 again anyway on whatever machine you are standing in front of,
because the answers below are that host on that day and one of them has already
changed the work rather than being a detail.

**No copy of the members database goes onto your laptop.** Rule 13. Every
command below runs on hsl-web through your ssh session, and the table after the
assumptions lists where each copy lives and what removes it. If you catch
yourself typing `scp`, stop.

**What you have at the end, and what you do not.** After step 10 hsl-web runs an
identity service, a Postgres holding a migrated copy of the members data, and a
members API answering under `/v1` on a new hostname. There is no portal. The
deployment's routes serve a health check and the members API, with a 404 at the
root, so there is no page for a member to open. A member sees no change at all,
on purpose. The gaps at the end list the rest of what is missing.

**The blocks below are not from hsl-web,** apart from the answers in the
assumption section and in `docs/plan/hsl-web-survey.md`. They come from a laptop,
on 2026-08-30 and 2026-08-31, against a Postgres 9.6 container standing in for
the legacy database, on a machine where another stack already held the ports.
The container names, the hostname and the port numbers are written as the ones
this guide chooses. Nothing else in them is edited, and the counts you see are
twelve invented members rather than the lab's.

---

## What was assumed, and what the machine said

Step 1 was run against hsl-web on 2026-08-31 and every assumption below has an
answer now. `docs/plan/hsl-web-survey.md` holds the readings in full. Four came
back as assumed, three did not, and one of those three stops this document
where it stands.

```
ANSWERED: the legacy members application and its Postgres both run on hsl-web.
  Apache with Passenger serves /srv/web/members.heatsynclabs.org and Postgres
  listens on the same host.

WRONG: that Postgres is 9.6. It is 8.4.20, on i386, which reached end of life
  in July 2014. The --no-role-passwords workaround in step 2 is still the right
  one, because that flag arrived in Postgres 10 and 8.4 is further from it, not
  nearer. What it also means is that the read back in step 2 cannot use a
  matching image: the oldest official Postgres on Docker Hub is 9.1, checked on
  2026-08-31.

ANSWERED: something on hsl-web holds ports 80 and 443. httpd holds both.

WRONG, AND IT STOPS THIS DOCUMENT: Docker is not installed on hsl-web, and it
  cannot be. The host is i686 on kernel 2.6.32, and Docker needs x86_64 and
  kernel 3.10 or newer. CentOS 6.8 has been out of support since November 2020,
  so there is no repository to upgrade from either. Step 3 installs Docker and
  steps 5 through 11 all run containers, so this runbook cannot be followed on
  this machine. Steps 1 and 2 can, and they are the ones that matter first.

WRONG: the dump is not known to be under 256MB. The members database is 520 MB
  on disk. A custom format archive is compressed and will be smaller, and
  nobody has measured it, so step 2 measures it before writing it.

ANSWERED: the legacy application's checkout is on hsl-web with its config on
  disk, at /srv/web/members.heatsynclabs.org. The two values everything
  downstream is built on came back as this project assumed: no pepper, and
  config.stretches is 10 outside the test environment. The Rails time zone is
  America/Phoenix for display and nothing sets the record timezone, so it is
  UTC, which is what the import reads.

WRONG: hsl-web has no room for container images. / is 88% full with 1.1G free
  and /srv is 98% full with 3.3G free. Even were Docker available, the three
  images this stack pulls come to more than that.
```

## Where every copy of the members database lives

Rule 13 asks for this to be written down rather than reconstructed later.

| Copy | Where it is | What removes it |
|---|---|---|
| Production | The legacy Postgres on hsl-web | Nothing here. It is never written to |
| The archive | `/root/hsl-legacy-backups` on hsl-web, mode 600 inside a mode 700 directory | You do, by hand. Nothing else will |
| The roles file beside it | The same directory. On 9.6 it carries password hashes until step 2 strips them | The same |
| The configuration archive | The same directory. It carries `database.yml` and the session secret | The same |
| The staging copy | Inside the `oro-staging` container, which has no volume | `docker rm -f oro-staging` at the end of step 9, which takes the rows with it |
| The `legacy` schema | Inside whichever database the import ran against | `DROP SCHEMA legacy CASCADE`, which the import itself tells you to run |
| The imported members | The `db_data` volume of the ORO stack, once step 10 puts them there | `docker compose down --volumes` |
| Your terminal | The preflight and the import print member names and email addresses | Closing it. Do not redirect that output into a file, and never paste it into a channel |

---

## 1. Find out what is on hsl-web

Nothing in this step changes anything. Run all of it and keep the answers. Do
not start step 2 until you have them.

These blocks say what to read in the answer rather than quoting a run, because
none of these commands has been run on hsl-web. Where a command is missing the
machine says `command not found`, and the alternatives are named beside it.

**What the machine is.**

```
uname -a
cat /etc/os-release
```

Read: the distribution and the kernel. Everything below assumes Linux with a
package manager. A `docker compose` plugin has to exist for that distribution
before step 3 is possible at all.

**What holds port 80 and port 443.**

```
ss -lntp
```

If `ss` is not there, try `netstat -lntp`. Failing that,
`lsof -i -P -n | grep LISTEN`.

Read: one line per listener, with the process name in the last column. The two
lines that matter are `:80` and `:443`. Whatever holds them is the thing this
deployment has to coexist with, and its name decides how step 4 reads. Write
down the process rather than only the port.

**What the existing application is.**

```
systemctl list-units --type=service --state=running
ps aux | grep -Ei 'ruby|rails|passenger|unicorn|puma|nginx|apache|httpd'
```

Read: which of those is serving `members.heatsynclabs.org`. The application is
Rails 3.2.8, so expect it behind a web server rather than answering the port
itself. If any of it is in Docker, the next command says so and the commands in
step 2 change shape.

**Whether Docker is there.**

```
docker --version
docker compose version
docker ps
```

Read: two version lines and a table. If the first says `command not found`,
step 3 has to install it, and that is a change to this machine. If Docker is
there and `docker ps` lists the legacy application, then step 2 reads the
database through `docker exec` rather than through `sudo -u postgres`.

**What the application is configured with.** Two values in the Rails checkout
decide things this project has already built on, and neither has been read from
this machine. Find the checkout first:

```
ls -d /var/www/* /srv/* /home/*/* 2>/dev/null | head -20
ps aux | grep -Ei 'ruby|rails|passenger|unicorn|puma' | head -3
```

Read: the directory holding `config/`, `app/` and `Gemfile`. Set it once:

```
APP=/the/path/you/found
grep -nE 'config\.(pepper|stretches)' $APP/config/initializers/devise.rb
```

Read: whether `config.pepper` is commented out, and the number in
`config.stretches`. Answered on 2026-08-31, and the answer is the one this
project needed: pepper commented out, stretches `Rails.env.test? ? 1 : 10`.
Read it again anyway on whatever machine you are standing in front of, because
a hand edit on a host is invisible everywhere else and that is the whole reason
this step exists. **If a pepper is set, stop.** Every hash in that database was
made with a secret this project does not have, none of them can be imported as
they are, and that changes phase 2 rather than being a detail.

```
grep -nE 'time_zone|default_timezone' $APP/config/application.rb
```

Read: `config.time_zone`, and whether anything sets
`config.active_record.default_timezone`. The import reads every naive timestamp
`AT TIME ZONE 'UTC'` on the basis that Rails 3.2 stores UTC and the zone in that
file is only for display. If something there sets the record timezone to
`:local`, every migrated date moves seven hours and the check that would catch
it is written against the other answer.

```
grep -vE 'password|secret' $APP/config/database.yml
ls $APP/config/initializers/
```

Read: the adapter, the host, the database name and the user. **Do not paste that
file anywhere, even after the grep.** A `database.yml` is a credential file, and
so is anything under `config/initializers/` named for a secret.

**Which file serves the members site.**

```
grep -rl 'members.heatsynclabs.org' /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null
```

Read: one path, most likely. Nothing in this document changes it. Write it down
anyway, because step 13's rollback claims it was never touched and that claim is
worth being able to check.

**Where the database is and what version it is.**

```
sudo -u postgres psql -c 'select version()'
sudo -u postgres psql -c '\l+'
```

Read: the first prints one line naming the major version, which the assumption
above says is 9.6. The second lists every database on the server with its size,
and one of them is the members database. Write down its name. This guide calls
it `members` from here on and yours may be called something else.

If `sudo -u postgres` is refused, the Postgres is probably in a container and
the form is `docker exec CONTAINER psql -U postgres -c 'select version()'`.

**How much room there is.**

```
df -h
free -m
```

Read: free space on whichever filesystem holds `/var/lib/docker` and `/root`.
The images alone are about 1GB, and you are about to write the dump twice, once
as an archive and once as rows inside a container.

**Whether the two names resolve.**

```
getent hosts oro.heatsynclabs.org
getent hosts id.oro.heatsynclabs.org
```

Read: nothing, most likely, because neither record exists yet. That is fine for
everything up to step 10 and it is not fine for step 11. Phase 0 item 4 of
`docs/plan/order-of-operations.md` asks for these records, and whoever controls
the zone is a name nobody has filled in. Until they exist you reach this
deployment with `curl --resolve` or with a line in your own machine's hosts
file, and no member can reach it at all.

## 2. Take the backup, and read it back

This is gate one of rule 12, the thing every phase of this project sits above,
and it has never been done. Everything in this step reads. `pg_dump` takes no
lock that blocks the application and writes nothing to the database.

**`make backup` cannot do this, and it is better to know now than at the
prompt.** `tools/backup/backup.sh` is built and proven, and it is hardcoded to
a database named `oro` inside a container. Pointed at anything else it refuses,
measured on 2026-08-31:

```
backup.sh: the container oro-legacy96 is there but the oro database
did not answer, so nothing was backed up. make logs shows what the
database printed. Nothing was written.
```

So the production backup is `pg_dump` typed out. Three other things differ from
the database that tool was built against. The legacy schema has no foreign key
constraints anywhere, so nothing in it enforces that a card points at a member
who exists. It is a major version this project does not run, so the archive is
read back by a newer `pg_restore` than the one that wrote it. And its cluster
roles carry passwords, which is the paragraph after next.

Make somewhere for it to go, on hsl-web:

```
mkdir -p /root/hsl-legacy-backups
chmod 700 /root/hsl-legacy-backups
ls -ld /root/hsl-legacy-backups
```

Expected: `drwx------` and root.

Take the archive:

```
umask 077
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
sudo -u postgres pg_dump --format=custom members > /root/hsl-legacy-backups/members-$STAMP.dump
```

Expected: nothing at all. `pg_dump` is silent when it works. If the database is
in a container the middle line becomes
`docker exec CONTAINER pg_dump -U postgres --format=custom members >` the same
path.

Then look at it:

```
ls -l /root/hsl-legacy-backups
```

Expected: one file, mode `-rw-------`, owned by root.

```
-rw------- 1 root root 8975 Aug 31 01:36 members-20260831T013647Z.dump
```

**Read the size and compare it against 256MB.** That number is the assumption
in `compose.yaml` beside `shm_size`, and this is the moment it stops being one.
Under 256MB, nothing to do. Over it, raise `shm_size` in `compose.yaml` before
any restore, because `tools/backup/restore.sh` refuses an archive that does not
fit and its refusal names that line.

Now the roles. A database archive does not carry them, because a role belongs
to the cluster rather than to one database, and a restore into a cluster that
has never heard of them dies on the first `GRANT`.

```
sudo -u postgres pg_dumpall --roles-only --no-role-passwords > /root/hsl-legacy-backups/members-$STAMP.roles.sql
```

On Postgres 9.6 that flag does not exist, measured on 2026-08-31:

```
/usr/lib/postgresql/9.6/bin/pg_dumpall: unrecognized option '--no-role-passwords'
```

It arrived in Postgres 10. So on 9.6 the roles come out carrying an md5
password hash for every login role, which makes that file a credential store as
well as a list of names:

```
CREATE ROLE hslweb;
ALTER ROLE hslweb WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS PASSWORD 'md51ed1d468e6f84fc00ede9fc73f1fce1c';
```

Take it without the flag and strip the passwords yourself:

```
sudo -u postgres pg_dumpall --roles-only \
  | sed -e "s/ PASSWORD '[^']*'//" \
  > /root/hsl-legacy-backups/members-$STAMP.roles.sql
grep -c PASSWORD /root/hsl-legacy-backups/members-$STAMP.roles.sql
```

Expected: `0`. Measured on 2026-08-31, that `sed` leaves the role and every one
of its attributes and removes only the password clause:

```
ALTER ROLE hslweb WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS;
```

If the count is anything other than 0 the file holds a live credential. Delete
it and do not go on until the strip works.

**Back up the configuration as well, because it is not in this repository
either.** The database is what matters and it is not the only thing that would
have to be reconstructed. `$APP` is the path from step 1:

```
umask 077
tar -czf /root/hsl-legacy-backups/legacy-config-$STAMP.tar.gz \
  "$APP/config" /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null
ls -l /root/hsl-legacy-backups/legacy-config-$STAMP.tar.gz
```

Expected: one file, mode `-rw-------`. `tar` prints a warning for each of those
`/etc` paths that does not exist, which is why the error output goes away, and
it still archives the ones that do.

**That archive holds credentials.** `database.yml` carries the database
password and `secret_token.rb` or `secrets.yml` carries the session secret,
which is why it lives in the mode 700 directory beside the dump and why it does
not go on your laptop. Rule 13. It is on the list at the top of this document
for the same reason.

**Read the archive back before you believe in it.** A backup nobody has opened
is a file of the right size.

```
pg_restore --list /root/hsl-legacy-backups/members-$STAMP.dump | head -14
```

Expected: a header naming the database, the entry count and both versions.

```
;
; Archive created at 2026-08-31 01:36:47 UTC
;     dbname: members
;     TOC Entries: 24
;     Compression: gzip
;     Dump Version: 1.13-0
;     Format: CUSTOM
;     Integer: 4 bytes
;     Offset: 8 bytes
;     Dumped from database version: 9.6.24
;     Dumped by pg_dump version: 9.6.24
;
```

If that errors, the archive is damaged or was never finished. Take it again
rather than carrying on.

**A backup nobody has restored is a hypothesis, so restore it.** This is phase
0 item 5, and it wants a copy rather than the original. Step 9 restores it into
Postgres 18 while building the staging copy. Do it once here as well, into the
same major version the archive came from, because that is the restore you would
actually perform if production were gone. It needs Docker, so if step 1 said
Docker is absent, come back to this after step 3.

```
docker run -d --name oro-restore-check -e POSTGRES_PASSWORD="$(openssl rand -base64 24)" postgres:9.6
```

Wait for it, and wait for it twice. The Postgres image runs a temporary server
during first initialisation and then restarts it, so the first answer you get
can come from a server that is about to disappear:

```
ready=0; i=0
while [ $i -lt 90 ]; do
  if docker exec oro-restore-check psql -U postgres -d postgres -tAc 'SELECT 1' >/dev/null 2>&1
  then ready=$((ready+1)); [ $ready -ge 2 ] && break
  else ready=0
  fi
  i=$((i+1)); sleep 2
done
echo "answered twice after $((i*2)) seconds"
```

Expected: `answered twice after 8 seconds`, or thereabouts. Skipping this is how
you get `terminating connection due to administrator command` in the middle of a
restore that looked like it had started.

```
docker exec -i oro-restore-check psql -U postgres -d postgres < /root/hsl-legacy-backups/members-$STAMP.roles.sql
docker exec oro-restore-check psql -U postgres -d postgres -c 'CREATE DATABASE members'
docker exec -i oro-restore-check pg_restore -U postgres -d members --exit-on-error --single-transaction < /root/hsl-legacy-backups/members-$STAMP.dump
```

Expected: the roles file reports exactly one error, and it names `postgres`.

```
ERROR:  role "postgres" already exists
```

That is the superuser the fresh container already has, so it is the one role
that cannot be created again. Any other name in that message is a role that
failed for some other reason and wants reading. `CREATE DATABASE` prints
`CREATE DATABASE`. The restore prints nothing and exits 0.

Now compare the copy against the original, table by table. On production:

```
sudo -u postgres psql -d members -tAc "SELECT string_agg(format('SELECT %L AS t, count(*) FROM public.%I', c.relname, c.relname), ' UNION ALL ' ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'" | sudo -u postgres psql -d members -tA -F' '
```

On the copy:

```
docker exec oro-restore-check sh -c "psql -U postgres -d members -tAc \"SELECT string_agg(format('SELECT %L AS t, count(*) FROM public.%I', c.relname, c.relname), ' UNION ALL ' ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'\" | psql -U postgres -d members -tA -F' '"
```

Expected: two identical lists. Ours were:

```
cards 8
users 12
```

Every table and every count has to match. If one does not, the archive is not a
backup of that database, and nothing downstream of here is worth doing.

Take the check container away, and the copy with it:

```
docker rm -f oro-restore-check
```

Expected: `oro-restore-check`. That container had no volume, so removing it
removes every row it held.

**Write down what you did**: the archive name, the two counts and the date.
Gate one of rule 12 is now met for the first time in this project, and the
evidence for it is that comparison rather than the fact that a command ran.

## 3. Put this repository on hsl-web

Only now does anything on the machine change.

If step 1 said Docker is absent, installing it is a decision rather than a
paste. Docker writes firewall rules of its own, and a published port can be
reachable from outside even when the host firewall was told to refuse it. Do
not take that on trust either way:

```
ASSUMPTION: publishing a port on this host makes it reachable from the lab
  network whatever the host firewall says.
CONFIRM BY: after step 5, from a second machine, try to reach hsl-web on the
  ORO HTTPS port and on 5432, and see which answers.
BLAST RADIUS: a members database on a port anybody on the network can reach.
  This stack publishes no database port, which is what makes the check cheap
  rather than frightening.
```

Clone and configure:

```
cd /opt
git clone https://github.com/heatsynclabs/project-oro.git
cd project-oro
git config core.hooksPath .githooks
cp .env.example .env
chmod 600 .env
```

Expected: a clone, and no output from the rest. `/opt` rather than a home
directory, because the next person to hold this machine has to find it.

Now fill in `.env`. Every value in it is documented in the file itself and
nothing has a default. Four are secrets you generate here and keep:

```
openssl rand -base64 24     # ORO_DB_PASSWORD
openssl rand -base64 24     # ORO_IDENTITY_DB_PASSWORD
openssl rand -hex 24        # ORO_API_DB_PASSWORD, hex because it goes in a URL
openssl rand -hex 16        # ORO_IDENTITY_MASTERKEY, exactly 32 bytes
```

`ORO_IDENTITY_ADMIN_USERNAME` and `ORO_IDENTITY_ADMIN_PASSWORD` are the first
administrator of the identity service. That password is a handover rather than
a credential: the account is made to change it at first sign in.

**Back up `ORO_IDENTITY_MASTERKEY` somewhere other than beside the database
dump.** Lose it and the identity database cannot be read, which takes every
member's password with it. Section 3 of `people-and-custody.md` says where
secrets are supposed to live and names nobody, so until it does, write this one
on paper and put it in the lab safe.

The remaining values are what step 4 decides.

## 4. Choose the ports, the names and the certificate

Both stacks want a web port and only one of them can have 80 and 443. The
existing one keeps them. It is serving members today and this one serves
nothing anybody uses yet, so the whole of the coexistence is that ORO binds a
different pair:

```
ORO_HOSTNAME=oro.heatsynclabs.org
ORO_TLS=internal
ORO_HTTP_PORT=8080
ORO_HTTPS_PORT=8443
```

Use whatever pair step 1 showed to be free. Nothing else changes on either
side, and nothing on the legacy side is reconfigured. That is the property
worth protecting: the way back from all of this is to stop one set of
containers.

**The hostname.** A new name rather than `members.heatsynclabs.org`, which
stays with the legacy application until phase 6. The identity service takes
`id.` under whatever this is set to, so these two lines settle two DNS records.

**Set the name and the port once and mean it.** The identity service publishes
an issuer built from both, and everything it signs carries that issuer.
Measured on 2026-08-31 on a stack recreated first with a different port and
then with a different hostname: the discovery document followed both, and the
old name stopped answering. So moving them later is survivable and it is not
free. Clients registered by `tools/identity/configure.py` hold the origins they
were given, and re-registering them is another run of that script.

**A port other than 443 stops the members API accepting tokens.** This is the
one thing in the stack that a beside deployment breaks, and it is worth reading
twice. The identity service builds its issuer from the hostname, the port and
the scheme, so on 8443 it issues `https://id.oro.heatsynclabs.org:8443`.
`compose.api.yaml` builds `ORO_API_TOKEN_ISSUER` as `https://id.` and the
hostname with no port, and states the assumption in a comment where it does it.
Measured on 2026-08-31 on a stack running on a non standard port, the two
strings were:

```
what the identity service signs:  https://id.oro.heatsynclabs.org:8443
what the API was told to expect:  https://id.oro.heatsynclabs.org
```

The stack comes up healthy either way, because the API's healthcheck is a call
with no token that has to come back 401, and it does. What fails is every call
carrying a real token, answered 401 with `token refused: Invalid issuer` in the
API log. Nothing routes a member to that API yet, so today this costs nothing.
It has to be settled before anybody signs in, and settling it is a change to
`compose.api.yaml` rather than to `.env`.

**The certificate comes from Caddy's own authority, and no browser trusts it.**
That is what `internal` means. Measured:

```
*  issuer: CN=Caddy Local Authority - ECC Intermediate
*  start date: Aug 31 01:42:27 2026 GMT
*  expire date: Aug 31 13:42:27 2026 GMT
*  SSL certificate verify result: unable to get local issuer certificate (20)
```

A publicly trusted certificate is not available while the legacy system holds
the standard ports. `.env.example` records that an ACME issuer needs the
hostname to resolve from the internet with port 80 reachable, and port 80 is
taken. The other route is a DNS challenge, and the `caddy:2-alpine` image this
stack runs carries no DNS provider: measured on 2026-08-31, it lists 134
modules and not one of them is a `dns.providers` module. So a public
certificate here means building a different Caddy image, or waiting for
cutover, which is when the ports come free. For a parallel run that only the
build lead and a cohort of volunteers reach, `internal` is the honest setting,
and a browser interstitial is what it costs.

**One hazard, measured, with no fix in configuration.** Caddy cannot see the
port mapping, so its redirect from plain HTTP names the standard port:

```
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://hsl-web:8080/health
308 https://oro.heatsynclabs.org/health
```

On this machine that redirect lands on the legacy application over 443. Reach
this deployment on the HTTPS port directly and never on the HTTP one, and say
so to anybody else you give the link to.

## 5. Start the stack beside the existing one

```
cd /opt/project-oro
make up
```

Expected: compose pulls three images and builds one the first time, then six
lines. The wait allows 300 seconds because the identity service applies its own
schema and seeds an instance before it answers anything.

```
 Container oro-identity_bootstrap-1  Exited
 Container oro-schema-1  Exited
 Container oro-identity-1  Healthy
 Container oro-caddy-1  Healthy
 Container oro-db-1  Healthy
 Container oro-api-1  Healthy
```

`Exited` and healthy at the same time is right. `identity_bootstrap` makes a
volume writable and stops. `schema` puts the members schema into the stack's
own database and stops.

```
make ps
```

Expected: six rows, four of them `Up ... (healthy)`. The database, the identity
service and the API publish no port. Only Caddy does.

```
NAME                       SERVICE              STATUS                 PORTS
oro-api-1                  api                  Up (healthy)           8000/tcp
oro-caddy-1                caddy                Up (healthy)           0.0.0.0:8080->80/tcp, 0.0.0.0:8443->443/tcp
oro-db-1                   db                   Up (healthy)           5432/tcp
oro-identity-1             identity             Up (healthy)           8080/tcp
oro-identity_bootstrap-1   identity_bootstrap   Exited (0)
oro-schema-1               schema               Exited (0)
```

Read what the schema service said, because it is the only record that the
database was built:

```
docker compose logs schema
```

Expected, on a first start:

```
schema-1  | applying 000_migrations.sql
...
schema-1  | applying 001_reference.sql
schema-1  | The schema and the reference data are in.
schema-1  | oro_api_login is created, so the members API can log in.
```

On every later start it says the schema is already there and no migration was
applied. That is correct and it is also its whole limit: it is not a migration
runner, it records nothing about which files ran, and a migration written after
the database was built will not be applied by it.

Ask the deployment four questions. Until the DNS records exist, `--resolve` is
how you reach a name the machine does not know, and `-k` is because of the
certificate.

```
curl -sk --resolve oro.heatsynclabs.org:8443:127.0.0.1 https://oro.heatsynclabs.org:8443/health
```

Expected: `ok`.

```
curl -sk --resolve oro.heatsynclabs.org:8443:127.0.0.1 -w '\n%{http_code}\n' https://oro.heatsynclabs.org:8443/
```

Expected, and the 404 is correct rather than a fault:

```
Project ORO is running. No application is deployed here yet.
404
```

```
curl -sk --resolve oro.heatsynclabs.org:8443:127.0.0.1 -o /dev/null -w '%{http_code}\n' https://oro.heatsynclabs.org:8443/v1/me
```

Expected: `401`. That is the members API, refusing a call that carries no
token, which means the request reached it and it reached the database to be
refused by it. A `404` here means Caddy answered instead and the API is not
routed.

```
curl -sk --resolve id.oro.heatsynclabs.org:8443:127.0.0.1 https://id.oro.heatsynclabs.org:8443/.well-known/openid-configuration
```

Expected: a JSON document whose first field is the issuer, carrying the name
and the port from step 4.

```
{"issuer":"https://id.oro.heatsynclabs.org:8443","authorization_endpoint":...
```

If that answers `Instance not found. Make sure you got the domain right`, the
request arrived under some other name. The identity service works out which
instance a call is for from the Host header, so `127.0.0.1` on the right port
is refused, and it reads like a routing fault when it is not.

## 6. Register the clients

`compose.yaml` creates the instance, its administrator and one machine account,
and that is the whole of what a compose file can create. Everything above it is
written by one step: the project, the three portal clients, the door service
account, the lab's colours on the sign in screens, and the sign up button.

Until this has run there is no client id for anything to sign in with, and no
token the identity service issues can carry the audience `compose.api.yaml`
gives the members API, so every call to `/v1` with a real token comes back 401.
Step 8 hands people sign ins, and without this they can sign in to nothing.

It is idempotent. A second run reads back what the first one wrote and reports
every line as already there. Run it again whenever the hostname or the port in
step 4 changes, because each client holds the origin it was given.

**The name has to resolve on this machine.** The identity service works out
which instance a request is for from the Host header, so an address is not a
substitute for the name, and unlike `curl` this step has no `--resolve`. Until
the DNS records exist, one line in `/etc/hosts`:

```
127.0.0.1 oro.heatsynclabs.org id.oro.heatsynclabs.org
```

```
getent hosts id.oro.heatsynclabs.org
```

Expected: `127.0.0.1 id.oro.heatsynclabs.org`. Take that line out again once
the zone has the records, so this machine and everybody else resolve the name
the same way.

**Python has to trust the certificate.** `internal` in step 4 means Caddy
issued it from its own authority, which nothing on this machine trusts. The
`curl -k` above skips the question and no Python here does. So copy the
authority's own root out of the container and name it:

```
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt \
  /root/oro-caddy-root.crt
openssl x509 -in /root/oro-caddy-root.crt -noout -subject
```

Expected, measured on 2026-08-31:

```
subject=CN=Caddy Local Authority - 2026 ECC Root
```

That verifies against the authority rather than skipping verification, so a
certificate from anywhere else still fails. Without it the step stops on
`CERTIFICATE_VERIFY_FAILED` and says so.

**Run it.**

```
SSL_CERT_FILE=/root/oro-caddy-root.crt \
ORO_IDENTITY_URL="https://id.oro.heatsynclabs.org:8443" \
ORO_IDENTITY_TOKEN="$(docker compose cp identity:/bootstrap/pat - | tar -xO)" \
  tools/identity/configure.py \
    --members-origin https://oro.heatsynclabs.org:8443 \
    --admin-origin https://admin.oro.heatsynclabs.org:8443 \
    --door-origin https://door.oro.heatsynclabs.org:8443
```

Not `make identity-configure`. That target builds the three origins from
`ORO_HOSTNAME` with no port on them, and step 4 chose a port. A client
registered without the port refuses the redirect the browser comes back on, and
the member sees the sign in screens reject the application rather than anything
that names the cause.

Expected on a first run. These lines come from a laptop, so the port in them is
8453 rather than the 8443 step 4 chose:

```
project Project ORO: created
Members portal: created
Members portal: signs in at https://id.oro.heatsynclabs.org:8453, written to apps/members/identity.json
Admin portal: created
Door app: created
door-service: created
branding: colours, mark and light theme applied and activated
mail: no server given, so nothing can send a code. Registering, a forgotten password and a changed address all stop at a screen asking for one. Pass --mail-host to fix that.
self registration: already on

configured against https://id.oro.heatsynclabs.org:8453
```

Two lines in that are worth reading rather than skipping.

`self registration: already on` says the step found the Register button on
rather than turning it on, because a fresh instance ships with it on. Step 8 is
where that becomes a decision.

`mail: no server given` is correct here. Mail is step 8 and it is set up by
hand, and this step is deliberately not the thing that points a deployment at a
mail server.

A second run says `already there` and `already correct` on every line and
writes nothing:

```
project Project ORO: already there
Members portal: already correct
Admin portal: already correct
Door app: already correct
door-service: already there
```

The one file it writes into the checkout is `apps/members/identity.json`,
carrying the client id the identity service generated. There is no portal on
this deployment so nothing reads it here, and it is written because the same
command serves a laptop that does have one.

## 7. Check that nothing on the old side moved

Do this now, while it is cheap to undo. Run it from a second machine rather
than from hsl-web.

```
curl -sI https://members.heatsynclabs.org/ | head -3
```

Expected: the same status line the legacy application gave before you started.
Somebody should have written that down during step 1. If it changed, take this
stack down with `make down` and read step 12.

```
ss -lntp
```

Expected: the listeners from step 1 unchanged, plus the two Caddy binds. None
of the legacy application's ports has moved.

Then ask a member to open the members site and say whether it looks normal.
That costs a message, and it is the only check here that reads the thing a
member actually sees.

## 8. Decide about mail, and prove whichever way you go

The identity service sends nothing, and it does not say so. It accepts the
request, answers 200, and writes the reason into its own log. The screens are
worse than the API. Measured on 2026-08-31, following Reset Password on the
sign in screen gave the member this:

```
Password Reset Link Sent
Check your email to reset your password.
```

while the service wrote this:

```
level=error msg="could not create email channel"
  error="ID=QUERY-fwofw Message=Errors.SMTPConfig.NotFound"
```

So this is a decision rather than a step anybody can skip past. Take it here,
while no member has been given a sign in yet and nothing depends on the answer.

**What is unavailable until somebody configures a mail server.** Every one of
these is measured, and `tools/identity/README.md` holds the measurement:

1. A member cannot reset a forgotten password. The screen tells them a link is
   on its way. An admin sets a new one for them instead, through the identity
   service.
2. A member cannot verify a new address after changing it, so the address on
   their account is the one an admin recorded.
3. The Register button is on and cannot be finished, because a registration
   lands in `USER_STATE_INITIAL` waiting for a code. A person who presses it
   is stuck on Activate User, and an admin has to remove that account and make
   them a sign in, per item 4. Step 6 turned the button on, because this site
   replaces one that has a sign up. If you are not configuring mail today, the
   branch below is where you take it away again.
4. An account that is already in `USER_STATE_INITIAL` cannot be repaired at
   all. Every write to it is refused. The only route is to remove it and make
   a new one, which is what
   `tools/identity/make_a_sign_in.py --repair ADDRESS --remove-and-recreate`
   does, and it costs the member their identity subject.

Everybody's sign in is made by an admin either way:

```
SSL_CERT_FILE=/root/oro-caddy-root.crt \
ORO_IDENTITY_URL="https://id.oro.heatsynclabs.org:8443" \
ORO_IDENTITY_TOKEN="$(docker compose cp identity:/bootstrap/pat - | tar -xO)" \
  tools/identity/make_a_sign_in.py "Ada Byron <ada@example.org>"
```

Expected: three lines, and a password on the terminal that is in no file. Run
it from a terminal or it refuses before it creates anything.

The first two lines are the ones step 6 set up, and every Python command in
this document that speaks to the identity service needs both. Without
`ORO_IDENTITY_URL` the default is a port on `localhost` that only a laptop
publishes, and without `SSL_CERT_FILE` the certificate from step 4 is one
nothing trusts.

### If you are not configuring one today

**Close the sign up first.** This is the part that has to happen rather than
be written down. The Register button is on, and behind it is the one state no
admin can repair: a person who presses it lands in `USER_STATE_INITIAL`, the
screens ask for a code, nothing can send one, and every write to that account
is refused from then on. So a deployment that cannot send mail should not be
offering the button.

```
SSL_CERT_FILE=/root/oro-caddy-root.crt \
ORO_IDENTITY_URL="https://id.oro.heatsynclabs.org:8443" \
ORO_IDENTITY_TOKEN="$(docker compose cp identity:/bootstrap/pat - | tar -xO)" \
  tools/identity/configure.py \
    --members-origin https://oro.heatsynclabs.org:8443 \
    --admin-origin https://admin.oro.heatsynclabs.org:8443 \
    --door-origin https://door.oro.heatsynclabs.org:8443 \
    --self-registration off
```

The same command as step 6 with one flag on the end, because it is one
idempotent step and running it twice is what it is for. Everything else in it
reports itself already correct.

Expected, on the last line before the summary:

```
self registration: turned off
```

Then read the screen a person would arrive at, because the policy is the
mechanism and the button is what anybody meets. The client id is in the file
step 6 wrote:

```
CLIENT=$(python3 -c 'import json;print(json.load(open("apps/members/identity.json"))["client_id"])')
curl -sk -L -c /tmp/oro-jar -b /tmp/oro-jar \
  "https://id.oro.heatsynclabs.org:8443/oauth/v2/authorize?client_id=$CLIENT&redirect_uri=https%3A%2F%2Foro.heatsynclabs.org%3A8443%2F&response_type=code&scope=openid&code_challenge=Ab_cdefghijklmnopqrstuvwxyz0123456789ABCDEFG&code_challenge_method=S256" \
  | grep -c 'name="register"'
rm -f /tmp/oro-jar
```

Expected: `0`. Measured on 2026-08-31 against 4.17.1 on a laptop, both ways:
`1` with the sign up open and `0` with it closed. A `1` here means the button
is still there and the command above did not take. Somebody who wants an
account now asks an admin, which is the command above this branch.

The cookie jar is not decoration. The authorize request is bound to a cookie,
and without one the screens answer 200 and render an internal error, so the
grep would read `0` and say the button was gone when the request never got as
far as a screen. `code_challenge` is any 43 character string: nothing here
completes the sign in.

**Then write the decision down** where the answers from step 1 are, with the
date and the name of whoever made it. The four things above stay unavailable,
and the next person to stand in front of this deployment needs to know that
was a decision rather than an oversight.

When a mail server does arrive, the sign up comes back with the same command
and `--self-registration on`, which is the default.

Then go to step 9.

### If you are configuring one

Ask whoever holds the lab's mail for four things. None of them is guessable
and none of them is in this repository, so do not fill any of them in from
memory.

| What to ask for | What a good answer looks like |
|---|---|
| The host and its port | A name and a port together, in one string, as `smtp.example.org:587`. 587 is the usual submission port and expects STARTTLS, which is the `tls` field below. 465 is the older implicit TLS port |
| The user and password | Credentials for a mailbox or a relay the lab already owns. Never a volunteer's personal account: it leaves with them |
| The address messages come from | An address on a domain the lab controls, and one that will still exist in three years. A member replying to a password reset should reach somebody |
| Whether that address accepts replies | If it does not, a reply to address that does |

The password goes to the identity service and to nothing else. Do not put it in
`.env`, which nothing here reads for it.

Read a token, and set the two names this uses. `--resolve` is how you reach a
name the machine does not know yet, and `-k` is the certificate from step 4:

```
TOKEN="$(docker compose cp identity:/bootstrap/pat - | tar -xO)"
ID_HOST=id.oro.heatsynclabs.org
ID_PORT=8443
```

Create the configuration. Replace every value below with the answers you were
given:

```
curl -sk --resolve "$ID_HOST:$ID_PORT:127.0.0.1" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  "https://$ID_HOST:$ID_PORT/admin/v1/smtp" -d '{
    "senderAddress": "members@example.org",
    "senderName": "HeatSync Labs",
    "replyToAddress": "members@example.org",
    "host": "smtp.example.org:587",
    "user": "members@example.org",
    "password": "the password you were given",
    "tls": true,
    "description": "the lab mail relay"
  }'
```

Expected: an id, which the next two commands need.

```
{"details":{...},"id":"388664033303068677"}
```

`senderAddress`, `senderName` and `host` are the three the service requires. It
refuses a request missing any of them by name, so a 400 here names the field
you left out.

Activate it. A configuration that is created and never activated is stored,
readable, and changes nothing:

```
SMTP=the-id-from-above
curl -sk --resolve "$ID_HOST:$ID_PORT:127.0.0.1" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  "https://$ID_HOST:$ID_PORT/admin/v1/smtp/$SMTP/_activate" -d '{}'
```

Expected: a details block and no error.

Now send a real message, because a mail configuration nobody has sent through
is a mail configuration that does not work. Put your own address in:

```
curl -sk --resolve "$ID_HOST:$ID_PORT:127.0.0.1" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  "https://$ID_HOST:$ID_PORT/admin/v1/smtp/$SMTP/_test" \
  -d '{"receiverAddress": "you@example.org"}'
```

Expected: `{}`, and a message in your inbox within a minute or two.

A wrong host, a wrong port or a blocked outbound connection answers like this,
and the text is the same whichever of the three it was:

```
{"code":13, "message":"could not contact with the SMTP server, check the port,
firewall issues... (EMAIL-skwos)"}
```

The two checks are separate and both are required. `{}` says the identity
service reached the relay. The message arriving says the relay accepted it and
delivered it, and only a person opening a mailbox can say that. A relay that
answers on the port and then drops everything from an unknown sender is a real
thing, and it looks identical from here.

Last, prove the thing a member actually does. Open the sign in screen for the
account you made above, follow Reset Password, and read the mail. If the
message arrives, this step is done and item 1 in the list above is closed.

**Write down which SMTP configuration is live and who holds its password.**
Section 3 of `docs/plan/people-and-custody.md` is where secret custody is meant
to live and it still names nobody, so until it does, this goes in the notes
from step 1 alongside the master key.

## 9. Make a staging copy, and let the migration ask its questions

Everything from here works against a copy. Production is not read again after
step 2 and it is never written to.

The copy is a container with no volume, so removing the container removes every
row in it. Start it:

```
docker run -d --name oro-staging -e POSTGRES_PASSWORD="$(openssl rand -base64 24)" -e POSTGRES_DB=oro postgres:18
```

Wait for it twice, with the loop from step 2 and this container's name.

The legacy tables have to land in a schema called `legacy`, because that is
where `tools/migration/` reads them from, and a production dump carries them in
`public`. Nothing in this repository does that rewrite, so it is two commands
here. Empty the public schema first, so that the archive's own
`CREATE SCHEMA public` succeeds and the restore can be held to
`--exit-on-error`:

```
docker exec oro-staging psql -U postgres -q -d oro -c 'DROP SCHEMA public CASCADE'
```

Expected: `DROP SCHEMA`.

```
docker exec -i oro-staging pg_restore -U postgres -d oro --no-owner --no-privileges --single-transaction --exit-on-error < /root/hsl-legacy-backups/members-$STAMP.dump
```

Expected: nothing, and exit 0. The archive arrives on a pipe, so no copy of the
members database is written inside that container. Measured on 2026-08-31: a
9.6 archive restores into Postgres 18 this way and every row arrives.

Without the `DROP SCHEMA` first, this reports
`ERROR: schema "public" already exists`, treats it as ignorable, and still
exits 0. That is the shape of error worth refusing rather than reading past.

```
docker exec oro-staging psql -U postgres -q -d oro -c 'ALTER SCHEMA public RENAME TO legacy; CREATE SCHEMA public'
```

Expected: `ALTER SCHEMA` and `CREATE SCHEMA`.

Look at what came across, now, before anything else is added to this database:

```
docker exec oro-staging psql -U postgres -d oro -c '\dt legacy.*'
```

Expected: every table the legacy application has. Ours is a fixture with two.
Yours has more, and `contracts` is one of the names to look for, because phase
0 asks what it holds and nobody at the lab has been able to say.

```
                List of tables
 Schema | Name  | Type  |  Owner
--------+-------+-------+----------
 legacy | cards | table | postgres
 legacy | users | table | postgres
```

Two questions phase 0 asks that the migration never will. First, how many rows
each table has, which is what settles `contracts` cheaply:

```
docker exec oro-staging sh -c "psql -U postgres -d oro -tAc \"SELECT string_agg(format('SELECT %L AS t, count(*) FROM legacy.%I', c.relname, c.relname), ' UNION ALL ' ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'legacy' AND c.relkind = 'r'\" | psql -U postgres -d oro -tA -F' '"
```

Expected: one line per table. A count of zero on `contracts` answers the
question and costs nothing. A count that is not zero means somebody has to
look, and looking means member data on a screen, so do it with whoever can
decide rather than alone.

Second, the spread of bcrypt cost prefixes, which phase 2 needs before anybody
plans a login wave:

```
docker exec oro-staging psql -U postgres -d oro -c "SELECT substring(encrypted_password from 1 for 7) AS prefix, count(*) FROM legacy.users WHERE encrypted_password <> '' GROUP BY 1 ORDER BY 1"
```

Expected: one row per prefix. Ours:

```
 prefix  | count
---------+-------
 $2a$10$ |    11
```

`$2a$10$` is what the committed `devise.rb` produces, at cost 10 with no
pepper. Any other prefix is a member whose hash was written under a different
setting, and each one wants recording by legacy id.

Now put the ORO schema in beside it. The `schema` service that does this for
the stack talks to the container called `db` and cannot be pointed at this one,
so here it is a loop. It also writes the `schema_migrations` row for each file,
which `db/migrations/000_migrations.sql` says is what makes a second apply
safe, and which nothing outside the database test runner writes today:

```
cd /opt/project-oro
for f in db/migrations/*.sql db/seed/*.sql; do
  base=$(basename "$f")
  docker exec -i oro-staging psql -v ON_ERROR_STOP=1 -q -U postgres -d oro < "$f" || break
  case "$base" in 000_*) ;; *)
    sum=$(docker exec -i oro-staging sha256sum < "$f" | cut -d' ' -f1)
    docker exec oro-staging psql -v ON_ERROR_STOP=1 -q -U postgres -d oro \
      -c "INSERT INTO schema_migrations (filename, sha256) VALUES ('$base', '$sum')" ;;
  esac
  echo "applied $base"
done
docker exec -i oro-staging psql -v ON_ERROR_STOP=1 -q -U postgres -d oro < tools/migration/005_staging.sql
```

Expected: one `applied` line per file, in filename order, ending on the seed.

```
applied 000_migrations.sql
applied 001_schema.sql
...
applied 014_column_comments.sql
applied 001_reference.sql
```

```
docker exec oro-staging psql -U postgres -d oro -c 'SELECT count(*) AS recorded FROM schema_migrations'
```

Expected: one fewer than the number of files applied, because `000` creates the
ledger and does not record itself. Ours was 15 against 16 files.

Then let the preflight speak. It reads the legacy rows and refuses while
anything in them needs a person:

```
{ echo "BEGIN;"; cat tools/migration/010_preflight.sql; echo "ROLLBACK;"; } \
  | docker exec -i oro-staging psql -v ON_ERROR_STOP=1 -q -U postgres -d oro
```

Expected: a refusal that names every row. This is the point of the whole step.
Ours, against the invented fixture:

```
ERROR:  the legacy data holds 7 thing(s) a person has to decide:
  cards outside slots 10 to 199: card 3 (tag 00000003), card 250 (tag 000000FA)
  cards owned by nobody: card 77 (tag 0000DEAD, user_id 999999)
  members with no email address: user 12 (Blank Email)
  cards carrying a permission other than 1: card 60 (permission 20)
  members carrying the legacy instructor flag: user 2 (Six Char). ...
  members with a payee, somebody paying on their behalf: user 3 ...
  members who signed a waiver with no row in legacy.waiver_documents: user 1 ...
HINT:  docs/plan/data-model.md section 6.3 gives most of these an owner ...
```

That output is the deliverable of this step. It is phase 0 item 6 answered
against real rows. It names real members, so keep it in the ssh session and
carry the decisions out of it by hand. Section 5 of `people-and-custody.md`
gives four of those questions an owner, and every one of those owners reads
`TBD`, so this is where that list stops being abstract.

A card at a slot outside 10 to 199 is the one that cannot be automated. A slot
is an address in the door controller's memory, so renumbering a card points a
member at somebody else's door permission.

## 10. Run the import against the copy

Write the answers down as SQL. `tools/migration/fixtures/decisions.sql` shows
the shape and is explicitly not a recommendation: it is one plausible set of
answers to the fixture's problems. Yours names the lab's real rows and belongs
somewhere a second person can read it.

With the answers applied, run the import as one transaction:

```
{ echo "BEGIN;"
  for f in 010_preflight 020_migrate 022_roles 024_waivers 040_not_carried 030_verify; do
    cat tools/migration/$f.sql
  done
  echo "COMMIT;"
} | docker exec -i oro-staging psql -v ON_ERROR_STOP=1 -q -U postgres -d oro
```

`040` runs before `030` on purpose. It carries who oriented whom, and `030`
asserts that it did.

Expected: a run of notices ending on two verify lines. Ours:

```
NOTICE:  preflight: nothing in the legacy data needs a decision
NOTICE:  roles carried from the legacy booleans, every one of them with no approval behind it:
NOTICE:    member 1 (Ada Invented) now holds admin, granted by nobody, recorded ...
NOTICE:    the two approver rule has NOT armed: 1 of 3 bootstrap admin grant(s) are used ...
NOTICE:  waivers: 1 row(s) carried, each holding a date and where the document is kept and nothing else
NOTICE:  not carried, twelve columns of the forty:
NOTICE:    11 member(s) have an encrypted_password, and it is not carried here on purpose ...
NOTICE:  verify: 12 member(s) and 5 card(s), every card at the slot it had
NOTICE:  the legacy schema is still in this database, with 12 member row(s) and their encrypted_password ...
NOTICE:  verify: 2 role(s) and 1 waiver(s) carried, and nothing that no legacy row asked for
```

Read three of those lines twice.

The card line, because every card being at the slot it had is the assertion the
door depends on. `030_verify.sql` refuses to finish if any card moved, so
reaching that line at all is the proof.

The two approver line, because a lab whose legacy database holds fewer than
three admins comes out of this import with a bootstrap seat still open, and
somebody could then be made an admin with nobody approving it.

The last legacy line, because the `legacy` schema is still sitting in the
database holding every member's address, phone number and password hash. It is
there so you can compare against the source. Once you have, and the comparison
is written down:

```
docker exec oro-staging psql -U postgres -d oro -c 'DROP SCHEMA legacy CASCADE'
```

**Then take the whole copy away.**

```
docker rm -f oro-staging
```

Expected: `oro-staging`. That container had no volume, so the members data goes
with it. Do this even if you plan to run the import again tomorrow, because a
staging copy nobody remembers is a copy of the lab's membership sitting on a
disk.

### When the copy has to persist

A parallel run needs the data in the stack's own database rather than in a
container you throw away. That database already holds the ORO schema, because
the `schema` service put it there at step 5, so its `public` schema is
occupied and the trick from step 9 does not work on it. Restore into a scratch
database in the same container, rename the schema there, then move that one
schema across:

```
docker exec oro-db-1 psql -U postgres -d postgres -q -c 'CREATE DATABASE legacy_import'
docker exec oro-db-1 psql -U postgres -d legacy_import -q -c 'DROP SCHEMA public CASCADE'
docker exec -i oro-db-1 pg_restore -U postgres -d legacy_import --no-owner --no-privileges --single-transaction --exit-on-error < /root/hsl-legacy-backups/members-$STAMP.dump
docker exec oro-db-1 psql -U postgres -d legacy_import -q -c 'ALTER SCHEMA public RENAME TO legacy'
docker exec oro-db-1 sh -c 'pg_dump -U postgres -d legacy_import --schema=legacy --no-owner --no-privileges | psql -U postgres -d oro -v ON_ERROR_STOP=1 -q'
docker exec oro-db-1 psql -U postgres -d postgres -q -c 'DROP DATABASE legacy_import'
docker exec oro-db-1 psql -U postgres -d oro -c "SELECT (SELECT count(*) FROM legacy.users) AS users, (SELECT count(*) FROM legacy.cards) AS cards"
```

Expected: the same two counts you read at step 9, now inside the stack's
database. The pipe in the fifth line runs inside the container, so nothing is
written to a filesystem on the way.

```
 users | cards
-------+-------
    12 |     8
```

Then `005_staging.sql` and your answers, followed by the import transaction
from the top of this step, all against `oro-db-1` instead of `oro-staging`.
Drop the `legacy` schema afterwards the same way.

**Say out loud that you have done this.** It is the first copy of the members
database this project makes that outlives a `docker rm`. It lives in the
`db_data` volume, and `docker compose down --volumes` is the only thing that
removes it. Take a backup of it while you are there, which is what
`tools/backup/` was built for and what it can do, because now the database is
called `oro`:

```
make backup
```

Expected: two files under `$HOME/oro-backups`, and a first line saying the
archive was read back before it was named.

## 11. Run the two side by side

The legacy application serves members exactly as it does today. This one serves
a health check and the members API under `/v1`, with a 404 at the root. That is
the whole of the parallel run available right now, and it is deliberately
small.

What a member sees: nothing. `members.heatsynclabs.org` is untouched, the ORO
hostname has no DNS record, and there is no portal behind it in any case.
`apps/members` is served only under the development routes, which a deployment
never imports.

What breaks if you turn this off: nothing. `make down` and the lab is where it
was this morning. Test that claim rather than believing it, once, by taking it
down and asking somebody to load the members site.

What has to keep working throughout, and it is not negotiable: physical cards
open the door. The controller matches them against its own memory, the legacy
application is the only thing that writes that memory, and nothing in this
document goes near either. There is no state of this deployment, running or
stopped or half configured, that reaches the door.

Two things become possible here, and both need a person rather than a command:

- DNS for `oro.heatsynclabs.org` and `id.oro.heatsynclabs.org`, which is phase 0
  item 4. The zone holder is a name nobody has filled in.
- Ten real members signing in with the passwords they already have, which is
  phase 2's exit criterion. Nothing in this repository imports real hashes into
  a running identity service yet, so that is not runnable today. Gap 6.

## 12. Cutover, and what has to be true first

Cutover is phase 6 and this document does not perform it. What it can do is
list what has to be true beforehand, so nobody arrives at that day with the
list unread. From `docs/plan/order-of-operations.md`:

1. Phases 1 through 5 have each met their exit criterion, with the evidence
   named beside each one. Not one of them has today.
2. The contract has been reviewed by somebody who did not write it.
3. Ten real members have signed in to this deployment with their existing
   passwords, spanning the oldest and newest accounts.
4. Card management is frozen in the legacy application first. Disabled rather
   than merely unused. Two systems both writing cards is the worst failure this
   project can produce, because a revocation silently undoes itself while both
   audit logs look correct.
5. The reconcile loop has run read only for a week and then a week with writes,
   and the controller's table matches the database at the end of it.
6. `space_api.json` is byte identical on a test hostname and under 900 bytes.
7. The two approver rule has been to a vote at Hack Your Hackerspace, or the
   branch where that vote fails has been taken.

The day itself is a DNS change and a port change, both reversible in minutes,
which is the reason for choosing a separate hostname back at step 4.

## 13. Rollback

The step people skip writing. Each of these undoes exactly one thing, in the
reverse order of the steps above, and none of them touches the legacy
application, because none of the steps above did either.

**Stop this deployment and keep everything.**

```
cd /opt/project-oro && make down
```

Expected: the containers stop. The database volume is kept on purpose, so
`make up` afterwards finds the same rows.

**Stop it and destroy its data.** This removes the members data this project
imported, and the identity database with it, including the bootstrap token and
every account made in it.

```
docker compose down --volumes
```

There is no way back from that except step 10 again. The one time it is the
right answer is a half written first instance: if the identity service ever
dies with `permission denied` on its bootstrap file, the second attempt fails
on a unique constraint over the instance domain it already wrote, and there is
no forward path.

**Give the ports back.** They were never taken from the legacy system, so
stopping the containers is the whole of it. Confirm with `ss -lntp` against
what you wrote down at step 1.

**Remove the staging copy**, if one is still running:

```
docker rm -f oro-staging
```

**Remove the archive.** Only once there is another copy of it somewhere, which
today there is not, because there is no timer and no offsite copy.

```
shred -u /root/hsl-legacy-backups/members-STAMP.dump
```

**Undo the machine changes.** The clone at `/opt/project-oro` goes with
`rm -rf`, and its `.env` holds four secrets, so `shred -u .env` first. Docker,
if step 3 installed it, is the one change worth leaving in place: uninstalling
it is another change to a production host and it buys nothing.

Step 6 left two things outside that clone. The `/etc/hosts` line comes out by
hand, and it should come out anyway once the DNS records exist, so that this
machine resolves those names the same way everybody else does. The copy of
Caddy's root certificate is not a secret and is not a credential, and it is
still a file naming an authority nobody should be asked to trust once this is
gone:

```
shred -u /root/oro-caddy-root.crt
```

**Remove the configuration archive** the same way the database archive goes,
and for a stronger reason: it carries `database.yml` and the session secret.

```
shred -u /root/hsl-legacy-backups/legacy-config-STAMP.tar.gz
```

**What has no rollback.** The backup at step 2 read production, so there is
nothing to undo. Nothing else in this document wrote to the legacy database, to
the legacy application, or to the door controller. If you are looking for the
step that could have broken members, there is not one. That is the point of the
shape.

---

## What this runbook does not cover

Numbered, because each one is a thing somebody has to build, and a person
following this at 2am should not discover it by watching a command fail.

1. **No migration runner.** The `schema` service in `compose.api.yaml` applies
   `db/migrations` to the stack's database on a first start and says in its own
   header that it is not a migration runner: it records nothing, and a
   migration written after the database was built will not be applied by it.
   `schema_migrations` is written by nothing outside `db/tests/run.sh`, and the
   loop at step 9 that writes it lives in this document rather than in the
   repository, where no test covers it.
2. **`tools/backup/` cannot back up the production database.** `backup.sh` and
   `restore.sh` both hardcode a database named `oro` inside a container, so
   gate one of rule 12 is met at step 2 by typing `pg_dump` rather than by
   running the tool built for it. Nothing tests the commands in step 2.
3. **`tools/migration/run.sh` cannot be pointed at real data.** It always loads
   `fixtures/legacy-schema.sql` and `fixtures/legacy-data.sql`, so steps 9 and
   10 run the numbered SQL files by hand, and the eleven cases in
   `make migration-test` say nothing about that sequence.
4. **Nothing rewrites a production dump's `public` schema into `legacy`.**
   Steps 9 and 10 do it with `ALTER SCHEMA`, and no test covers that either.
5. **The backup is not on a timer and there is no offsite copy.** A fire in the
   lab takes the server and the archive together. `tools/backup/README.md` says
   what each of those would need.
6. **Nothing imports real password hashes into a running identity service.**
   `tools/identity/tests/check_legacy_import.py` reads the committed fixture
   and runs inside its own throwaway stack, so phase 2's exit criterion has no
   command behind it yet.
7. **`ORO_API_TOKEN_ISSUER` carries no port**, so on any HTTPS port other than
   443 the members API refuses every token the identity service issues. Step 4
   has the measurement. It costs nothing while no member is routed to that API
   and it has to be settled before one is.
8. **There is no portal on a deployment.** `apps/members` is served only under
   the development routes, so the hostname answers a 404 at the root. Wiring
   the portal to the API is the rest of phase 3.
9. **DNS.** Two records that do not exist, and a zone holder with no name in
   `people-and-custody.md`.
10. **A publicly trusted certificate.** Not available while the legacy system
    holds 80 and 443, and the DNS challenge that would avoid them needs a Caddy
    image this project does not build.
11. **The plain HTTP port redirects to the standard port and lands on the
    legacy site.** Measured, and no setting fixes it.
12. **Whether Docker's published ports bypass this host's firewall.** The
    assumption block at step 3 names the check and nobody has run it.
13. **Down migrations.** Rule 3 of `CLAUDE.md` starts requiring them at the
    first production apply. Step 10 against `oro-db-1` is that apply, and from
    that day every migration ships with its reverse and both directions get run
    before merge.
14. **The driver's seat drill.** Phase 0 does not exit until somebody who did
    not build this brings the stack up and restores the database from the
    written runbook while the person who built it watches and says nothing.
    Every question asked out loud is a defect in this file. Fix it here.
15. **No command resets a password somebody has forgotten.**
    `tools/identity/make_a_sign_in.py --repair` sets a password only on an
    account holding none, deliberately, so that running it twice cannot take
    away a password a member chose. Until a mail server exists, a forgotten
    password is an admin calling `POST /v2/users/{id}/password` on the identity
    service and reading the new one out to them.
