# Bootstrap

## What it is

The command that gives this system its first admins. A fresh database holds no
members and the identity service holds one administrator of its own, and there
is no path from there to a person who can administer the lab. This is that path.

It seats people against the escape in
[`db/migrations/013_bootstrap_three_admins.sql`](../../db/migrations/013_bootstrap_three_admins.sql),
which allows three grants of a role that can itself grant roles with no approval
behind them. Three, because two is the smallest number the two approver rule can
bind at and leaves the lab with nothing in reserve. The third seat is the spare
that `docs/plan/people-and-custody.md` section 1 asks for.

Each person needs three things, and the command does all three or none of them:

- an account on the identity service, holding a password they have to change
- a row in `members`, carrying the subject that account will arrive with
- a row in `member_roles` granting admin

The fourth person is refused, and the refusal comes out of the database. Nothing
here counts seats or decides who may be an admin. The command creates the
identity account, asks the database for the rest, and prints what the database
said.

## How to run it

From a terminal, with the stack up and `db/migrations` applied to its `oro`
database:

```sh
make bootstrap-admins \
  ADMIN1="Ada Byron <ada@example.org>" \
  ADMIN2="Grace Hopper <grace@example.org>" \
  ADMIN3="Katherine Johnson <katherine@example.org>"
```

Each person is named on the command line, in the shape an address is written in
a mail client. Nobody's address goes into a file in this repository, which rule
13 of `CLAUDE.md` asks for and which a committed list of admins would break on
the first commit.

For any other number of people, the command underneath takes `--admin` as many
times as you name it:

```sh
tools/bootstrap/seat_admins.py --admin "Ada Byron <ada@example.org>"
```

**Run it from a terminal.** Every new admin gets a password, and that password
is written to `/dev/tty` and to nothing else. Redirecting the report into a file
keeps the report and captures no password. A run with no terminal attached
refuses before it creates anything, because seating three people and printing
their passwords nowhere would leave three accounts nobody can sign in to.

The password is a handover rather than a credential. Give it to the person it
belongs to and to nobody else. The identity service makes them choose their own
the first time they sign in: after the login name and the password, the third
screen is Change Password, measured against Zitadel 4.17.1 on 2026-08-29.

Running it again is safe. It reports what is already seated and writes nothing,
and it does not touch a password on that path, because by then the person may
have chosen their own.

### When something goes wrong

The identity account is created first, because the member row cannot be written
until the subject that account will arrive with is known. That ordering is also
what `docs/plan/data-model.md` section 6.1 requires: a member row that already
holds a role is not claimable by `link_or_create_member`.

So a database refusal leaves an identity account that holds no role and can do
nothing here. The report names it. The database side is one transaction and
rolls back whole, so there is no half seated member to find later.

A refused fourth admin is not a fault to work around. Two of the three admins
grant the fourth between them, one proposing and the other approving.

## How to test it

```sh
tools/bootstrap/tests/run.sh
```

It brings up a database and an identity service as its own compose project on
its own ports, applies the schema, seats three invented people, and takes it all
down. Nothing it does can reach a stack you already have running.

Twelve checks read the two systems back and a thirteenth signs one admin in
through the hosted screens. Every refusal around them is checked by its own text rather
than by an exit code alone, because a broken command that exits nonzero looks
exactly like a working refusal from outside. What it proves:

- three people are seated, and each can sign in with the password that was
  printed
- the subject in the token a portal receives is the subject on the member row,
  through a real sign in on the hosted screens
- the fourth is refused, in the database's own words, and the command holds no
  copy of the rule it was refused by
- a second run leaves the database byte for byte what it was
- the two approver rule is armed afterwards, and the application role cannot
  grant admin even with an admin signed in
- the report a person redirects into a file carries no password

It is not part of `make check`. That is a decision for whoever owns that list:
this suite starts an identity service, which is the slowest thing in the
repository to start.

## What it depends on

| Thing | Why |
|---|---|
| `db/migrations/013_bootstrap_three_admins.sql` | The escape being spent, and the refusal after it |
| `db/migrations/008_system_paths.sql` | `link_or_create_member`, the only path that writes a member row without an admin |
| `tools/identity/api.py` | How to call the identity service, and why each path looks the way it does |
| `compose.yaml` | The database and the identity service. The suite starts its own |
| Docker, and Python from the standard library | Nothing is installed to run any of this |

### The database role, and why it is the owner

`member_roles` has `FORCE ROW LEVEL SECURITY`, and its INSERT policy is
`is_admin(current_member_id())`. On the first day nobody is signed in, so
`current_member_id()` raises before the policy has anything to decide, and with
no admin in the table it would decide against you anyway. The application role
has no way through that, on purpose.

The role that owns the schema does, because it is the superuser the migrations
ran as, and row level security does not apply to a superuser. The suite proves
both halves: the application role refused with no member signed in, and refused
again for granting admin with an admin signed in.

The command reaches that role the way `make psql` does, through the psql inside
the container, because `compose.yaml` publishes no port for the database and
means it. `ORO_PSQL` replaces that command whole, which is how the suite points
it at a throwaway compose project.

### What it is not

There is no API service yet. `services/api` does not exist, so this writes rows
itself, which is a layer this repository will not keep. When that service
arrives, seating an admin becomes a call to it.
