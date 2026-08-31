# Deploy beside the legacy system

Follow this to put Project ORO on hsl-web next to the members application it
will replace, and to take the first real backup of the members database. It
assumes you did not build any of this, and that you have ssh as root on
hsl-web.

Read these five things before step 1.

**The door is not waiting on you, and nothing here can stop it.** A physical
card is matched against a table in the Arduino's own memory with no network
involved, and the legacy Rails application is the only thing that writes that
table. Neither is touched anywhere in this document. If the door stops working
while you are following this, it stopped for some other reason, and this is not
the runbook for it. Rule 12 of `CLAUDE.md` puts that above every phase, so if
you find yourself about to type something that could reach the controller or
the legacy application's card screens, stop instead.

**Nobody has seen hsl-web.** Six things this document would otherwise guess at
are written as assumptions below, and step 1 is where each one gets an answer.
Do step 1 first and write the answers down. If one of them comes back
differently from what is assumed here, that changes the work rather than being
a detail.

**No copy of the members database goes onto your laptop.** Rule 13. Every
command below runs on hsl-web through your ssh session, and the table after the
assumptions lists where each copy lives and what removes it. If you catch
yourself typing `scp`, stop.

**What you have at the end, and what you do not.** After step 8 hsl-web runs an
identity service, a Postgres holding a migrated copy of the members data, and a
members API answering under `/v1` on a new hostname. There is no portal. The
deployment's routes serve a health check and the members API, with a 404 at the
root, so there is no page for a member to open. A member sees no change at all,
on purpose. The gaps at the end list the rest of what is missing.

**The blocks below are not from hsl-web.** They come from a laptop, on
2026-08-30 and 2026-08-31, against a Postgres 9.6 container standing in for the
legacy database, on a machine where another stack already held the ports. The
container names, the hostname and the port numbers are written as the ones this
guide chooses. Nothing else in them is edited. Step 1 is where transcripts start
coming from the real machine, and the counts you see there will be the lab's
rather than the twelve invented members here.

---

## What is assumed, and what confirms it

```
ASSUMPTION: the legacy members application and its Postgres both run on
  hsl-web, rather than the database living on another host.
CONFIRM BY: step 1, the listener table and the process list.
BLAST RADIUS: everything. If the database is elsewhere, steps 2 and 3 run
  there instead, and this machine may not be where ORO belongs either.

ASSUMPTION: that Postgres is 9.6, which is the version
  tools/migration/README.md says the fixture replica was built against.
CONFIRM BY: step 1, select version().
BLAST RADIUS: the flags in step 2. --no-role-passwords does not exist before
  Postgres 10, which is measured below. The workaround there is only needed
  while the answer is 9.6.

ASSUMPTION: something on hsl-web already holds ports 80 and 443.
CONFIRM BY: step 1, the listener table.
BLAST RADIUS: step 4 chooses ports and a certificate issuer on this basis. If
  80 and 443 turn out to be free, read step 4 again before choosing, because
  one thing in the stack is built on the assumption that HTTPS is on 443.

ASSUMPTION: Docker with the compose plugin is not installed on hsl-web.
CONFIRM BY: step 1, docker version.
BLAST RADIUS: step 3. Installing Docker is the largest thing this document
  asks of a production host, and it is the step to think hardest about.

ASSUMPTION: a custom format dump of the production members database is under
  256MB. This is compose.yaml's own stated assumption, written where shm_size
  is set, and it has never been confirmed.
CONFIRM BY: step 2, the size of the file.
BLAST RADIUS: tools/backup/restore.sh refuses an archive that does not fit in
  the database container's /dev/shm. The fix is one line in compose.yaml and
  the refusal names it.

ASSUMPTION: hsl-web has room for about 1GB of container images plus the dump
  held twice over, with enough left that the legacy application does not run a
  disk out.
CONFIRM BY: step 1, df.
BLAST RADIUS: a full disk on the machine that opens a building. Measured on
  2026-08-31: postgres:18 is 666MB, the identity service image is 221MB and
  caddy:2-alpine is 84.6MB. The members API image is built on the host rather
  than pulled, so it costs whatever its build costs on top.
```

## Where every copy of the members database lives

Rule 13 asks for this to be written down rather than reconstructed later.

| Copy | Where it is | What removes it |
|---|---|---|
| Production | The legacy Postgres on hsl-web | Nothing here. It is never written to |
| The archive | `/root/hsl-legacy-backups` on hsl-web, mode 600 inside a mode 700 directory | You do, by hand. Nothing else will |
| The roles file beside it | The same directory. On 9.6 it carries password hashes until step 2 strips them | The same |
| The staging copy | Inside the `oro-staging` container, which has no volume | `docker rm -f oro-staging` at the end of step 7, which takes the rows with it |
| The `legacy` schema | Inside whichever database the import ran against | `DROP SCHEMA legacy CASCADE`, which the import itself tells you to run |
| The imported members | The `db_data` volume of the ORO stack, once step 8 puts them there | `docker compose down --volumes` |
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
everything up to step 8 and it is not fine for step 9. Phase 0 item 4 of
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
0 item 5, and it wants a copy rather than the original. Step 7 restores it into
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

## 6. Check that nothing on the old side moved

Do this now, while it is cheap to undo. Run it from a second machine rather
than from hsl-web.

```
curl -sI https://members.heatsynclabs.org/ | head -3
```

Expected: the same status line the legacy application gave before you started.
Somebody should have written that down during step 1. If it changed, take this
stack down with `make down` and read step 10.

```
ss -lntp
```

Expected: the listeners from step 1 unchanged, plus the two Caddy binds. None
of the legacy application's ports has moved.

Then ask a member to open the members site and say whether it looks normal.
That costs a message, and it is the only check here that reads the thing a
member actually sees.

## 7. Make a staging copy, and let the migration ask its questions

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

## 8. Run the import against the copy

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
occupied and the trick from step 7 does not work on it. Restore into a scratch
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

Expected: the same two counts you read at step 7, now inside the stack's
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

## 9. Run the two side by side

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

## 10. Cutover, and what has to be true first

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

## 11. Rollback

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

There is no way back from that except step 8 again. The one time it is the
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
   loop at step 7 that writes it lives in this document rather than in the
   repository, where no test covers it.
2. **`tools/backup/` cannot back up the production database.** `backup.sh` and
   `restore.sh` both hardcode a database named `oro` inside a container, so
   gate one of rule 12 is met at step 2 by typing `pg_dump` rather than by
   running the tool built for it. Nothing tests the commands in step 2.
3. **`tools/migration/run.sh` cannot be pointed at real data.** It always loads
   `fixtures/legacy-schema.sql` and `fixtures/legacy-data.sql`, so steps 7 and
   8 run the numbered SQL files by hand, and the eleven cases in
   `make migration-test` say nothing about that sequence.
4. **Nothing rewrites a production dump's `public` schema into `legacy`.**
   Steps 7 and 8 do it with `ALTER SCHEMA`, and no test covers that either.
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
    first production apply. Step 8 against `oro-db-1` is that apply, and from
    that day every migration ships with its reverse and both directions get run
    before merge.
14. **The driver's seat drill.** Phase 0 does not exit until somebody who did
    not build this brings the stack up and restores the database from the
    written runbook while the person who built it watches and says nothing.
    Every question asked out loud is a defect in this file. Fix it here.
