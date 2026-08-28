# Handoff

You are picking up Project ORO. This file is the fastest path to being useful.

Project ORO replaces the HeatSync Labs members and door system: the Rails 3.2.8
app at `members.heatsynclabs.org` and the Arduino that unlocks the building.
Three previous rewrites over eight years stalled. Nothing has been deployed and
nothing in production has been touched.

---

## 1. Read in this order

| # | File | Why |
|---|---|---|
| 1 | `CLAUDE.md` | The working rules. They bind anyone writing code here |
| 2 | `docs/plan/architecture.md` | The system, and what would replace each piece |
| 3 | `docs/plan/data-model.md` | Why the schema is shaped the way it is |
| 4 | `docs/plan/api-design.md` | The contract. Written before the services, on purpose |
| 5 | `docs/plan/order-of-operations.md` | Build order, with an exit criterion per phase |
| 6 | `docs/plan/people-and-custody.md` | Who holds what. **The real blocker lives here** |
| 7 | `docs/plan/changes-from-the-original.md` | Diff against the original ORO document and its mockups |
| 8 | `docs/glossary.md` | Domain words. Code uses these exactly |

If you read only two, read `CLAUDE.md` and `people-and-custody.md`.

## 2. What is built, and what is not

This table is the single place this is tracked. Update it as things land.

| Thing | State |
|---|---|
| `db/migrations/` schema, rules, RLS, immutability | **Built.** Applies clean from nothing |
| `db/tests/` and `db/tests/run.sh` | **Built.** 79 assertions, deterministic |
| `db/seed/001_reference.sql` | **Built.** Tiers, roles, governance parameters |
| `tools/voice-check/` prose gate | **Built.** 74 tests |
| `.githooks/commit-msg` | **Built.** Install it, see section 3 |
| The plan documents | **Written.** Reviewed adversarially twice |
| `services/api/` | Not started. Phase 3 |
| `services/door/` and its adapter and fake | Not started. Port and fake belong in phase 1 |
| `apps/` members, admin, door | Not started. Phase 3 onward |
| `packages/gantry-tokens`, `gantry-css` | Not started. Phase 1 |
| `.github/workflows/ci.yml` | Not started. Phase 0 |
| Import boundary and file ceiling linting | Not started. Phase 0 |
| `tools/attributions/generate.py` | Not started. Needs a lockfile first |
| `docs/runbooks/` | Not started. Created with the first runbook |
| `CODEOWNERS`, `.sops.yaml` | Not started. Created with the first real name and the first secret |

## 3. Run everything

```sh
git config core.hooksPath .githooks      # once per clone, enables the commit gate

./db/tests/run.sh                        # rebuilds the schema from nothing, runs 79 assertions
./db/tests/run.sh --update               # regenerate expected output, deliberately

python3 tools/voice-check/test_voice_check.py
python3 tools/voice-check/test_regressions.py
python3 tools/voice-check/test_behaviour.py
python3 tools/voice-check/voice_check.py docs/ CLAUDE.md db/ tools/
```

`db/tests/run.sh` needs Docker and nothing else. It creates a throwaway
`postgres:18` container, applies every migration and seed in order, runs each
test file in a transaction that rolls back, and removes the container. It leaves
nothing behind. Expect it to take about twenty seconds.

Everything should be green. If it is not, that is a real failure: the suite has
been run more than twenty times consecutively without a flake.

## 4. Decisions already made

Each has reasoning behind it. Do not silently reverse one; supersede it with an
ADR (`docs/decisions/0000-template.md`).

- **Identity: Zitadel.** The only candidate that imports the existing Devise
  bcrypt hashes with no fork and no bespoke login UI. Verified pepper is off and
  cost is 10.
- **API: one handwritten FastAPI service, not PostgREST.** Row level security
  underneath, so there is no bypass to take.
- **Deployment: portable Docker Compose.** No vendor anywhere. It must run on the
  lab's R610, a VPS, or a laptop, identically.
- **Door: its own VLAN, no tunnel, outbound only.** Commands are asynchronous
  because of that, and status is pushed rather than pulled.
- **Door service is an API plus a controller adapter**, so the Arduino can be
  replaced without the contract changing.
- **Theme: CSS first, not Vue first.** The consumers are split across Astro plus
  Vue, React 19, and Rails ERB.
- **Payments are out of scope.** The schema reserves the tables.
- **Order: identity, member management, admin, door.**

## 5. What is actually blocking

Not code. All three are people problems, and they are the reason the previous
attempts died.

1. **No name is filled in anywhere in `people-and-custody.md`.** Every role is
   TBD. By the rule in that file, a phase does not start while the roles it needs
   are empty. This is deliberate, not an oversight.
