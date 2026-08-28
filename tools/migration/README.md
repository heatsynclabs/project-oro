# Migration

## What it is

The import that carries the legacy members and cards into this schema, and the
proof that it either works or refuses.

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

That starts a throwaway `postgres:18`, applies `db/migrations` and `db/seed`,
loads the fixture beside this file, applies the decisions in
`fixtures/decisions.sql`, migrates, and checks every assertion in
`docs/plan/data-model.md` section 6.2. It leaves nothing behind.

To watch it refuse instead:

```sh
tools/migration/run.sh --undecided
```

That skips the decisions, and the preflight then names every row a person has to
rule on before an import can start. That output is the answer to the questions
`docs/plan/order-of-operations.md` phase 0 asks of the production data, and
running it against a staging copy is how those get answered for real.

## What is here

| File | What it is |
|---|---|
| `010_preflight.sql` | Refuses to start, naming every row a person has to decide on |
| `020_migrate.sql` | Members and cards. Nothing else yet |
| `030_verify.sql` | The assertions in `data-model.md` section 6.2, checked after the fact |
| `fixtures/legacy-schema.sql` | The legacy tables, taken with `pg_dump` from a replica |
| `fixtures/legacy-data.sql` | Invented members and cards, written by a replica through the legacy application's own models |
| `fixtures/legacy-passwords.json` | The plaintexts for those members, so a sign in can be proven |
| `fixtures/decisions.sql` | One plausible set of answers to what the preflight refuses. Not a recommendation |

Certifications, waivers, payments and door events are not migrated. Nothing
reads them yet and rule 10 forbids shipping what does not exist.

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
