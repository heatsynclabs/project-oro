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
| `tools/development/tests/run.sh` | **Built.** 23 checks over both stack shapes, `make development-test`. It reads the deployment's certificate issuer, asserts a laptop answers plain HTTP with no redirect, and calls the identity service under `id.` on the deployment and on its own port on a laptop. In CI |
| `.githooks/commit-msg` | **Built.** Install it, see section 3 |
| The plan documents | **Written.** Reviewed adversarially twice |
| The identity service, in the stack | **Built.** Zitadel 4.17.1 in `compose.yaml` with its own database and login on the existing Postgres server, ten minute access tokens, and a first instance created from configuration with no console click. Reached at `id.HOSTNAME` on a deployment and on `ORO_IDENTITY_PORT` on a laptop. [ADR 0004](docs/decisions/0004-identity-service.md) |
| `tools/identity/` password proof | **Built.** 16 checks, part of `make identity-test`, in CI. Part (a) of the phase 2 proof: hashes written by bcrypt-ruby at cost 10 with no pepper, imported and signed in with. It found a real defect, in `tools/identity/README.md` |
| `tools/migration/` the legacy import | **Built.** `make migration-test`, in CI. Members and cards, with a preflight that refuses to start while anything needs a person and names the rows, and the assertions from `data-model.md` section 6.2 checked afterwards. The fixture was written by a replica of the legacy application through its own models |
| `tools/identity/configure.py`, the four clients and the branding | **Built.** `make identity-configure`. The project, three public PKCE clients with no secret, the door service machine account, and the GANTRY palette on the hosted screens, set and activated. Idempotent, and the suite runs it twice to prove that |
| Legacy members signing in | **Demonstrated with invented accounts.** 6 checks in `make identity-test` take hashes the legacy application wrote and sign in with the passwords that produced them. Nine of eleven succeed and the two that do not are over the bcrypt limit. This is not part (b) of the phase 2 proof: every password in it was chosen by whoever wrote the replica |
| `.github/workflows/deploy.yml` | **Written, never run.** Dormant until a server exists and four secrets are set. One step, `make up` over SSH. [ADR 0008](docs/decisions/0008-deploying-from-actions.md), which supersedes what `architecture.md` said about CI never holding a deploy credential |
| Ten minute tokens with rotating refresh | **Built and demonstrated.** 11 further checks in `make identity-test` sign a member in through the real hosted screens, read the access token lifetime off the token, use the refresh token, and prove the previous one stops working |
| The hosted login screens | **Built.** [ADR 0007](docs/decisions/0007-hosted-login-screens.md). The default in 4.17.1 sends a member to a page this image does not serve, so a check asserts the page really carries a login field |
| `services/api/` | Not started. Phase 3 |
| `services/door/` port, fake, conformance suite | **Built.** 104 tests, `services/door/tests/run.sh` |
| `services/door/` HTTP API, reconcile loop, real socket against hardware | Not started. Phase 5 |
| `apps/members/` | **Built against the contract mock.** The six self service views, read only, no sign in. `docs/plan/api-design.md` section 7 step 2, not phase 3. See its README |
| `tools/members-portal/tests/` | **Built.** 22 checks over the portal through Caddy, `make portal-test`. No browser, so it does not see the rendered document. In CI |
| `apps/` admin, door | Not started. Phase 3 onward |
| `packages/gantry-tokens` | **Built.** The token layer, the two measured defects fixed, and the contrast checker over the theme by ground cross product. 65 tests plus 112 measured pairs, `packages/gantry-tokens/tests/run.sh`. Sixteen pairs are triaged in `validator/known-failures.txt`, four of them a real `--g-ink-3` defect held open on a brand colour decision |
| `packages/gantry-css`, `gantry-vue` | Not started. Later in phase 1 and after |
| `compose.yaml`, `compose.development.yaml`, `Makefile`, `.env.example`, `caddy/`, `db/init/` | **Built.** Postgres, Caddy and the identity service. The override file adds the mock, points Caddy at the development routes and publishes the identity service on a port, so the portal and the mock share one origin over plain HTTP and a browser can open a login screen. `make up` on a clean machine, proven |
| `docs/api/members-v1.yaml` | **Written.** OpenAPI 3.1.1, validates clean. Still needs the review by somebody who did not write it that phase 1 asks for |
| `.github/workflows/ci.yml` and `tools/ci/` | **Built.** Twelve jobs, all green on a real runner on 2026-08-28. They run in parallel, so the wall clock is the slowest job and not the sum, and that is the identity one. Five of them start containers, the ceilings one included, because it runs ruff as a pinned image rather than installing it. A thirteenth workflow, the deploy, is dormant and runs only when somebody asks |
| File and function ceiling linting | **Built.** `make ceilings`, in CI, with 8 tests of its own over a throwaway repository: five put one violation in it and assert the checker catches it, three put something that is not a violation in it and assert the checker stays quiet. Ruff in a pinned container for complexity, parameters and nesting depth, and `tools/ceilings/check_ceilings.py` for the two ceilings no tool measures. [ADR 0005](docs/decisions/0005-file-and-function-ceilings.md). Two files are exempt with a reason, and an exemption that stops being needed fails the check |
| Import boundary linting | **Decided, not built.** [ADR 0006](docs/decisions/0006-import-boundaries.md): there is no TypeScript at all and only `services/door` is an importable Python package, so neither gate has anything to refuse yet. Each lands with the first code that gives it something |
| `tools/attributions/generate.py` | Not started. Needs a lockfile first |
| `docs/runbooks/` | Not started. The directory exists on disk, empty and untracked, so a fresh clone does not have it. It gets its first file with the first runbook |
| `CODEOWNERS`, `.sops.yaml` | Not started. Created with the first real name and the first secret |

