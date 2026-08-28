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
| `db/tests/` and `db/tests/run.sh` | **Built.** 171 assertions, deterministic |
| `db/seed/001_reference.sql` | **Built.** Tiers, roles, governance parameters |
| `tools/voice-check/` prose gate | **Built.** 77 tests |
| `tools/mock/` mock server for the API contract | **Built.** `make mock-test`, 13 checks, run by CI |
| `tools/development/tests/run.sh` | **Built.** 20 checks over both profiles, `make development-test`. It reads the deployment's certificate issuer and asserts the development profile answers plain HTTP with no redirect. Not in CI |
| `.githooks/commit-msg` | **Built.** Install it, see section 3 |
| The plan documents | **Written.** Reviewed adversarially twice |
| `services/api/` | Not started. Phase 3 |
| `services/door/` port, fake, conformance suite | **Built.** 104 tests, `services/door/tests/run.sh` |
| `services/door/` HTTP API, reconcile loop, real socket against hardware | Not started. Phase 5 |
| `apps/members/` | **Built against the contract mock.** The six self service views, read only, no sign in. `docs/plan/api-design.md` section 7 step 2, not phase 3. See its README |
| `tools/members-portal/tests/` | **Built.** 22 checks over the portal through Caddy, `make portal-test`. No browser, so it does not see the rendered document. Not in CI |
| `apps/` admin, door | Not started. Phase 3 onward |
| `packages/gantry-tokens` | **Built.** The token layer, the two measured defects fixed, and the contrast checker over the theme by ground cross product. 65 tests plus 112 measured pairs, `packages/gantry-tokens/tests/run.sh`. Sixteen pairs are triaged in `validator/known-failures.txt`, four of them a real `--g-ink-3` defect held open on a brand colour decision |
| `packages/gantry-css`, `gantry-vue` | Not started. Later in phase 1 and after |
| `compose.yaml`, `compose.mock.yaml`, `Makefile`, `.env.example`, `caddy/` | **Built.** Postgres and Caddy, and a development profile that adds the mock and puts it and `apps/members/` behind Caddy on one origin, over plain HTTP. `make up` on a clean machine, proven |
| `docs/api/members-v1.yaml` | **Written.** OpenAPI 3.1.1, validates clean. Still needs the review by somebody who did not write it that phase 1 asks for |
| `.github/workflows/ci.yml` and `tools/ci/` | **Built.** Seven jobs. Never run on GitHub, see section 7 |
| Import boundary and file ceiling linting | Not started. Phase 0. Three files need their exemption listed here when this lands: `docs/api/members-v1.yaml` at 1,923 lines, `packages/gantry-tokens/tokens.css` at 398, and the copy of that token layer the members portal ships at `apps/members/theme/tokens.css`, which is the same 398 lines and the same reason |
| `tools/attributions/generate.py` | Not started. Needs a lockfile first |
| `docs/runbooks/` | Not started. Created with the first runbook |
| `CODEOWNERS`, `.sops.yaml` | Not started. Created with the first real name and the first secret |

## 3. Run everything

```sh
git config core.hooksPath .githooks      # once per clone, enables the commit gate

./db/tests/run.sh                        # rebuilds the schema from nothing, runs 171 assertions
./db/tests/run.sh --update               # regenerate expected output, deliberately

python3 tools/voice-check/test_voice_check.py
python3 tools/voice-check/test_regressions.py
python3 tools/voice-check/test_behaviour.py

./services/door/tests/run.sh             # the port, the fake, and the conformance suite
./packages/gantry-tokens/tests/run.sh    # the theme, and every ink on every ground

make mock-test                           # the API contract mock, started, called, removed
make mock                                # serve it on 4010 until you stop it

make development                         # portal at /, contract mock under /v1, one origin, plain HTTP
make development-test                    # 20 checks over both profiles, in a throwaway project
make portal-test                         # 22 checks over the members portal, likewise

./tools/ci/voice-gate.sh                 # the prose gate over every tracked file
./tools/ci/voice-gate.sh origin/main     # or only over what a branch changed
./tools/ci/check-commits.sh origin/main  # every commit message in a range

npx @redocly/cli@2.49.0 lint docs/api/members-v1.yaml   # the API contract
```

CI runs everything above except `make mock` and `--update`. `tools/ci/` holds the
two checks that need a git range, so what CI runs is the same script a person
runs, rather than a copy of it that drifts. The contract lint reports three
warnings and that is expected; `docs/decisions/0001-openapi-toolchain.md` says
which and why.

`make mock` is a foreground server that runs until you stop it, so no CI job
could run that one. `make mock-test` starts the mock, checks it, and takes it
down, and CI does run that.

`make up` starts Postgres and Caddy. Copy `.env.example` to `.env` and set every
value in it first: nothing there has a default, and `make up` refuses rather than
starting on a value nobody chose.

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

`docs/plan/kickoff.md` is a prompt that walks somebody through picking up the
next step correctly. Use it to start a session.

In order.

