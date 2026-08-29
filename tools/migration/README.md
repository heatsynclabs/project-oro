# Migration

## What it is

The import that carries the legacy members, cards, roles and waivers into this
schema, and the proof that it either works or refuses.

The legacy system is the Rails 3.2.8 application at `members.heatsynclabs.org`.
Its source is [Open-Source-Access-Control-Web-Interface](https://github.com/heatsynclabs/Open-Source-Access-Control-Web-Interface),
and this directory reads its data rather than its code.

**The one thing to know before reading anything else:** the slot on the door
controller is the legacy `cards.id` primary key. `app/models/card.rb` in that
application builds its request to the Arduino as `m#{self.id}`, so an integer
primary key is an EEPROM address, and it is typed in by hand by an admin through
a form that offers 10 to 200. `docs/plan/data-model.md` section 6.2 calls
keeping it not negotiable, and `030_verify.sql` refuses to finish if any card
moved.

## How to run it

```sh
make migration-test
```

That runs eleven cases, each in a throwaway `postgres:18` built from
`db/migrations` and `db/seed`. Ten are imports of the same fixture: three carry
everything and seven have to be refused. One of the three runs in
`America/Phoenix`, which is how the dates are proved not to move. Two are the
same import past the bootstrap admin quota, run once as it ships and once with
the role grant trigger left on, which is how the disable in `022_roles.sql` is
proved to be load bearing. The eleventh runs the role step on its own, outside
any transaction, and proves it cannot leave that trigger off. Every case is
checked against what it printed and not only against its exit code. It leaves
nothing behind.

To watch a single import refuse instead:

```sh
tools/migration/run.sh --undecided
```

That skips the decisions, and the preflight then names every row a person has to
rule on before an import can start. Several of those rows are what
`docs/plan/order-of-operations.md` phase 0 asks of the production data, so
running this against a staging copy is how those get answered for real. It does
not answer all of phase 0: what `contracts` holds and the spread of bcrypt cost
prefixes are not questions about rows this import writes.

## What is here

The steps run in this order, and everything from `010` down runs inside one
transaction. A migration that half ran is worse than one that did not.

| File | What it is |
|---|---|
| `005_staging.sql` | `legacy.waiver_documents`, where a person writes down where each signed waiver is kept. Not legacy data |
| `010_preflight.sql` | Refuses to start, naming every row a person has to decide on |
| `020_migrate.sql` | Members and cards |
| `022_roles.sql` | The legacy `admin` and `accountant` booleans, as `member_roles` rows |
| `024_waivers.sql` | The legacy `waiver` date, as a `waivers` row pointing at where the document is kept |
| `040_not_carried.sql` | Names what did not come across, and carries who oriented whom |
| `030_verify.sql` | The assertions in `data-model.md` section 6.2, and the same kind of assertion over the roles and waivers, checked after the fact |
| `fixtures/legacy-schema.sql` | The legacy tables, taken with `pg_dump` from a replica |
| `fixtures/legacy-data.sql` | Invented members and cards, written by a replica through the legacy application's own models |
| `fixtures/legacy-passwords.json` | The plaintexts for those members, so a sign in can be proven |
| `fixtures/decisions.sql` | One plausible set of answers to what the preflight refuses. Not a recommendation |
| `tests/run.sh` | Runs the eleven cases and reads what each one printed |
| `tests/check_the_guard.sh` | Runs the role step alone, which `run.sh` cannot do, and proves it leaves the trigger on |
| `tests/*.sql` | Hand authored, one per case the suite adds. Deliberately not part of the fixture, which carries a provenance claim these would make false |

## What comes across, and what does not

The legacy `users` table has forty columns. Twenty six arrive. Fourteen do not. Twelve of
them are counted by `040_not_carried.sql` on every run, and the other two are
the ones the preflight refuses, so they never reach it. Nobody gets to mistake
the import for complete. The suite reads that report and fails if it
stops being true.

Two of the fourteen are refused rather than dropped. The import will not start
while any legacy user carries the `instructor` flag or a `payee`:

- **`instructor` cannot be carried.** An instructor here is an instructor on one
  tool, which `docs/glossary.md` states and `certification_instructors` builds.
  `db/seed/001_reference.sql` seeds no instructor role and no certifications, so
  a global boolean has nothing to point at. Somebody has to say which tools each
  of these people covers.
- **`payee` has no column anywhere in this schema.** Somebody has to say where it
  goes, or that it goes nowhere.

Roles come across as the deliberate, logged exception `data-model.md` section
6.1 authorises. The legacy booleans have no approval behind them, so
`022_roles.sql` turns off `role_grant_rules` by name inside the transaction,
writes `granted_by` and `approval_id` null, and then names every member it
granted to. `arm_the_rule` is left on, so an import that takes the lab past
three admins arms the two approver rule on its way through. `granted_at` is when
the import ran: the legacy schema records no date for when anybody was made an
admin, and inventing one would put a date on a grant nobody can stand behind.

Waivers come across as a date and a pointer, never a document. `waivers.storage`
is `NOT NULL` and a reference identifies one document, so neither can be guessed
from a date, and `005_staging.sql` is where a person writes the answer down.

The `legacy` schema is left standing after the import, so that whoever ran it can
compare against the source. That means a second copy of every member's address,
phone, emergency contact and password hash is in the database this system serves
from, which rule 13 says is a second thing to protect and to leak. `030_verify.sql`
says so on every run and names the statement that removes it. Dropping it is a
step somebody takes once the import has been checked, not something this script
does while the evidence is still needed.

Certifications, payments and door events are not migrated. Nothing reads them
yet and rule 10 forbids shipping what does not exist.

## Where the fixture came from

Not hand written. It was produced by a replica of the legacy application, so the
rows are rows that application writes and the hashes are hashes it stores. The
replica lives outside this repository, because it is somebody else's source and
this project does not vendor it.

```sh
mkdir -p ../temporary-hsl-infra && cd ../temporary-hsl-infra
git clone https://github.com/heatsynclabs/Open-Source-Access-Control-Web-Interface.git
```

Then a small image with the three versions that decide a stored credential
pinned to that repository's own `Gemfile.lock`: `devise 2.2.7`,
`bcrypt-ruby 3.0.1`, `rails 3.2.8`. It loads the real `db/schema.rb` and the
real `app/models/user.rb` and `app/models/card.rb`, and creates members through
them. `postgres:9.6` underneath, which is the major version production runs.

Two things about that replica are not the legacy application and both are
written down because they could matter:

- **Ruby 2.3, not the 1.9.3 the legacy Dockerfile names.** That image is a
  Docker Schema 1 manifest and containerd refuses to pull it, and the amd64
  images of that era segfault under emulation here. What decides a stored
  credential is `Devise::Models::DatabaseAuthenticatable#password_digest`,
  which is `BCrypt::Password.create("#{password}#{pepper}", cost: stretches)`
  with pepper nil and stretches 10. The Ruby underneath does not change a
  bcrypt hash.
- **The web application is not run.** Only its schema and its models are, so
  controllers, views and the asset pipeline are not exercised. What is being
  reproduced is the data, not the site.

## What it proves, and what it does not

`tools/identity/tests/check_legacy_import.py` takes the hashes out of that
fixture, imports them into the identity service, and signs in with the passwords
that produced them. Nine of the eleven succeed. The two that do not are the two
whose passwords are longer than 72 bytes, which is the defect
`tools/identity/README.md` records.

That is as close as a script gets to part (b) of the phase 2 password proof, and
it is not part (b). Every password in the fixture was chosen by whoever wrote
the replica, so the awkward cases are the ones somebody thought of. Real members
choose passwords nobody thought of, which is the entire reason
`docs/plan/order-of-operations.md` asks for ten of them.

## What it depends on

| Thing | Why |
|---|---|
| `db/migrations/` and `db/seed/` | The schema this migrates into, and the tiers and roles it maps onto |
| `docs/plan/data-model.md` section 6 | The assertions, and the list of decisions a person owns |
| Docker | A throwaway `postgres:18`. Nothing is installed |

Nothing else. No Ruby, no legacy source, and no network: the fixture is
committed, so the suite runs offline.