## 3. Run everything

```sh
git config core.hooksPath .githooks      # once per clone, enables the commit gate

make check                               # every suite below, in one command

./db/tests/run.sh                        # rebuilds the schema from nothing, runs 171 assertions
./db/tests/run.sh --update               # regenerate expected output, deliberately

python3 tools/voice-check/test_voice_check.py
python3 tools/voice-check/test_regressions.py
python3 tools/voice-check/test_behaviour.py

./services/door/tests/run.sh             # the port, the fake, and the conformance suite
./packages/gantry-tokens/tests/run.sh    # the theme, and every ink on every ground

make mock-test                           # the API contract mock, started, called, removed

make development                         # portal at /, contract mock under /v1, one origin, plain HTTP
make development-test                    # 23 checks over both stack shapes, throwaway project
make portal-test                         # 22 checks over the members portal, likewise
make identity-test                       # 33 checks over the phase 2 identity work, likewise
make migration-test                      # the legacy import, refused and then run
make identity-configure                  # the project, the clients and the branding, against a running stack

make ceilings                            # rule 6, in a pinned ruff and a line counter

./tools/ci/voice-gate.sh                 # the prose gate over every tracked file
./tools/ci/voice-gate.sh origin/main     # or only over what a branch changed
./tools/ci/check-commits.sh origin/main  # every commit message in a range

npx @redocly/cli@2.49.0 lint docs/api/members-v1.yaml   # the API contract
```

Four lines in that block have no CI job and none of them could have one. Two are
not checks at all: `git config core.hooksPath` sets up a clone, and
`make development` starts a stack and leaves it running. `--update` rewrites the
expected files. `make check` is the others in one command, and CI runs them
separately so a failure names the suite. Every check in the block has a job.

Four of those jobs start containers and are slow. The identity one is the
slowest by a wide margin, because that service applies its own schema and seeds
an instance before it answers anything.

`tools/ci/` holds the two checks that need a git range, so what CI runs is the
same script a person runs rather than a copy of it that drifts. The contract lint
reports three warnings and that is expected;
`docs/decisions/0001-openapi-toolchain.md` says which and why.