2. **Phase 0 needs a shell on hsl-web** to take a verified, restorable backup.
   That is the credentials and custody problem the lab has not solved since 2013.
   It needs a named grantor, two named recipients, and a date.
3. **The two approver rule needs an HYH vote** before it binds anyone. It is a new
   policy this project introduces, and the proposal is step zero of phase 1.

## 6. Do this next

In order.

1. Fill in two names in `people-and-custody.md` section 1. Two, not one.
2. Ask for hsl-web access, with a date.
3. Post the two approver proposal to Hack Your Hackerspace.
4. Write `.github/workflows/ci.yml`: run `db/tests/run.sh`, the three prose gate
   suites, and the voice gate over changed files. Also check every commit in the
   pull request for an LLM attribution trailer, so the hook cannot be bypassed by
   a push from another machine.
5. Build the door controller port, its fake, and the conformance suite. This is
   phase 1 work even though the door ships in phase 5, because three rewrites
   stalled at the door and the point is to retire that risk early.

## 7. Traps

Things that look wrong and are not, and things that already bit somebody.

**The bootstrap escape is not a security hole.** `db/migrations/003_rules.sql`
lets an admin be granted with no approval when fewer than two live admins exist.
That looks like a bypass. It is the only way the system can be bootstrapped or
recovered: a two approver rule cannot bind until two approvers exist, and without
it the database is permanently unadministrable. It closes for good at the second
admin, it grants no power a lone admin does not already have, and every use
raises a warning. Reasoning in `data-model.md` section 3.1. Two earlier versions
of this trigger deadlocked, both of which read as correct.

**Slot 200 arithmetic.** The EEPROM base address is 24, not 0, so slot 200 sits
at `24 + 200*5 = 1024` and writes past the end of a 1024 byte EEPROM, onto the
alarm state bytes. Slot 199 ends exactly at byte 1023. Somebody will try to
"correct" the offset to 1000. It is not 1000.

**The reconcile loop must diff, never rewrite.** The firmware calls
`EEPROM.write` and never `EEPROM.update`, so an unchanged byte still costs an
erase cycle. A blind rewrite every fifteen minutes exhausts the rated 100,000
cycles in under three years. This is why tag numbers are stored uppercase: mixed
case would defeat the diff and rewrite every slot on every pass while reporting
success.

**`space_api.json` cannot grow past about 900 bytes.** The ESP8266 in the wall
parses it with a 1 KB buffer and does not report an error on overflow. It just
silently stops updating. Serve any newer SpaceAPI version at a new path.

**The two approver rule is not in the bylaws.** It is new, introduced by this
project. Never let it be described as an existing lab rule. The two signature
rule people remember is about monetary expenditure.

**Card eligibility is two months, not six.** The public site is stale. The date of
the vote is disputed between two research passes, so the seed row says
`DATE UNCONFIRMED`. Check the bylaws page history before asserting a date.

**`db/migrations/` is the authority for the schema.** `docs/plan/data-model.md`
explains the reasoning and deliberately contains no DDL, because the schema
existed in two places once and they drifted within an hour.

**Test output comes from stderr only.** Every assertion is a `RAISE NOTICE`.
Do not add `\echo` to a test file: it writes to stdout, and merging the two
streams makes the suite flaky in a way that took three attempts to find. Use
`CALL t.note(...)`.

**`pg_isready` lies.** The postgres image runs a temporary server during initdb
and then restarts it, so readiness goes true before the real database exists.
`run.sh` waits for a real query against the real database, twice. That was the
root cause of every phantom "relation does not exist".

## 8. The research is not in this repository

`.research/` is gitignored on purpose. It holds roughly twenty files of source
material: a 66,000 document knowledge vault, Slack exports, mailing list
archives, and adversarial reviews. It contains quoted private conversations and
named individuals, and it is not this project's to publish.

The plan documents cite it, so if you need the evidence behind a claim, ask
whoever handed this to you for the `.research/` directory. It is worth reading
before you disagree with a decision: most of them are downstream of something
somebody said in 2018 that is still true.

## 9. How this was checked

So the next person knows what "green" is worth.

- Every SQL claim was executed against a real Postgres 18, not reasoned about.
  Doing that found two bootstrap deadlocks that read as correct SQL.
- The plan was reviewed adversarially twice: once for technical defects, once as
  the most skeptical member of the lab. Both reviews are in `.research/`.
- A separate consistency pass diffed every document against every other and
  against the SQL.
- The prose gate has 74 tests and lints itself clean, including its own ban lists.