1. Fill in two names in `people-and-custody.md` section 1. Two, not one.
2. Ask for hsl-web access, with a date.
3. Post the two approver proposal to Hack Your Hackerspace.
4. Get `docs/api/members-v1.yaml` reviewed by somebody who did not write it, and
   merged. Phase 1 step 1 asks for that review by name and it is the cheapest
   hour in the project, because everything downstream is built against it.
5. Push a branch and watch CI actually run. It has never run on GitHub, only
   locally, which is the one claim in this repository with no evidence behind it.
6. Add the import boundary and file ceiling linting that phase 0 still owes, and
   list `docs/api/members-v1.yaml` in its exemptions with a reason. It is 1,923
   lines and rule 6 wants exemptions named rather than covered by a glob.

Items 4 to 6 are the code that is left. Items 1 to 3 are not code, and they are
the ones that decide whether any of this ships.

## 7. Traps

Things that look wrong and are not, and things that already bit somebody.

**The bootstrap escape is not a security hole.** `db/migrations/003_rules.sql`
lets an admin be granted with no approval, and
`db/migrations/013_bootstrap_three_admins.sql` bounds that to three such grants
over the life of the database. That looks like a bypass. It is the only way the
system can be bootstrapped: a two approver rule cannot bind until two approvers
exist, so without an escape the database is unadministrable on its first day.
Three rather than two because `people-and-custody.md` section 1 wants a spare in
every role, and at two admins, losing one leaves a rule nobody can satisfy.

It is a quota, spent by use, rather than a threshold on the live admin count.
A threshold of three would hold the escape open for as long as the lab had only
two admins, which is exactly the point at which two people could have satisfied
the rule and should have been made to. Nothing separate records the quota: a
bootstrap grant is already a `member_roles` row with a null `approval_id`.

It closes for good at the third grant, revoking people does not hand it back, it
grants no power a lone admin does not already have, and every use raises a
warning naming which seat it took. Reasoning in `data-model.md` section 3.1. Two
earlier versions of this trigger deadlocked, both of which read as correct.

**A test fixture that seats two admins is not testing the rule.** Below three,
the escape is open, so a refusal test written under that fixture passes because
the grant succeeded rather than because anything refused it. `db/tests/attacks.sql`
seats three on purpose and says so.

**CI has never actually run on GitHub.** Every job in
`.github/workflows/ci.yml` was built by running its steps locally, and the
workflow file passes `actionlint`. The commit gate was proven against a
throwaway clone carrying deliberately bad messages, and it caught both an
attribution trailer and banned vocabulary. What has never happened is a run on a
real runner.

```
ASSUMPTION: the ubuntu-latest runner has Docker, python3, Node and npm, and
            actions/checkout at the pinned commit fetches enough history for the
            two checks that need a range.
CONFIRM BY: push a branch and open a pull request. The first run is the check.
            Docker 28.0.4 and Node 22 were read from actions/runner-images on
            2026-08-27, so the likely failure is the git range, not a runtime.
BLAST RADIUS: a red first build on a workflow file, before any code depends on it.
```

**Two holes in the prose gate, found and left open on purpose.** Neither is
worth fixing blind, and both are worth knowing before somebody trusts a green
run more than it deserves.

`.githooks/commit-msg` has no file suffix, so a directory walk never reaches it,
and naming it directly makes the gate read a shell script as if it were prose.
Shell scripts with a `.sh` suffix are covered.

The spaced hyphen check needs three or more letters on both sides, so
`service - it` passes while `service - was` is caught. Loosening it risks
flagging legitimate writing, so it wants a real look rather than a wider regex.

**`--profile development` starts the mock and does not route to it.** Caddy
picks which file it imports from `caddy/routes/` out of `COMPOSE_PROFILES`, so
the variable form does both jobs and the flag form does only one. Ask for the
development stack with `COMPOSE_PROFILES=development docker compose up`, or with
`make development`, which sets it. That command runs as typed, with nothing
sourced and nothing exported first. The flag form leaves the hostname answering
"No application is deployed here yet" while a healthy mock sits behind it
unreachable, which reads as a broken proxy and is not one.

`make down` and `make logs` carry the matching hazard in reverse, and both
select every profile. Compose resolves the service list from the deployment
otherwise, and a service in a profile is not in it: a plain `down` leaves the
mock running and then cannot remove the network, and a plain `logs` prints
`caddy` and `db` and silently omits the one service the profile added.

**The two profiles do not serve the same scheme.** `make up` serves the hostname
over TLS, unchanged. `make development` serves plain HTTP on `ORO_HTTP_PORT` and
opens no TLS listener at all, so the HTTPS port refuses a connection rather than
answering one. That is deliberate. Under `tls internal` the certificate comes
from Caddy's local authority, Chrome answers it with an interstitial no
automation can click through, and a volunteer clears it only by running
`caddy trust` as an administrator and installing a root certificate into a
machine the lab does not own. `docs/decisions/0003-plain-http-for-development.md`
holds the reasoning. What it costs: a defect that only appears under TLS is
invisible on a laptop. A cookie marked `Secure` is never sent on a plain HTTP
origin, and mixed content cannot happen where nothing is HTTPS. Check that kind
of change against the deployment profile before it ships.