`make check` runs every suite in this repository in one command, which is what a
person wants at 2am, and each still works on its own. It leaves out the contract
lint, which is the last line of the block above: that one needs Node, and
everything else here needs only Docker and python3. CI runs it as its own job.

`make up` starts Postgres, Caddy and the identity service, and runs one
container that exists only to hand the identity service a volume it can write
to, which is why `make ps` shows something exited and healthy at the same time.
Copy `.env.example` to `.env` and set every value in it first: nothing there has a default, and `make up` refuses rather than
starting on a value nobody chose.

`db/tests/run.sh` needs Docker and nothing else. It creates a throwaway
`postgres:18` container, applies every migration and seed in order, runs each
test file in a transaction that rolls back, and removes the container. It leaves
nothing behind. Expect about ten seconds once the `postgres:18` image is
local, and a first run that pulls it takes longer.

Everything should be green. If it is not, that is a real failure: the suite has
been run more than twenty times consecutively without a flake.

## 4. Decisions already made

Each has reasoning behind it. Do not silently reverse one; supersede it with an
ADR (`docs/decisions/0000-template.md`).

- **Identity: Zitadel.** It imports the existing Devise bcrypt hashes with no
  fork and no bespoke login UI, proven against a running instance on 2026-08-28.
  [ADR 0004](docs/decisions/0004-identity-service.md), which also corrects the
  claim this line used to make: Zitadel is not the only candidate that can do
  this. Logto can too, and Keycloak, the obvious default, cannot without a JAR
  the lab would maintain forever. Pepper is off and cost is 10 in the committed
  `devise.rb`, and that still wants confirming against the deployed file.
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

`docs/plan/kickoff.md` is a prompt for picking up one step carefully.
`docs/plan/kickoff-ultra.md` is the one for a session meant to carry several
phases at once.

### Not code, and they decide whether any of this ships

1. Fill in two names in `people-and-custody.md` section 1. Two, not one.
2. Ask for hsl-web access, with a date.
3. Post the two approver proposal to Hack Your Hackerspace.

### Finishing what is already here

4. Get `docs/api/members-v1.yaml` reviewed by somebody who did not write it, and
   merged. Phase 1 step 1 asks for that review by name, and everything
   downstream is built against it.
5. Get pull request 1 reviewed and merged. CI is green, so what is left there is
   a person reading the diff.
6. Revoke the bootstrap token, or decide it should not be minted. It grants
   everything, it sits in a volume until somebody removes it, and it expires in
   a year with nothing watching. `make identity-configure` was the last thing
   that needed it, and that now exists, so the moment to do this has arrived.
   ADR 0004 leaves the shape of it open.

7. Decide whether the second factor prompt should appear. The hosted screens
   offer a member a second factor after the password and let them decline it.
   Nobody has decided anything about MFA, which `order-of-operations.md` lists
   as later, so the prompt is left alone rather than configured away. ADR 0007
   has it as an open question.
8. Move `tools/identity/configure.py` off the v1 management API. Its proto marks
   those methods deprecated in 4.17.1 and still routes them. The v2 service
   accepts an application id of our choosing, which makes a re-run exact instead
   of a lookup by name. Small work, and it wants doing before the next Zitadel
   major.

9. Give the door app the door API in its audience, which
   `docs/plan/api-design.md` section 2 asks for. It cannot be done yet: an
   audience is another project's id and the door API has no project until phase
   5. `configure.py` says so where the client is defined.

10. Find out whether Logto has the 72 byte defect. ADR 0004 has the exact test
    and calls it ten minutes. The answer could change which identity service
    this project runs.

11. Decide what happens to the password policy on cutover day. Every migrated
    member can sign in and most of them cannot change their password: the
    legacy application asked for six characters and nothing else, and the
    identity service defaults to eight with an uppercase, a lowercase, a number
    and a symbol. Either relax the policy to match what members already have, or
    tell every member before the day rather than on it. Section 7 has the
    measurement.

12. Carry the rest of the member record. `tools/migration/` moves members and
    cards. It reports what it does not carry, and that list is the work:
    `admin`, `instructor` and `accountant` become roles and need the exception
    in `data-model.md` section 6.1, the waiver dates need somewhere to say where
    a document is kept, and nobody has decided what a `payee` is for.

### The build that is actually left

Do not read the list above as nearly done. The plan has seven phases, numbered
0 to 6, and not one of them has met its exit criterion. Phase 0 has not started
at all, because it needs a shell on hsl-web. Phase 1 has most of its work built
and cannot exit without a contract review. Phase 2 has the left column of its
first row built and cannot exit without volunteers. Phases 3, 4, 5 and 6 have
not started. Each row below splits what a session can build today from what waits on
a person, because the two get confused and the confusion produces a phase that
looks finished and is not.

| Phase | Buildable now | Waits on a person |
|---|---|---|
| 2, identity | **The whole left column is built.** The identity service and its own database in the stack, the four clients, ten minute tokens with rotating refresh demonstrated through the real screens, GANTRY on those screens, and the whole synthetic half of the password proof | The real half. Ten members signing in to staging with the password they already use, which needs the production hashes and volunteers. Choose that cohort for a range of password habits, not only a range of account ages: the 72 byte defect is invisible until somebody hits it |
| 3, member management | `services/api/`, the FastAPI service against the merged contract, connecting as `oro_api` and setting the member identity per transaction so the policies apply to it too. Repointing `apps/members` off the mock and onto it. **The migration is built and runs against a replica**, so what is left of it is the certifications, waivers, payments and door events | The production dump, and the six decisions section 5 of `people-and-custody.md` lists. `tools/migration/010_preflight.sql` names them row by row when it is run against a real copy, which turns each one into a question with a list attached |
| 4, admin | `apps/admin`, the two approver flow in the service over the database rules that already enforce it, card issue and revoke with a reason, waiver status for hosts | The HYH vote. If it fails, the trigger and the constraint are dropped and the portal loses a step. That branch is already written down |
| 5, door | The door service HTTP API, the reconcile loop, the SQLite snapshot and the buffered event log, all against the fake that exists and passes the conformance suite | The real adapter, the VLAN, and a week of read only running beside the live system |

The exit criterion for phases 2, 3 and 5 cannot be met without the right hand
column. Build the left, and never record a phase as exited when only the left is
done.

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

**CI has run, and the assumption it carried is settled.** This entry used to say
every job had only ever been run locally, with an assumption block about whether
the runner had Docker, python3, Node and npm, and whether the pinned checkout
fetched enough history for the two checks that need a git range. Pull request 1
answered it on 2026-08-28: first all seven jobs green in 22 seconds, then all
eleven in 46, then all twelve, the commit message check and the changed files
gate included, so the history was deep enough. The four jobs added later start containers on the
runner's own Docker and none of them needed anything installed.

Kept rather than deleted, because the next person adding a job should know the
question was asked and how it was answered. A job that needs more history than
the others still has to say so.

**Two holes in the prose gate, found and left open on purpose.** Neither is
worth fixing blind, and both are worth knowing before somebody trusts a green
run more than it deserves.

`.githooks/commit-msg` has no file suffix, so a directory walk never reaches it,
and naming it directly makes the gate read a shell script as if it were prose.
Shell scripts with a `.sh` suffix are covered.

The spaced hyphen check needs three or more letters on both sides, so
`service - it` passes while `service - was` is caught. Loosening it risks
flagging legitimate writing, so it wants a real look rather than a wider regex.

**There is one way to start the development stack, and there used to be two.**
`make development`, which runs
`docker compose -f compose.yaml -f compose.development.yaml up`. That is the
whole mechanism.

It was a compose profile until 2026-08-28, and the profile is why this entry
exists. Caddy picked its route file out of `COMPOSE_PROFILES`, so one variable
both started the mock and routed to it. That meant the documented form worked
and `docker compose --profile development`, which is the form Docker's own
documentation teaches, started the mock and left Caddy serving the deployment
404 in front of it. The Caddyfile documented that rather than removing it. If
you find yourself deriving one setting from another to save a line, this is what
it costs. ADR 0002 carries the record.

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
`/health` under both shapes, so the repeated route drifting apart fails a
check.