**The route files own their site block, and that is not an accident.**
`caddy/Caddyfile` imports one of them at the top level and opens no site of its
own. Somebody will want to hoist the site block back into that file to stop the
health route appearing twice. It cannot be hoisted: a site address written
`http://` may not carry a `tls` directive, and a file imported from inside a
site block may not open a site. The header of `caddy/Caddyfile` names the two
other arrangements that were weighed. `tools/development/tests/run.sh` calls
`/health` under both profiles, so the repeated route drifting apart fails a
check.

**A compose volume takes no profile, and a bind whose source is missing
becomes a directory.** The `caddy` service is in no profile, so every bind on it
belongs to a deployment as much as to the development stack. Both halves were
measured: with `packages/gantry-tokens/tokens.css` moved aside and the
deployment started, Caddy reported healthy, the stylesheet answered 404, and
Docker created a directory at `packages/gantry-tokens/tokens.css` in the working
tree. `git status` says nothing about it while `packages/` is untracked. So the
portal ships its own copy of the token layer at `apps/members/theme/tokens.css`,
and `make portal-test` fails when it differs from the package by a byte.
Mounting the package inside `apps/members` was never open anyway: Docker has to
create the parent directory of a file bind mount and `/srv/members` is itself a
read only mount, which fails at container start with `make parent dir of
file bind-mount: read-only file system`.

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

**`--update` is a footgun and the runner now defends against it.** Capturing
output with `--update` once laundered five failing assertions into expected
files, and every run afterwards printed "all database tests passed". The runner
now refuses to start if any expected file contains a `FAIL` line, refuses to
capture one, and counts assertions: if a file has twelve `CALL t.must` and
reports eleven results, it aborted partway and that is a failure, not silence.
Do not weaken those checks.

**`current_user` inside a `SECURITY DEFINER` function is the owner, not the
caller's role.** A carve out written as `IF current_user <> 'oro_api'` therefore
fires every time and the gate never applies. Ordinary triggers are fine, because
they run as the caller. In a definer function, gate on the identity setting or
fail closed.

**A view is not covered by the policies underneath it.** Unless a view is
created with `security_invoker = true`, it runs as its owner and bypasses row
level security completely. Both views here once handed rows to a caller with no
identity set while the base tables correctly refused. `member_directory` now sets
that option. `waiver_status` became a `SECURITY DEFINER` function instead,
because a host checking somebody in needs rows an invoker view would filter away.
`db/tests/view_security.sql` asserts both refuse a caller with no identity.

**Read policies without write policies is a trap.** An earlier pass enabled
`FORCE ROW LEVEL SECURITY` and wrote only SELECT policies. The result was that
the API could read correctly and insert nothing, and the tables carrying
authority had no row level security at all while the app role held INSERT and
UPDATE on them, so any member could grant themselves a role or edit the bylaws
numbers. If you add a table, add its write policies in the same change.

**`is_admin()` and `admin_count()` must stay `SECURITY DEFINER`.** They read
`member_roles`, which has row level security forced. Without it they return only
what the caller can see, so a member asking whether somebody else is an admin
gets false and `admin_count()` reads zero for everyone. Every policy that calls
`is_admin()` would then decide on an answer that depends on who is asking.
`db/tests/write_policies.sql` asserts both.

**`t.must_pass` on an UPDATE proves almost nothing.** An UPDATE that matches zero
rows does not raise, so an assertion like "an admin may change this" passes
whether or not the admin could see the row. Two tests were passing vacuously that
way. Use `t.must_change`, which checks rows affected.

**The two approver rule is not in the bylaws.** It is new, introduced by this
project, and it covers admin access changes only. Never let it be described as an
existing lab rule. The two signature rule people remember is about monetary
expenditure.

**The waivers table holds no personal information, on purpose.** It records that
a member signed one, when, and where the document is kept. An earlier draft
stored names, addresses, emergency contacts, guardians and signature IPs. The lab
already keeps waivers somewhere, so a second copy is a second thing to protect
and to leak. `db/tests/waivers.sql` asserts the table has no such column, so
adding one back fails the suite.

**Card access is not a workflow in this system, on purpose.** The bylaws process
happens in a room: a cardholder nominates, the proposal is posted two weeks
ahead, card members vote at Hack Your Hackerspace. An earlier draft modelled that
as a state machine with quorum counting and vote tallies. It was cut as out of
scope. Issuing a card is an ordinary admin action with a note. Do not rebuild
it.

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

**`--color-text-tertiary` is below the contrast minimum on three grounds.** It
aliases `--g-ink-3`, which measures 3.61 on the dark page ground, 3.09 on dark
raised, and 4.29 on hazard in both themes. Those four pairs are listed in
`packages/gantry-tokens/validator/known-failures.txt` with the reason, so the
build is green with them open. They are a held defect, not an exemption on
principle: clearing them means a lighter `--smoke` in the dark theme and a
darker hazard literal, which are brand colour decisions. Until somebody makes
them, a `.g-*` component in gantry-css must not put anything a person has to
read into that token.

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
- The prose gate has 77 tests and lints itself clean, including its own ban lists.