**A bind whose source is missing becomes a directory.** Docker does not fail on
one; it creates a directory at that path in the working tree, and the stack
comes up healthy serving nothing where a file was. Measured: with
`packages/gantry-tokens/tokens.css` moved aside and the stack started, Caddy
reported healthy, the stylesheet answered 404, and a directory appeared in its
place. `git status` says nothing while that path is untracked.

So Caddy binds the `packages/gantry-tokens` directory, which is tracked, and the
development routes serve it at `/theme`. The portal used to ship a byte
identical copy of the token layer with a check to catch the two drifting apart,
which is a defect and a detector for it where one file does. `make portal-test`
fails if that copy comes back. Mounting a file inside `/srv/members` is not open
anyway: Docker creates the parent directory of a file bind and that path is
itself a read only mount, which fails at container start.
**A database volume older than `db/init/` has no identity database, and the
stack will not start on it.** The postgres image runs
`/docker-entrypoint-initdb.d` once, against an empty data directory, and never
again. Anybody who ran `make up` before the identity service landed has a volume
that predates `db/init/001_identity_role.sql`, and the db healthcheck now asks
for the `identity` database, so it reports unhealthy and `make up` times out.
The message from `make up` names this. The fix is
`docker compose down --volumes`, which is safe today because that stack's
database is empty by design and `make down` deliberately keeps the volume, or
running the two statements in that file by hand with `make psql`.

**A bcrypt password over 72 bytes signs in to the Rails app and not to the
identity service.** Measured, both ways, on 2026-08-28. Ruby's bcrypt truncates
its input at 72 bytes and verifies against the first 72, so the legacy
application accepts a password of any length. Go's refuses, and the identity
service turns that refusal into HTTP 500 with the text `An internal error
occurred`, not into a wrong password. The boundary is exact: 72 bytes signs in,
73 does not.

Bytes, not characters. A passphrase of 27 Japanese characters is 81 bytes and
nothing about it looks long. And the members it affects cannot be found in
advance, because finding them would need the plaintext. `tools/identity/README.md`
carries the measurement and the three options. The suite asserts the behaviour as
it stands, so an improvement fails a check rather than passing quietly.

**docker cp cannot read a file on a tmpfs.** It reads the container filesystem,
and a tmpfs is not part of it, so the file is written correctly and the copy
reports it missing. Measured on 2026-08-28 with `docker exec` printing a file
that `docker cp` said was not there. This cost an hour, because the identity
image is distroless and `docker cp` is the only way to read anything out of it,
so a tmpfs looked like the right place for a token that should not touch disk
and was in fact the one place it could not be read from. It is a named volume
now, and `identity_bootstrap` owns making that volume writable.

**A named volume is created owned by root, and the identity service runs as uid
1000.** Without the `identity_bootstrap` service that chowns it first, the setup
writes half the first instance, dies on `open /bootstrap/pat: permission denied`,
and then cannot retry: the second attempt fails on a unique constraint over the
instance domain it already wrote, and `restart: unless-stopped` puts it in a
loop that compose still counts as started. The recovery from that state is
`docker compose down --volumes`. There is no forward path.

**The slot on the door controller is the legacy card row's primary key.**
`app/models/card.rb` in the legacy application builds its request as
`m#{self.id}`, so an integer primary key is an EEPROM address, and an admin
types it in through a form offering 10 to 200. That form offers slot 200, which
the firmware cannot hold: 200 sits at byte 1024 and writes past the end of the
EEPROM. `tools/migration/030_verify.sql` refuses to finish if any card moved.

**Every migrated member can sign in, and most of them cannot change their
password.** The legacy application asked for six characters and nothing else,
read from devise 2.2.7's `lib/devise.rb`. Zitadel 4.17.1 defaults to eight with
an uppercase, a lowercase, a number and a symbol, read from its
`cmd/defaults.yaml`. An imported hash is a hash rather than a password, so it
bypasses the policy and the member gets in. The wall is the first password
change. Measured: the identity service refused `correct horse battery staple`
as a new password for a member who had just signed in with it. Somebody has to
decide whether to relax the policy or to tell every member on cutover day.

**A legacy password can be longer than 72 bytes by a wide margin.** Devise
allowed 128 characters, and it counted characters rather than bytes, so a UTF-8
password could reach 512. bcrypt reads 72 and wraps at the first NUL byte, in
`ext/mri/crypt_blowfish.c`. That is the mechanism behind the 71, 72, 73
boundary in `tools/identity/README.md`.

**The identity service ships pointing at login screens it does not serve.**
Zitadel 4.17.1 defaults `Features.LoginV2.Required` to true, so its authorize
endpoint redirects a member to `/ui/v2/login`, and the
`ghcr.io/zitadel/zitadel` image answers that path with
`{"code":5, "message":"Not Found"}`. Those screens are a second container. The
stack is healthy the whole time and every check that speaks to the API passes,
which is how this survived a full green suite before anybody looked.
`ZITADEL_DEFAULTINSTANCE_FEATURES_LOGINV2_REQUIRED` set to false uses the
screens the same binary serves. ADR 0007 has the reasoning, and
`check_configuration.py` asserts the page carries a field to type a login name
into, so flipping it back turns five checks red.

**Python's cookie jar drops cookies for a host with no dot in its name, and
localhost has no dot.** A check written with the default policy gets the login
screen's shell with the title "An internal error occurred" instead of the login
form, because the authorization request is bound to a user agent cookie that was
never kept. It answers 200 either way. `tools/identity/flow.py` carries a
policy that keeps them, and the same code with the default policy was measured
failing beside it.

**The variable that reads as though it sets the access token lifetime does
not.** `ZITADEL_OIDC_DEFAULTACCESSTOKENLIFETIME` is the fallback for an instance
that has no setting of its own, and setup gives this instance one, so setting it
alone leaves tokens at the 12 hour default. Measured: a real token through a real
grant carried 43200 seconds with that variable set to `10m`. The one that works
is `ZITADEL_DEFAULTINSTANCE_OIDCSETTINGS_ACCESSTOKENLIFETIME`, and it seeds the
instance at setup, so changing it later needs the instance updated through the
API rather than a restart. `tools/identity/tests/check_identity.py` reads the
`exp` and `iat` claims off a real token and asserts 600, so this cannot come
back quietly.

**The identity service resolves which instance a call is for from the Host
header.** A call to `127.0.0.1` on the right port is refused with `Instance not
found. Make sure you got the domain right`, which reads like a routing fault and
is not one. Use the name it was configured with, or `curl --resolve`.

**The bootstrap token is written once, and it is durable.** The first setup
writes it into the `identity_bootstrap` volume and every later start skips that
step, because it records that it ran. It survives restarts and container
recreates, measured on 2026-08-28 by recreating the container and reading the
same token back. Only `docker compose down --volumes` removes it, and that
removes the identity database in the same breath, so there is no state where the
instance exists and the token does not.

The risk is the other way round. It administers the whole instance, it expires
in a year, and nothing revokes it. Section 6 item 6 pairs registering the four
clients with revoking it, because that is the moment it stops being needed.

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
- The legacy side is not reasoned about either. A replica of the Rails
  application runs its own schema and its own models on postgres 9.6, and the
  migration fixture is what that replica wrote.
  `tools/migration/README.md` says how to rebuild it and names the two things
  about it that are not the legacy application.
- On 2026-08-28 an audit read every numeric claim in the prose against a command
  and found six wrong, including two tables inside plan documents that still
  recorded GitHub as holding no deploy credential after ADR 0008 had reversed
  it. The same pass found that the migration dropped eighteen legacy columns
  without saying so, three of them access, and that the parser reading the
  legacy dump matched fields by position rather than by name.
