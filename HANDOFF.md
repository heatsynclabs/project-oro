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
| 7 | `docs/plan/hsl-web-survey.md` | What the machine this replaces actually is. The only plan document written from a real host |
| 8 | `docs/plan/changes-from-the-original.md` | Diff against the original ORO document and its mockups |
| 9 | `docs/glossary.md` | Domain words. Code uses these exactly |

If you read only two, read `CLAUDE.md` and `people-and-custody.md`. If you are
about to plan where any of this runs, read the survey first: it is the reason
the plan's assumed host is not available.

## 2. What is built, and what is not

This table is the single place this is tracked. Update it as things land.

| Thing | State |
|---|---|
| `db/migrations/` schema, rules, RLS, immutability | **Built.** Applies clean from nothing |
| `db/tests/` and `db/tests/run.sh` | **Built.** 197 assertions across ten files, deterministic. Eight of them are new on 2026-08-31 and are the first in this repository that run seated as an admin, which is how an admin keeping a confirmation date through a change of address survived every earlier pass |
| `db/seed/001_reference.sql` | **Built.** Tiers, roles, governance parameters |
| `tools/voice-check/` prose gate | **Built.** 78 tests. The triad warning required an Oxford comma until 2026-08-31 and this repository writes none, so the check that bans the rule of three could not fire on its own subject. Correcting it took the gate from 17 warnings to 70 over the 260 files tracked at the time, with zero errors either way, and the threshold was left at three. With the seven files this change adds it reads 73 over 269 |
| `tools/mock/` mock server for the API contract | **Built.** `make mock-test`, 14 checks, run by CI. This row said 13 until 2026-08-29, when the suite printed 14/14 and nobody had changed it |
| `tools/development/tests/run.sh` | **Built.** 33 checks over both stack shapes, `make development-test`. It reads the deployment's certificate issuer, asserts a laptop answers plain HTTP with no redirect, calls the identity service under `id.` on the deployment and on its own port on a laptop, and asserts that neither shape serves a contract mock under `/v1`. In CI |
| `.githooks/commit-msg` | **Built.** Install it, see section 3 |
| The plan documents | **Written.** Reviewed adversarially twice. `docs/plan/hsl-web-survey.md` joined them on 2026-08-31 and is the only one written from a real machine rather than from reasoning: what hsl-web is, what it runs, what its database holds, and the three things on it that are credentials |
| The identity service, in the stack | **Built.** Zitadel 4.17.1 in `compose.yaml` with its own database and login on the existing Postgres server, ten minute access tokens, and a first instance created from configuration with no console click. Reached at `id.HOSTNAME` on a deployment and on `ORO_IDENTITY_PORT` on a laptop. [ADR 0004](docs/decisions/0004-identity-service.md) |
| `tools/identity/` password proof | **Built.** 16 checks, part of `make identity-test`, in CI. Part (a) of the phase 2 proof: hashes written by bcrypt-ruby at cost 10 with no pepper, imported and signed in with. It found a real defect, in `tools/identity/README.md`. Two suites beside it need nothing running and go first, so a fault in how a refusal is read, or in the command that can remove somebody's account, is reported before a container starts: 8 checks in `check_api_refusals.py`, which hold `api.search` to reporting a refused search as a refusal rather than as an empty result, hold an unreachable service to a sentence rather than a traceback, and since 2026-08-31 hold a certificate nothing trusts to naming the certificate rather than sending the reader to check a hostname that was already right. And 12 in `check_sign_ins.py` |
| `tools/backup/` backup and the restore drill | **Built.** `make backup`, `make restore`, `make backup-test`, in CI. Gate one of rule 12, which is the first thing above every phase. A backup is two files: the database archive and a roles file, because `oro_api` and `door_reader` are cluster roles that a database archive does not carry, and the archive is full of `GRANT ... TO oro_api`, so a restore without them dies on the first grant. An earlier version of this row, and the commit message that introduced it, said every policy names one of those roles. That is false and was measured: no policy in `db/migrations` names a role at all, every one of them defaults to PUBLIC. The grants are the reason, not the policies. The drill backs up a migrated database, destroys the cluster, restores, and compares 95 things including every card's slot, then makes eight further attempts that have to be refused or to change exactly what they claim. A restore over a database holding members is refused until the caller names how many they are destroying, on the command line: an exported variable is refused outright, because make imports the environment and that would arm every later restore in the shell.

Stopping a restore stops it. `docker exec` does not forward a signal, so an earlier version went on and committed while the operator's terminal had stopped printing; the connection is named and terminated now, and a test kills a restore part way and requires the database not to have moved. `kill -9` is still a limit and is written down in three places rather than fixed, because nothing catches it. The archive is streamed onto the container's `/dev/shm` so no copy of the members database lands on a disk, which is why `compose.yaml` now sets `shm_size: 256mb`: the Docker default is 64MB and a restore refuses an archive that does not fit. That 256 carries an assumption about the size of the real dump, stated where it is set. Also here: `roles_the_archive_needs.sh`, `tests/checks.sh` and `tests/what_a_restore_changes.sh` **It proves the mechanism and it did not take the lab's backup.** That was done on 2026-09-01 by a script written for the occasion, because `backup.sh` and `restore.sh` both hardcode a database named `oro` inside a container and hsl-web has no containers. See the row below. No timer and no offsite copy, so a fire in the lab takes the backups with the server |
| The lab's first backup | **Taken and read back on 2026-09-01. Never restored.** 36 MiB custom archive of the `members` database, 62 MiB of `pg_dumpall` beside it in plain SQL, the roles, the application's `config`, Apache, the TLS key, and a row count per table read in the same sitting. Every checksum matches what hsl-web computed. Staged in `/dev/shm` and copied off, so nothing was written to a disk there: `/` and `/srv` read the same before and after. It closed two open questions. `pg_restore` 14 reads what `pg_dump` 8.4.20 wrote, which was not a given, and the archive is 36 MiB against the 256MB `compose.yaml` assumes where it sets `shm_size`. What it is not: restored, which needs a machine, and safe, because it is one copy in a plain directory on a laptop with FileVault off. **The script that took it is not in this repository either**, so the only working backup procedure the lab has lives on one machine. `docs/plan/hsl-web-survey.md` has the numbers |
| `COMMENT ON` for every table and column | **Built.** `db/migrations/014_column_comments.sql` writes the 147 that were missing, and `db/tests/comments.sql` is the gate rule 10 names, widened from tables to columns. Measured on 2026-08-29 against a database built from the migrations and the seed: 17 relations, 16 tables and the `member_directory` view, and 159 columns between them, of which 12 carried a comment. An earlier version of this row said 12 of 150, which came from parsing `db/migrations` rather than from a database and missed the view's 8 columns and one more. Two comments say that nothing reads the column: `tiers.notes` is set by no seed row, selected by nothing, and absent from the `Tier` object in the contract, and `certifications.legacy_id` has no legacy table behind it. **Four passes have been over these comments and the fourth is the one worth knowing about.** The first wrote them, the second verified them and found 55 defects, the third audited them and found 36 more. The fourth read what actually reached the database rather than what the file says, and found that applying the third's corrections had garbled 25 of the 147: SQL string literal syntax pasted into the prose, a sentence written twice, and one full stop spliced onto a comma. Every one of them passed the gate, because the gate read comments for absent text and for banned characters and never for coherence. It reads for coherence now. The gate asks five questions and watches each one fail against a table it makes and drops: a relation or column with no comment, a comment of nothing but whitespace of any kind, a comment carrying a character rule 11 bans, quoting that leaked out of the migration, a sentence written twice, and a full stop followed by a comma. The dash question reads table and view comments as well as column comments, which it did not until the fourth audit measured an em dash and an emoji sitting in a table comment while the gate said none. One consequence for anybody adding a comment: no standalone quote character, so the file says at time zone UTC rather than quoting it |
| `docs/runbooks/` | **Two files, and one of them cannot be followed on the machine it names.** `restore-the-members-database.md`, ten numbered steps with the output each one prints, which is what created the directory. `deploy-beside-the-legacy-system.md`, thirteen steps for standing this up beside the legacy system, with a rollback and its own gaps section. Step 6 registers the clients, which nothing did until 2026-08-31: it named `configure.py` twice in passing and never ran it, so a deployment following it end to end had no project, no clients, no branding, and no token that could carry the audience `compose.api.yaml` gives the members API. **Steps 3 onward cannot run on hsl-web.** That host is 32 bit CentOS 6.8 on a 2.6.32 kernel and every step from 3 to 11 wants containers, so the document now says so at the top and its assumption block carries the measured answers rather than guesses: three of the seven came back wrong. Steps 1 and 2 do run there and both have been run, which is how the survey and the backup exist. Step 1 also reads the deployed `devise.rb` and `application.rb` now, and step 2 archives the application's configuration beside the dump |
| `tools/bootstrap/` seat the first three admins | **Built.** `make bootstrap-admins`, in CI, 23 checks. A laptop passes its own `ORO_IDENTITY_URL` for the same reason `make identity-configure` needs one. The only path from an empty database to somebody who can administer it, and it spends the escape `013_bootstrap_three_admins.sql` opens. Per person: an identity account, then `link_or_create_member`, then the role, in that order because a member row holding a role is not claimable afterwards. The handover password goes to the terminal and to no file. Safe to run twice, and the fourth admin is refused by the database rather than by the script |
| `tools/migration/` the legacy import | **Built.** `make migration-test`, in CI. Members, cards, the `admin` and `accountant` booleans as roles, and the waiver date as a pointer to where the document is kept. A preflight refuses to start while anything needs a person and names the rows. Eleven cases: ten imports of the same fixture, three that carry and seven that must be refused, plus one that runs the role step alone. Every refusal is checked by its text and not only its exit code. The fixture was written by a replica of the legacy application through its own models |
| `tools/identity/configure.py`, the clients, the branding, the sign up and the mail | **Built.** `make identity-configure`. The project, three public PKCE clients with no secret, the door service machine account, the GANTRY palette on the hosted screens set and activated, the words on the message a new member gets, self registration turned on through `login_policy.py`, and the mail server the codes go through when `--mail-host` is passed. Idempotent, and `check_reconfiguration.py` runs it twice to prove that. `make identity-test` prints 79 across ten files: 8, 12, 16, 10, 3, 6, 6, 6, 8, 4. Eight modules rather than one because the file passed the 300 line ceiling: `api.py` is how to call the service, `registrations.py` what it holds, `clients.py` what a client is, `branding.py` the label policy and its four uploads, `login_policy.py` the Register button in both directions, `messages.py` the words in the message, `mail.py` the SMTP provider, `portal_config.py` the one file it writes. Two flags arrived on 2026-08-31. `--self-registration off` closes the sign up, which a deployment with no mail server needs and had no way to do, and `--no-portal-config` leaves `apps/members/identity.json` alone, which is what a throwaway suite wants: three of them used to repoint a working portal at an instance about to be removed. One more thing about this target and it is the laptop half of the runbook's step 6 defect: it builds the three origins from `ORO_HOSTNAME` with no port, so `ORO_IDENTITY_URL=http://localhost:8180 make identity-configure` registered the portal with a redirect of `https://localhost/` while the portal is served on 8080. The comment above the target used to give that as the laptop example and now gives the direct call instead. A laptop has to pass `ORO_IDENTITY_URL`: the default is built from `ORO_HOSTNAME` as `https://id.<host>` and nothing resolves at `id.localhost` |
| Legacy members signing in | **Demonstrated with invented accounts.** 6 checks in `make identity-test` take hashes the legacy application wrote and sign in with the passwords that produced them. Nine of eleven succeed and the two that do not are over the bcrypt limit. This is not part (b) of the phase 2 proof: every password in it was chosen by whoever wrote the replica |
| `.github/workflows/deploy.yml` | **Written, never run.** Dormant until a server exists and four secrets are set. One step, `make up` over SSH. [ADR 0008](docs/decisions/0008-deploying-from-actions.md), which supersedes what `architecture.md` said about CI never holding a deploy credential |
| Ten minute tokens with rotating refresh | **Built and demonstrated.** 11 further checks in `make identity-test` sign a member in through the real hosted screens, read the access token lifetime off the token, use the refresh token, and prove the previous one stops working |
| The hosted login screens | **Built.** [ADR 0007](docs/decisions/0007-hosted-login-screens.md). The default in 4.17.1 sends a member to a page this image does not serve, so a check asserts the page really carries a login field |
| `services/api/` | **Built, and wired into both stack shapes.** Ten of the contract's twenty four operations, against a real Postgres with the real migrations, with the policies deciding every answer. It logs in as `oro_api_login`, a NOINHERIT role that holds nothing until the transaction runs `SET LOCAL ROLE oro_api`, because five places in the schema branch on `current_user` being `oro_api` and an inheriting role would fire every one of those carve outs. The identity is set with `set_config(..., true)`, which is SET LOCAL, and one test proves an identity does not survive on a pooled connection. Nothing in the service decides who may see what. 96 checks across seven files, `make api-test`, in CI: 19 over the endpoints, 23 over the self service reads, 14 over the door events page, 13 over profile edits, 12 over identity isolation including the seven token refusals, 12 over the first sign in, and 3 over the signing key clock. Plus one refusal proved in `run.sh` itself before the container starts. **It has now been run against the real identity service**, which it never had been: that suite serves its own key set from its own key, so until 2026-08-30 nobody had shown this service accepts a token Zitadel issues. It did not. `services/api/README.md` documented `ORO_API_TOKEN_AUDIENCE` as `oro-members-api` and nothing issues that. A real access token carries an `aud` list of every client id under the project plus the project's own identifier, and the client ids are generated per instance, so `oro-project` is the only entry a container can be given ahead of time. The fix was a value and no code changed. `make api-identity-test` holds it, and the audience is `oro-project`. `compose.yaml` includes `compose.api.yaml`, a separate file only because `compose.yaml` had reached 291 of the 300 lines rule 6 allows. It is at 300 exactly as of 2026-09-01, so the next line added to it fails the ceilings gate and the seam wants finding before that happens rather than after, and both Caddy route files carry `handle_path /v1/* { reverse_proxy api:8000 }`, so the portal reads this service in both shapes and the mock has no route at all. Phase 1 has not exited, so the contract underneath may still move |
| `services/door/` port, fake, conformance suite | **Built.** 104 tests, `services/door/tests/run.sh` |
| `services/door/` HTTP API, reconcile loop, real socket against hardware | Not started. Phase 5 |
| `apps/members/` | **Built, signing in, against the members API.** A landing for somebody signed out, with a Join that opens Registration on the hosted screens and a way in for somebody who already has an account. Then seven views: your record, your cards, entries, certifications, waiver, card access and the directory. The profile is editable, which is the one write a member makes besides the first sign in, and every field it offers is a field of `MemberSelfUpdate`. Sign in is authorization code with PKCE, written as classic scripts with no `import` statement anywhere, deliberately: ADR 0006 makes the first one the condition that brings a lockfile and a hundred packages in. Eight files, each of them under the ceiling after three splits. Three small things were fixed on 2026-08-31, each of them something only a reader would have noticed: the Roles card rendered a heading over nothing for a member holding no role, the note under the directory switches described the state the reader was not in because the box above it is ticked by default, and a website a member had typed in was printed as text rather than as a link. See its README |
| `tools/members-portal/tests/` | **Built.** 58 checks over the portal through Caddy, `make portal-test`, across five files because each ran past the 300 line ceiling as one: 21 of the page against the contract, 11 of appearance, 7 of what it ships and where it reads its client id, 5 of what it claims about the API behind it, and 14 of the profile form. No browser, so it does not see the rendered document: what it can do is read what the document says, and it refuses an EEPROM slot number, the wrong card access wording, and any use of the ink token that fails contrast. One of the seven was asserting a mechanism and was corrected on 2026-08-31: it refused `://` anywhere in a served script as a proxy for a hard coded origin, and a scheme with nothing after it names no origin. It reads a scheme followed by a host now, watched failing against a planted one. In CI |
| `apps/` admin, door | Not started. Phase 3 onward |
| `packages/gantry-tokens` | **Built.** The token layer, the two measured defects fixed, and the contrast checker over the theme by ground cross product. 69 tests plus 112 measured pairs, `packages/gantry-tokens/tests/run.sh`. Sixteen pairs are triaged in `validator/known-failures.txt`, four of them a real `--g-ink-3` defect held open on a brand colour decision. Two files here are generated and this row used to say the package was one file: `brand/hsl-lockup.svg` and `brand/hsl-lockup-dark.svg` are built from the two SVGs the portal masthead carries inline, because the hosted sign in screens take a file and a second copy of a logo is two logos that drift. The suite runs that generator with `--check`, which nothing did until 2026-08-31. The dark file arrived the same day: the light lockup was going into the dark slots, and its ink on that ground measures 1.06 to 1 |
| `packages/gantry-css`, `gantry-vue` | Not started. Later in phase 1 and after |
| `compose.yaml`, `compose.development.yaml`, `Makefile`, `.env.example`, `caddy/`, `db/init/` | **Built.** Postgres, Caddy and the identity service. The override file adds the mock, points Caddy at the development routes and publishes the identity service on a port, so the portal and the mock share one origin over plain HTTP and a browser can open a login screen. `make up` on a clean machine, proven |
| `docs/api/members-v1.yaml` | **Written.** OpenAPI 3.1.1, validates clean. Still needs the review by somebody who did not write it that phase 1 asks for |
| `.github/workflows/ci.yml`, `.github/workflows/ci-stacks.yml` and `tools/ci/` | **Built, and split in two on 2026-08-30.** Twenty one jobs, which was eighteen until 2026-08-31. `ci.yml` keeps the seven that start no container, the door suite, the theme, the contract lint, the prose gate, the contract citations, the lockfile coverage check and the commit message check, and is 150 lines. `ci-stacks.yml` holds the fourteen that do and is 280. The split happened because `ci.yml` had reached 299 lines against the 300 in rule 6 and the next job would have failed the build, and the seam is the one section 3 already named. Every job kept its name and its pinned checkout, so nothing that refers to a job by name has moved. The three added on 2026-08-31 are the browser checks, which were in no workflow at all, the citations gate, and the lockfile coverage check. Both workflows were green on their first run after the split, runs 33346731057 and 33346731067 on 2026-08-31, and the two start together: CI took 20 seconds and CI stacks 52. Measured on those two runs, before the three new jobs: first three admins 49s, identity 48s, legacy import 46s, members API against the identity service 45s, members API 44s, development stack and restore drill 40s each, database 27s, members portal 21s, import boundaries 18s, mock 17s, contract 16s, ceilings 14s, prose 9s, door 8s, theme 6s. The lead moves around, so re-measure rather than quoting this. The attributions generator is deliberately in neither workflow: it needs the network to build three images and it rewrites a tracked file. Its lockfile coverage check is in `ci.yml` because that one needs neither. A separate workflow, the deploy, is dormant and runs only on `workflow_dispatch` with the hostname typed in |
| File and function ceiling linting | **Built.** `make ceilings`, in CI, with 8 tests of its own over a throwaway repository: five put one violation in it and assert the checker catches it, three put something that is not a violation in it and assert the checker stays quiet. Ruff in a pinned container for complexity, parameters and nesting depth, and `tools/ceilings/check_ceilings.py` for the two ceilings no tool measures. [ADR 0005](docs/decisions/0005-file-and-function-ceilings.md). Two files are exempt with a reason, and an exemption that stops being needed fails the check |
| Import boundary linting | **Built on the Python half.** `make import-boundaries`, in CI, with 18 checks of its own over a throwaway tree. Two contracts in `tools/import-boundaries/contracts.ini`, the members API and the door service not importing each other and the door service's domain not importing its adapters, over a graph of 28 files and 41 dependencies which is clean. [ADR 0011](docs/decisions/0011-import-linter-arrives.md) settles how import-linter arrives: nobody publishes an image for it, so this repository builds one from a digest pinned python:3.13-slim and a hashed lock, and 3.13 is deliberate because grimp's only cp314 macOS arm64 wheel is for the free threaded build. Three blind spots have been found by planting violations rather than by reading, and all three are closed by `tools/import-boundaries/check_root_packages.py` beside the contracts. import-linter only sees what `root_packages` reaches, so a module beside the root packages was invisible, and so was a directory inside one with no `__init__.py`, which Python imports through as a namespace package and grimp does not walk into. The third is an import written as a string: `importlib.import_module` or `__import__` with a literal naming a root package loads the door service into the members API while both contracts report kept. A computed name is not findable at all and that limit is written down rather than papered over. Every one of the three is in the suite as an assertion, so the day import-linter stops needing help is the day they go red. The TypeScript half is still genuinely unowed: there is no TypeScript |
| `tools/attributions/generate.py` | **Built.** `make attributions`, `make attributions-check`, with 18 self tests. It builds the image each lock installs into and reads every package's own metadata out of it rather than guessing a licence from a name. Deliberately in no CI workflow: it needs the network to build three images and it rewrites a tracked file. **It read two of the three locks until 2026-08-31**, because the list was a tuple in `generate.py`, so `tools/browser-checks/requirements.txt` landed and `make attributions-check` reported green over four packages it had never seen. That hole is closed twice over: the third lock is a `Source`, and the generator refuses to run while `git ls-files` names a `requirements.txt` `SOURCES` does not, or while `SOURCES` names one git does not track. Three checks in `tools/attributions/test_sources.py`, in `make check` and in a CI job of its own, because that one needs neither the network nor a write |
| `tools/names/` | **Built.** `make names`, in `make check`, in CI. Every name a Python module uses has to exist, read by ruff with F821, F811 and F822 in the same pinned image the ceilings gate uses, with `--isolated` so `ruff.toml` goes on being rule 6's numbers and nothing else. Six self tests plant one broken name at a time. It exists because of one bug: `clients.py` was split out of `configure.py` carrying a use of a constant that stayed behind, and the branch that reads it runs only against an instance an older version of the tool configured, which is the deployment case and the one no suite reaches. `make identity-configure` died on a `NameError` on the one machine that mattered while 70 identity checks were green. It found a second on its first run |
| `tools/citations/` | **Built.** `make citations`, in `make check`, in CI, with 12 self checks over a throwaway pair of files. `docs/api/contract-review-notes.md` cites the contract by line and its own preamble calls a citation that lands in the wrong place a defect. The backticked thing before each number is the authority and the number is derived from it, so `--fix` renumbers and nothing asks anybody for another pass by hand. Measured before it existed on 2026-08-31: twenty five citations carried an anchor and one of them landed, the rest adrift by as much as 150 lines. Thirty land now and thirty three line references carry no anchor at all, which is printed on every run so a green cannot be read as full coverage. Two blocks that keep a record of an earlier state are marked `<!-- citations: frozen -->` and are not read |
| `tools/browser-checks/` | **Built, and in CI since 2026-08-31.** One check that opens the portal in a pinned chromium, lets the page's own script run, and asserts a signed out arrival gets the landing and no view. It writes a screenshot every time, red or green. [ADR 0015](docs/decisions/0015-a-browser-driver.md) chose Playwright. `run.sh` drives a stack somebody else started, which is why it is not in `make check`, and that cost something: the landing arrived the day after this check did, the check went red against a portal that was working correctly, and nothing noticed for a day. `with_its_own_stack.sh` beside it brings up its own compose project on its own ports and drives that, and the CI job runs it and keeps the screenshot |
| The mail catcher, and what needs it | **Built for a laptop.** `compose.development.yaml` runs Mailpit, pinned by digest, loopback only on `ORO_MAIL_PORT`. Registering, a forgotten password and a changed address all end in a code that arrives by mail, and without a server every one of them is a screen asking for a code that can never come. Measured on 2026-08-31 against 4.17.1: an account created through Register lands in `USER_STATE_INITIAL`, the screens show Activate User, and that screen carries a required code field, Next and Resend Code and no way past. `tools/identity/mail.py` writes the provider and activates it, which is the half that cost a day: a provider is created inactive and sends nothing. **It can only ever configure a catcher.** What it writes has no username, no password and TLS off, so a lab relay is configured once by hand and `point_at` refuses rather than replacing a provider it did not write. Activating one deactivates whichever was active, so before that refusal existed the shipped `ORO_MAIL_HOST=mail:1025` reaching a deployment would have taken the relay offline and printed success |
| `CODEOWNERS`, `.sops.yaml` | Not started. Created with the first real name and the first secret |

## 3. Run everything

```sh
git config core.hooksPath .githooks      # once per clone, enables the commit gate

make check                               # every suite below, in one command

./db/tests/run.sh                        # rebuilds the schema from nothing, runs 197 assertions
./db/tests/run.sh --update               # regenerate expected output, deliberately

python3 tools/voice-check/test_voice_check.py
python3 tools/voice-check/test_regressions.py
python3 tools/voice-check/test_behaviour.py

./services/door/tests/run.sh             # the port, the fake, and the conformance suite
./packages/gantry-tokens/tests/run.sh    # the theme, and every ink on every ground

make mock-test                           # the API contract mock, started, called, removed

make development                         # portal at /, contract mock under /v1, one origin, plain HTTP
make development-test                    # 33 checks over both stack shapes, throwaway project
make portal-test                         # 58 checks over the members portal, likewise
make identity-test                       # 79 checks over the phase 2 identity work, likewise
make migration-test                      # eleven cases, ten of them imports: three carried and seven refused
make identity-configure                  # the project, the clients and the branding, against a running stack

make ceilings                            # rule 6, in a pinned ruff and a line counter
make names                               # every name a Python module uses exists
make api-test                            # ten operations against a real Postgres and the real policies
make backup-test                         # back up, destroy the database, restore, compare
./tools/bootstrap/tests/run.sh           # the first three admins seated, and the fourth refused
make browser-checks                      # the portal in a real chromium. Needs a stack already up
./tools/browser-checks/with_its_own_stack.sh   # the same check, bringing up its own stack. This is what CI runs
make api-identity-test                   # the members API against a real token from the real identity service
make attributions-check                  # ATTRIBUTIONS.md against all three lockfiles
make import-boundaries                   # rule 5, over the Python in services/
make citations                           # the line numbers in the contract review notes

./tools/ci/voice-gate.sh                 # the prose gate over every tracked file
./tools/ci/voice-gate.sh origin/main     # or only over what a branch changed
./tools/ci/check-commits.sh origin/main  # every commit message in a range

npx @redocly/cli@2.49.0 lint docs/api/members-v1.yaml   # the API contract
```

Six lines in that block have no CI job. Four are not checks at all:
`git config core.hooksPath` sets up a clone, `make development` starts a stack
and leaves it running, `make identity-configure` registers clients against a
stack that is already up, and `--update` rewrites the expected files. `make
check` is the others in one command, and CI runs them separately so a failure
names the suite. One is a check with no job, on purpose:
`make attributions-check` needs the network to build three images and it
rewrites a tracked file. The part of it that needs neither, whether every
lockfile has a `Source`, is a job of its own.
`make browser-checks` still has none, and it does not need one: it drives a
stack somebody else started, which is right for a laptop, and
`with_its_own_stack.sh` beside it is the same check with a stack of its own and
is what the CI job runs. That was open until 2026-08-31, and the day it cost is
in section 2.

Fourteen of those jobs start containers: the database, the mock, the development
stack, the portal, the identity service, the browser checks, the ceilings, the
undefined names, the import boundaries, the migration, the first three admins,
the restore drill, the members API and the members API against the identity
service. They are the fourteen in `ci-stacks.yml`.
Counted by grepping for docker in the script each job runs, which is also where
the count in section 2 comes from. This paragraph said seven until 2026-08-29,
and it had been wrong since the bootstrap, backup and API jobs landed.

Starting a container does not make a job slow. The ceilings one came in at 4
seconds on run 33236264196. The import boundaries one builds its image the first
time and then reads a graph of 28 files, and the reading is under half a second
on a laptop with the image already built. In CI it took 18 seconds on run
33346731067, most of it the build.
The identity one applies its own schema and seeds an instance before it answers
anything, and the migration one builds eleven databases, which is what makes it
the slowest on run 33228017933 at 58 seconds. On run 33236264196 it came third at 48, behind the development stack and identity at 54 each.

`tools/ci/` holds the two checks that need a git range, so what CI runs is the
same script a person runs rather than a copy of it that drifts. The contract lint
reports six warnings and that is expected;
`docs/decisions/0001-openapi-toolchain.md` says which and why. Four places said
five until 2026-08-31, which is the same defect they had recorded once already
at three: `RecordWasRemoved` landed unreferenced on purpose, says so in its own
description, and nobody moved the count.

`make check` runs twenty two suites in one command, which is what a person wants
at 2am, and each still works on its own. It leaves out two. The contract lint
needs Node, and CI runs it as its own job. `make browser-checks` drives a stack
somebody else started rather than bringing up its own, and the Makefile says so
where the target is. `tools/browser-checks/with_its_own_stack.sh` beside it does
start one, and it stays out too: it builds an image carrying three browsers, and
CI is where that belongs. Everything in `make check` needs Docker and python3, and
`services/api/tests/run.sh` needs openssl and curl as well, both of which are on
a mac and on the runner image.

`make up` starts Postgres, Caddy, the identity service and the members API, and
runs two containers that exit and stay exited: one hands the identity service a
volume it can write to, and one applies the migrations. That is why `make ps`
shows something exited and healthy at the same time. `compose.yaml` includes
`compose.api.yaml`, so the API is in both shapes.
Copy `.env.example` to `.env` and set every value in it first: nothing there has a default, and `make up` refuses rather than
starting on a value nobody chose.

`db/tests/run.sh` needs Docker and nothing else. It creates a throwaway
`postgres:18` container, applies every migration and seed in order, runs each
test file in a transaction that rolls back, and removes the container. It leaves
nothing behind. Expect about ten seconds once the `postgres:18` image is
local, and a first run that pulls it takes longer.

Everything should be green. One flake has been seen, once, and never
reproduced: `test_a_changed_origin_is_applied_and_can_be_put_back` in
`check_reconfiguration.py` failed on a busy machine and passed on the same tree.
The identity service answers that read from a projection it updates after the
write, which `login_policy.py` documents for the neighbouring one, so a
projection lag is the likely cause and nothing has been changed on a guess.

Two suites hard code their ports, `tools/identity/tests/run.sh` and
`tools/members-portal/tests/run.sh`. Each brings up its own compose project, so
neither disturbs a stack somebody is looking at, which is what their headers
promise. Two copies of the same suite at once will collide, which nothing
promised and nobody has needed.

## 4. Decisions already made

Each has reasoning behind it. Do not silently reverse one; supersede it with an
ADR (`docs/decisions/0000-template.md`).

- **Identity: Zitadel.** It imports the existing Devise bcrypt hashes with no
  fork and no bespoke login UI, proven against a running instance on 2026-08-28.
  [ADR 0004](docs/decisions/0004-identity-service.md), which also corrects the
  claim this line used to make: Zitadel is not the only candidate that can do
  this. Logto can too, and Keycloak, the obvious default, cannot without a JAR
  the lab would maintain forever. Pepper is off and cost is 10, and that is
  confirmed against the file hsl-web actually runs rather than against the
  committed copy: read on 2026-08-31, `config.pepper` is commented out and
  `config.stretches` is `Rails.env.test? ? 1 : 10`. The lab's hashes import as
  they are.
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

One of these was answered on 2026-08-31 and it changed the shape of the other
three. `docs/plan/hsl-web-survey.md` is where the readings are.

1. **There is nowhere to run this.** hsl-web cannot, and that is measured rather
   than suspected: it is `i686` on kernel 2.6.32, CentOS 6.8, out of support
   since November 2020, and Docker needs `x86_64` and kernel 3.10 or newer. It
   is not that Docker is missing, it is that Docker cannot be installed. So
   `docs/runbooks/deploy-beside-the-legacy-system.md` cannot be followed past
   step 2 on that host, and every phase from 0 onward is waiting on a machine
   somebody names. `docs/plan/architecture.md` already requires the stack to be
   portable across the lab's R610, a rented box or a laptop, so nothing about
   the architecture moves. What is missing is a machine and a person who owns
   it.
2. **The backup exists and has never been restored.** Taken on 2026-09-01 and
   read back: 36 MiB custom archive, 62 MiB of plain SQL beside it, checksums
   matching what hsl-web computed. That is half of gate one of rule 12. The
   other half needs somewhere to restore it to, which is item 1, and there is
   not room on hsl-web for a second copy of a 520 MB database anyway.
3. **No name is filled in anywhere in `people-and-custody.md`.** Every role is
   TBD. By the rule in that file, a phase does not start while the roles it
   needs are empty. This is deliberate, not an oversight, and it is now also the
   reason item 1 cannot be answered here: choosing a machine is a custody
   decision before it is a technical one.
4. **The two approver rule needs an HYH vote** before it binds anyone. It is a
   new policy this project introduces, and the proposal is step zero of phase 1.

What is no longer blocking, and it was item 2 of this list for the life of the
project: **the shell on hsl-web.** It was granted and used on 2026-08-31. The
credentials and custody problem that had been open since 2013 was answered by
somebody signing in and running read only commands, and the answer produced item
1 above. That is what the exit criterion in `order-of-operations.md` phase 0
meant by "if access cannot be arranged, that is the finding". Access was
arranged, and the finding arrived anyway.

## 6. Do this next

`docs/plan/kickoff.md` is a prompt for picking up one step carefully.
`docs/plan/kickoff-ultra.md` is the one for a session meant to carry several
phases at once.

### Not code, and they decide whether any of this ships

1. **Name a machine that can run this**, and somebody who owns it. hsl-web
   cannot, measured on 2026-08-31, and every phase is behind that. Section 5
   item 1.
2. Fill in two names in `people-and-custody.md` section 1. Two, not one.
3. Post the two approver proposal to Hack Your Hackerspace.
4. **Rotate three credentials that were read off hsl-web on a terminal.** The
   Gmail app password the members site sends through, which is revocable in
   minutes. Whatever `config/s3.yml` holds, which nobody has opened. And the
   door controller password, which does not get rotated on impulse because the
   same value lives in the controller and changing one side stops the door.
   `docs/plan/hsl-web-survey.md` has the detail and none of the three is written
   down in this repository.
5. **Give the backup a second home.** It is one copy in a plain directory on one
   laptop with FileVault off. Section 5 item 2.

Asking for hsl-web access was item 2 of this list for the life of the project.
It was granted and used on 2026-08-31, and what it produced is item 1.

### Finishing what is already here

4. Get `docs/api/members-v1.yaml` reviewed by somebody who did not write it, and
   merged. Phase 1 step 1 asks for that review by name, and everything
   downstream is built against it.
5. **Done.** Pull request 1 was merged into main on 2026-08-29 as a merge
   commit, with all twelve CI jobs green on 9289dff. Note what that did not
   include: nobody outside the change read the diff, because there is nobody
   named to. Main has no branch protection, so none of the CI jobs is a
   required check and the merge button does not wait for them. That is worth
   fixing before the next change lands, and it is a repository setting rather
   than code.
6. **Decided, not built.** [ADR 0010](docs/decisions/0010-bootstrap-token.md)
   proposes minting no machine account at all, so there is no token to revoke or
   to leave behind. It is proposed rather than accepted, because it changes who
   can administer the identity service and `people-and-custody.md` has no name
   in the secret custody row.

   Five things behind it were measured on 2026-08-28 against throwaway stacks.
   The token is a personal access token on the machine user `oro-bootstrap`,
   which holds IAM_OWNER. `DELETE /management/v1/users/{userId}/pats/{tokenId}`
   revokes it, proven by calling it and then getting 401 on a call that had just
   worked. Revoking does not remove the file, so the volume keeps a dead
   credential that looks live. Clearing `ZITADEL_FIRSTINSTANCE_PATPATH` alone is
   worse than doing nothing: the token is still minted and now nobody holds a
   copy. And an administrator credential can be obtained with no bootstrap token
   at all, by signing in as the initial human administrator through the console
   client, which is what makes minting none of it possible.

   The ADR lists the four edits that implement it. None of them is made.

7. Decide whether the second factor prompt should appear. The hosted screens
   offer a member a second factor after the password and let them decline it.
   Nobody has decided anything about MFA, which `order-of-operations.md` lists
   as later, so the prompt is left alone rather than configured away. ADR 0007
   has it as an open question.
8. **Done, except for one part that has nowhere to go.** `configure.py`
   registers the project, the three portals and the door service account through
   the v2 services, each under an identifier this repository chose, so a re-run
   reads back exactly what it wrote rather than looking it up by name.

   How the deprecation was established, because it is not where anyone would
   look: Zitadel does not set the proto `deprecated` option on any of its 310
   management methods. It marks deprecation in the grpc-gateway openapiv2
   operation option instead, and 145 of the 310 carry it. That was read out of
   the descriptors embedded in the image's own binary.

   The branding stays on the v1 management API and that is not unfinished work.
   `AddCustomLabelPolicy`, `UpdateCustomLabelPolicy` and
   `ActivateCustomLabelPolicy` are not marked deprecated, and settings v2 has
   `GetBrandingSettings` and no setter at all. There is nowhere to move it to.

   Two things in `api.py` are still on deprecated methods and were left alone
   deliberately: `machine_token` uses the v1 machine user calls, and
   `import_member` and `set_password` use v2 methods that are themselves marked
   deprecated. The second pair is the password proof, which is the one thing in
   this repository nobody should disturb without a reason.

9. Give the door app the door API in its audience, which
   `docs/plan/api-design.md` section 2 asks for. It cannot be done yet: an
   audience is another project's id and the door API has no project until phase
   5. `configure.py` says so where the client is defined.

10. **Answered on 2026-08-28, and the answer is yes.** Logto 1.42.0 has the
    defect at the same boundary and in the same shape: 72 bytes signs in, 73
    does not, and over the limit is HTTP 500 rather than a wrong password.
    Measured through its real hosted screens against a throwaway instance, with
    the measurement in [ADR 0004](docs/decisions/0004-identity-service.md) under
    the flip condition it settles. That flip condition is now closed and the
    decision does not move.

11. **Decided, not built.**
    [ADR 0009](docs/decisions/0009-password-policy-at-cutover.md) proposes
    keeping the strict policy, writing it into `compose.yaml` rather than
    inheriting it, and telling every member before the day rather than on it.
    Proposed rather than accepted: nobody is named to accept it.

    The reasoning that decided it is that no policy setting keeps anybody out on
    cutover day. An imported hash bypasses complexity entirely, measured on a
    member carrying a hash the legacy replica wrote: signed in with a six
    character password under the strict default, HTTP 201. So relaxing buys
    nothing on the day and costs a weaker floor on every password set afterwards.

    The policy is settable two ways and both were measured:
    `PUT /admin/v1/policies/password/complexity` on a running instance, and
    `ZITADEL_DEFAULTINSTANCE_PASSWORDCOMPLEXITYPOLICY_MINLENGTH` and its four
    siblings at instance creation. The variable names came out of the image's own
    embedded defaults and were then proven by booting a stack with them set.

12. **Done, and one line of this item was wrong.** `tools/migration/` now
    carries `admin` and `accountant` as `member_roles` rows under the exception
    in `data-model.md` section 6.1, and the waiver date as a `waivers` row
    pointing at `legacy.waiver_documents`, which is where a person writes down
    where each document is kept.

    This item used to say `instructor` becomes a role too. It cannot.
    `docs/glossary.md` makes an instructor per tool, `db/seed/001_reference.sql`
    seeds no instructor role and no certifications at all, so a global boolean
    has nothing to become. The import refuses to start while any legacy user
    carries it, and the same is true of `payee`, which has no column anywhere in
    this schema. Both are now decisions the preflight names row by row.

    What is left of the member record: `payment_method`, `exit_reason` and the
    legacy `member` integer have no home and are not carried, and the Devise
    session columns are dropped on purpose. Certifications, payments and door
    events are still not migrated.

13. **Done, and the count in this item was wrong.** 147 `COMMENT ON COLUMN`
    statements landed in `db/migrations/014_column_comments.sql` on 2026-08-29,
    and `db/tests/comments.sql` is the gate. This item said 138 missing out of
    150, which came from parsing `db/migrations`. Measured against a database
    built from those migrations there are 159 columns across 17 relations, the
    `member_directory` view included, and 12 carried a comment. Section 2 has
    the rest.

    Two things worth carrying forward. Two columns turned out to be read by
    nothing at all, `tiers.notes` and `certifications.legacy_id`, and their
    comments say so rather than inventing a purpose. And the gate now asks a
    second question, whether any comment carries a character rule 11 bans,
    because the tool that assembled the migration wrapped three file paths
    across two quoted chunks and put a space inside them. That happened after
    the two passes over the comment text, so only a reader of the migration
    itself could have found it, and one did.

14. **Done.** `NoSuchPath` and `WrongMethod` are declared under
    `components.responses` in `docs/api/members-v1.yaml`, with the slugs,
    statuses, titles and sentences copied from
    `services/api/app/problems.py` rather than paraphrased, which is the promise
    that file makes about its own text.

    Neither is referenced by an operation and that is the answer rather than an
    omission. OpenAPI declares the paths a document has and gives no way to
    declare the absence of one, and a 405 belongs to the path rather than to any
    operation under it: hanging it on `GET /me` would say that operation can
    answer 405, when the 405 comes from `POST /me`, which this document does not
    declare. The reasoning is in `info.description` where a reader meets the
    one shape claim it sits under.

    It costs two `no-unused-components` warnings, so the contract lint went from
    three to five. Four places said three and all four were corrected: this
    file, `docs/decisions/0001-openapi-toolchain.md`,
    `docs/api/contract-review-notes.md` and the comment in
    `.github/workflows/ci.yml`. Warnings do not fail that job.

    It is six now, and the same four places said five until 2026-08-31.
    `RecordWasRemoved` is the third unreferenced response component and it is
    unreferenced on purpose: the 409 on `POST /me` carries two slugs, OpenAPI
    allows one response per status, so that operation declares the pair inline
    and this one is there to be read. Its own description says so. Nobody moved
    the count when it landed, which is what makes this worth writing down twice
    rather than once.

15. **Done, and this item named the wrong five.** Measured
    whitespace insensitively, the contract carried six copies of the sentence,
    not five, one of them wrapped across two lines so a plain grep found five.
    The six were not the six properties this item and finding 3 name.

    `RoleGrant.revoked_by` and `MemberCertification.revoked_by`, which this item
    named, carried no description at all, so the problem was invisible on them
    rather than misstated. Three the item did not name carried the sentence:
    `Card.revoked_by`, `Waiver.recorded_by` and `Approval.target_member`.

    The answer turns on who reads the response rather than on which schema
    carries the property, because `admin_reads_all` in
    `db/migrations/004_security.sql` keys on whether the caller holds admin and
    not on which endpoint answered. So four were corrected, two were described
    for the first time, and two were left alone because `Card` and `Approval`
    are returned only under `/admin/`. `Waiver.recorded_by` is a seventh
    property with this problem that finding 3 never listed, and the finding now
    records that. One decision still covers all seven and nobody has made it.

    A side effect worth knowing: the contract grew by about 136 lines in two
    places, so every line citation in `docs/api/contract-review-notes.md` moved.
    That file says a citation landing in the wrong place is a drift to fix, and
    they are fixed, with one exception now written into its preamble. Finding 3
    keeps its own numbers frozen because the text after its note is the record
    of the state before the edit.

16. **Done, and ADR 0014 has since been reopened by an audit.**
    [ADR 0013](docs/decisions/0013-signing-key-refresh.md) for the key set clock
    in `services/api/app/identity.py`, and
    [ADR 0014](docs/decisions/0014-restoring-without-touching-a-disk.md) for the
    `/dev/shm` choice and the signal handling in `tools/backup/restore.sh`. Both
    are proposed rather than accepted, because nobody is named to accept them.

    Writing 0013 found a defect in its own first draft. The draft said the
    service polls the identity provider once a window forever. It does not:
    `read_key_set()` has two callers, one at start and one that a request
    reaches only by carrying a bearer token.

    0014 has a larger problem and it is now the interesting one. It rejected
    streaming the archive on stdin, the option that leaves nothing at rest at
    all, on a measurement that pg_restore cannot read a pipe. It can. Section 7
    carries the measurement. The record now says plainly that the option it
    rejected is the one it would choose today, prices the flip, and names the
    check that would prove it: the drill already holds a restore part way with a
    lock on `members`, and while that lock is held `ls /dev/shm` has to show no
    archive. The mechanism is deliberately unchanged, because that suite is gate
    one of rule 12 and changing it is its own review.

17. **Done for Python, still owed for JavaScript.** `make import-boundaries`
    landed on 2026-08-29 with
    [ADR 0011](docs/decisions/0011-import-linter-arrives.md), which takes the
    number this directory was missing and settles how `import-linter` arrives.
    The open question ADR 0006 left, whether `services/door` gets a `domain`
    over `adapters` contract, is answered yes in the same change with the reason
    beside the contract.

    What took three passes was not the tool. It was that import-linter holds a
    contract only over what `root_packages` reaches, and two shapes were
    measured reporting both contracts kept while the interpreter loaded the door
    service from the members API: a module beside the root packages, and a
    directory inside one with no `__init__.py`, which Python imports through as
    a namespace package and grimp does not walk into.
    `tools/import-boundaries/check_root_packages.py` refuses both, and both are
    in the suite as assertions rather than as prose, so the day import-linter
    stops needing help there is the day they go red.

    What it does not cover: `apps/` holds no Python at all, and the seven Python
    files under `packages/gantry-tokens/validator/` sit under no rule 5 arrow
    with anything below them, so neither tree has a contract.
    `eslint-plugin-boundaries` still waits on its own flip condition, which is
    the first `import` statement in either tree.

### What the audit of 2026-08-31 left open

Six lanes read the range `9d35357..HEAD` against the running system, each with
its own throwaway stack. Most of what they found is fixed and is in the rows
above. These are the ones that are not, in the order they cost something.

18. **Done.** The deploy runbook has a step 6 that registers them, and every
    step after it moved down by one. It calls `configure.py` directly rather
    than `make identity-configure`, because that target builds the three origins
    from `ORO_HOSTNAME` with no port and step 4 chooses one.

    Two things a deployment needs that nobody had written down, both measured
    on 2026-08-31 against a deployment shaped stack on a non standard port. The
    name has to resolve on the machine, because the identity service works out
    which instance a request is for from the Host header and `configure.py` has
    no `--resolve`. And Python has to be told to trust the certificate: `internal`
    means Caddy issued it from its own authority, the curl beside it passes
    `-k`, and nothing in this repository does. Without the root named in
    `SSL_CERT_FILE` the step stops on `CERTIFICATE_VERIFY_FAILED`, and the
    advice it printed was about `ORO_HOSTNAME` and the stack being up, both of
    which were already right. `api.py` chooses its sentence by which failure it
    was now, and `check_api_refusals.py` holds it.

    The same two variables were added to the `make_a_sign_in.py` command in step
    8, which could not have worked as written: with no `ORO_IDENTITY_URL` it
    defaults to a port on `localhost` that only a laptop publishes.

19. **Done.** `login_policy.close_self_registration` is the other end of the
    same write, `configure.py --self-registration off` runs it, and the no mail
    branch of the runbook now closes the sign up rather than only describing
    what it costs. Which one runs is a flag and is never worked out from whether
    `--mail-host` was given: one variable doing two jobs is the trap ADR 0002
    records.

    The check drives it from the state the step is for and asserts the screen
    rather than the policy, because the policy is the mechanism and the button
    is what a person meets. Watched failing against a `close` that printed its
    line and wrote nothing, and measured both ways through a real authorize
    request: the sign in page carries `name="register"` once with the sign up
    open and not at all with it closed. The runbook carries that curl, with the
    cookie jar, because without one the screens answer 200 with an internal
    error and the grep reads zero for the wrong reason.

20. **Decided, and the carve out is gone for this one field.**
    `enforce_profile_self_edit` clears `email_verified_at` for an admin too,
    their own address included, and an admin who sets both in one statement
    keeps what they set, which is the path a confirmation would be recorded by.
    Everything else an admin may do is unchanged.

    The reasoning: a date that survives an address change is a record claiming
    somebody confirmed an address nobody confirmed. Eight assertions in
    `db/tests/profile.sql` cover it, seated as an admin, which is what nothing
    could do before: every profile edit check ran as a member. Two of the eight
    were watched failing against the old early return.

21. **Measured, and the blocker this item named turns out to be the wrong one.
    Not built.** This said the fix needed a claim the token does not carry,
    which is a change to what the portal asks for and to what the identity
    service asserts. Half of that is wrong.

    The portal already asks for the `email` scope, in `apps/members/identity.js`.
    Measured on 2026-08-31 by signing one member in through the real screens
    twice, once with that scope and once without: the access token carried the
    same eight claims both times, and the id token carried no address either.
    So the scope buys nothing.

    `GET /oidc/v1/userinfo`, called with the member's own access token and no
    credential of this service's, answered 200 with `email`, `email_verified`
    true, and a `sub` matching the token. The address is available today.

    What it costs is the thing worth deciding.
    [ADR 0016](docs/decisions/0016-recording-a-confirmed-address.md) prices it
    and is proposed rather than accepted. Taking it breaks the property
    `services/api/app/identity.py` is built around and states in its first
    paragraph, that this service asks the identity provider nothing on a request
    path. And it needs a schema change: the write runs as `oro_api` with an
    identity set, so the trigger refuses it with "A member cannot mark their own
    email verified", which makes recording a confirmation a system path and
    `db/migrations/008_system_paths.sql` its own review.

22. **Done.** `tools/identity/messages.py` writes the initialization message,
    `configure.py` applies it beside the branding, and a member who registers is
    no longer told "This user was created in Zitadel". The path is
    `PUT /management/v1/text/message/init/en`, read out of the image's own
    embedded document rather than guessed: four spellings were tried against the
    running service first and all four answered 404.

    The organisation's copy rather than the instance default, which is the level
    the label policy is already written at, and it is also the one that named the
    vendor: the instance default says "This user was created" and the
    organisation's said "created in Zitadel". Only that message is written. The
    others are left on the vendor's text because nobody has drafted replacements,
    and rule 10 says a half written set is worse than an honest one.

23. **Done.** `tools/browser-checks/with_its_own_stack.sh` brings up its own
    compose project on its own ports and drives it, and a job in `ci-stacks.yml`
    runs that and uploads the screenshot whether the run was red or green.
    `run.sh` is unchanged and still drives a stack somebody else started, which
    is the right shape for a laptop.

    Not in `make check`. That already runs thirteen suites that start containers
    and this one builds an image carrying three browsers, and a person with
    `make development` up runs `run.sh` as often as they like for the same
    answer.

24. **Done, and closed structurally rather than by adding one entry.**
    `tools/browser-checks/requirements.txt` is a `Source` now, so
    `ATTRIBUTIONS.md` carries its four packages, and
    `generate.py.every_lock_is_covered` refuses to generate while `git ls-files`
    names a `requirements.txt` that `SOURCES` does not, or while `SOURCES` names
    one git does not track. Three checks in `tools/attributions/test_sources.py`,
    in `make check` and in a CI job of its own, because the hole it closes landed
    on main and nothing noticed.

    One thing changed to make the third image readable: `read_metadata.py` is run
    as `python3` rather than `python`. The two `python:*-slim` images carry both
    names and the playwright base is Ubuntu noble, which carries only `python3`.

25. **Done.** `build-the-lockup.py --check` reports rather than rewrites, and
    `packages/gantry-tokens/tests/run.sh` runs it, so a masthead somebody edits
    without rebuilding fails a check. Watched failing against a lockup with a
    line appended. `packages/gantry-tokens/README.md` no longer says the package
    is one file and no build step.

26. **Done.** `build-the-lockup.py` takes the ink per file and writes two, and
    `branding.py` uploads the light one to `logo` and `icon` and the dark one to
    `logo/dark` and `icon/dark`. Measured with the checker in
    `packages/gantry-tokens/validator`: the light ink on the dark ground is
    1.06 to 1, which is the number this item carried, and the dark theme's
    `--bone` on that ground is 14.66.

    The check fetches what the identity service serves rather than comparing the
    files on disk, because the step that could go wrong is the upload choosing a
    slot. Watched failing with the light file put back in both dark slots.

27. **Built, and it covers half the file.** `tools/citations/` resolves the
    backticked thing before each number and compares, so the number is derived
    rather than maintained. `--fix` renumbers and the default writes nothing.
    Twelve self checks, then the real document. In `make check` and in CI.

    What it found is worse than the six this item recorded. Twenty five
    citations carried an anchor on 2026-08-31 and one of them landed; the rest
    were adrift by as much as 150 lines. Thirty are anchored and land now, after
    twelve more were rewritten into the anchored form, and thirty three
    line references carry no backticked anchor at all. That last number is
    printed on every run, green or red, because a gate covering part of a file
    and not saying which part reads as covering all of it.

    Two things a first draft got wrong and are worth carrying. A citation wraps
    across lines, so a line by line read walks past it, which is the same defect
    as the plain grep finding 3 records. And the notes cite other files too: a
    bare `(line 170)` three sentences after `012_close_remaining.sql` was named
    pointed into that file, at `sort_order`, which is also a property in the
    contract. The first draft would have renumbered a correct citation to point
    at the wrong file. Parentheses keep the two apart and finding 6 follows the
    convention the rest of the file already used.

    The blocks in findings 1 and 3 that keep a record of an earlier state are
    marked `<!-- citations: frozen -->` now, in the shape the prose gate already
    uses for a quotation, rather than left to be recognised by their prose. The
    preamble named only the third.

28. **All five done.** The Roles card shows a line when a member holds no role,
    through a `data-empty-for` beside the list, because a list inside a card has
    no section of its own and the `data-empty` a whole view uses does not reach
    it. The directory note describes both states rather than the one the reader
    is not in. A website a member entered is a link, opt in through `data-link`,
    with the scheme checked here as well as in the database because a
    `javascript:` URL in an href runs when somebody clicks it.

    That last one turned a portal check red, and the check was asserting a
    mechanism: it refused `://` anywhere in a served script as a proxy for "no
    hard coded origin". It reads a scheme followed by a host now, watched
    failing against a planted `https://id.oro.heatsynclabs.org`.

    `configure.py --no-portal-config` leaves `apps/members/identity.json` alone
    and all three throwaway suites that configure an instance pass it: the
    identity suite, the first three admins, and the members API against the
    identity service. The last two were found by looking at the file after a
    full `make check` rather than by reading, and each had left it naming a
    different dead port. The origin guard this
    item proposed cannot work, and that is written down where it would have
    gone: the suite passes the real portal origin for a stack that serves the
    portal on another port, and nothing in `portal_config.py` can tell that from
    a deployment.

    The triad warning reads a list written without an Oxford comma now. What
    correcting it cost, measured over the 260 files tracked at the time: the
    prose gate went from 17 warnings to 70, still zero errors. With the seven
    files this change adds it reads 73 over 269. The threshold stays at three,
    because moving it to make the new warnings go away is how a gate stops
    meaning anything, and the comment says plainly that a share of the matches
    are comma spliced sentences no pattern here can tell from parallel items.

### The build that is actually left

Do not read the list above as nearly done. The plan has seven phases, numbered
0 to 6, and not one of them has met its exit criterion.

Phase 0 has started, which it had not before 2026-08-31, and it is further from
exiting than anybody thought. Its first gate wanted a verified restorable backup
of the production database, and half of that exists now: taken, read back,
checksummed. The other half needs a machine to restore onto, and the survey of
hsl-web found that the host the whole plan assumed cannot run any of this. So
phase 0's blocker moved rather than cleared, from an access problem to a hardware
one, and it is section 5 item 1.

Phase 1 has most of its work built and cannot exit without a contract review.
Phase 2 has the left column of its first row built and cannot exit without
volunteers, though its largest unknown is now closed: the deployed `devise.rb`
says no pepper and cost 10, so the lab's 1061 password hashes import as they
are. Phases 3, 4, 5 and 6 have not started. Each row below splits what a session
can build today from what waits on a person, because the two get confused and
the confusion produces a phase that looks finished and is not.

| Phase | Buildable now | Waits on a person |
|---|---|---|
| 2, identity | **The whole left column is built.** The identity service and its own database in the stack, the four clients, ten minute tokens with rotating refresh demonstrated through the real screens, GANTRY on those screens, and the whole synthetic half of the password proof | The real half. Ten members signing in to staging with the password they already use, which needs the production hashes and volunteers. Choose that cohort for a range of password habits, not only a range of account ages: the 72 byte defect is invisible until somebody hits it |
| 3, member management | `services/api/`, the FastAPI service against the merged contract, connecting as `oro_api` and setting the member identity per transaction so the policies apply to it too. Repointing `apps/members` off the mock and onto it. **The migration is built and runs against a replica**, and now carries roles and waivers as well as members and cards, so what is left of it is the certifications, payments and door events | The six decisions section 5 of `people-and-custody.md` lists. **The production dump is no longer one of them**: it was taken on 2026-09-01 and holds 1061 members, 64 cards, 8291 payments and 2.87 million door events. Running the preflight against it needs a Postgres to load it into, which is section 5 item 1. `tools/migration/010_preflight.sql` names four of them row by row when it is run against a real copy, which turns each into a question with a list attached. What `contracts` holds and where signed waivers live are not questions about rows and it does not ask them |
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

**The 72 byte limit belongs to bcrypt, not to the identity service that was
chosen.** Logto was the runner up in ADR 0004 and the obvious thing to reach for
if Zitadel turned out to mishandle the lab's hashes. It does not help: measured
on 2026-08-28, Logto 1.42.0 refuses at exactly the same boundary and answers
with the same HTTP 500. Its log names the cause, `Password should be at most 72
bytes long`, out of hash-wasm rather than out of Go. Two independent
implementations refuse what Ruby truncates, so nobody should go looking for an
identity service that does not have this. The fix, whenever somebody takes it, is
a reset path for the members it locks out.

One thing found alongside it and not yet used: Logto rehashes a bcrypt row to
Argon2i on the first successful sign in, which would name the affected cohort
cheaply after cutover. Whether Zitadel does anything similar has not been
measured, and it is worth ten minutes to somebody planning that day.

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
as a new password for a member who had just signed in with it.
[ADR 0009](docs/decisions/0009-password-policy-at-cutover.md) proposes keeping
the policy and telling every member before the day. It is not accepted yet.

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

**The prose gate and the ceilings gate read `git ls-files`, so a file nobody has
added is a file neither one checks.** Both were green while ten new files sat
untracked beside them, and the file count each one prints is the only thing that
says so.
Measured on 2026-08-28: `git add -N` on the ten took the voice gate from 140
files to 150 and the ceiling checker from 101 source files to 109. Neither found
anything wrong, which is the point. They could not have. Add a new file before
you believe a green run that was supposed to cover it.

**Turning off `role_grant_rules` for the role import is required, not defensive.**
Four admin grants in a single `INSERT` are refused inside that one statement, at
the fourth row, with `Granting admin needs an approval from a second admin`. The
seat numbers in the warnings count 1, 2, 3 across rows of one statement, so the
counting functions do see rows inserted earlier in the same statement and there
is no large-INSERT loophole. `tools/migration/022_roles.sql` disables that one
trigger by name inside the transaction and `tools/migration/tests/run.sh` runs
the same import twice, once with the disable and once with it stripped out of a
copy, so the disable cannot quietly stop being load bearing. That test also
counts the two `ALTER TABLE` lines it strips and fails if they are not there,
because a copy identical to the original would pass while proving nothing.

**`arm_the_rule` only fires at the quota, so importing one or two admins leaves
the escape ajar.** It is a separate trigger and stays on when `role_grant_rules`
is disabled, which is why the import arms the rule on its way through. But
`arm_two_approver_rule` inserts only when `bootstrap_is_spent()`, and that needs
three. Measured: importing two admins leaves `two_approver_armed` empty, and a
third grant with no approval behind it still succeeds afterwards. A lab whose
legacy database holds fewer than three admins comes out of the migration with a
bootstrap seat still open.

**Writing a role onto a member makes their row unclaimable by
`link_or_create_member`.** It refuses with `That member already holds a role and
must be linked by an admin`, which is deliberate: it stops an admin's row being
taken over by whoever turns up with that email address. The consequence is an
ordering constraint. `data-model.md` section 6.1 puts the identity import before
roles, and that is the only order that works. Measured both ways, including that
revoking the role makes the row claimable again, because the check reads
`revoked_at IS NULL`.

**Revoking the bootstrap token does not remove the file.** Measured on
2026-08-28: after a successful `DELETE` of the personal access token, the same
277 bytes were still readable out of the `identity_bootstrap` volume, byte for
byte identical to the token that no longer works. Anybody who copies it out
later gets something that looks like a credential and answers 401. This is one
of the reasons [ADR 0010](docs/decisions/0010-bootstrap-token.md) proposes never
minting it rather than revoking it afterwards.

**A refused search used to read as a search that found nothing.** `api.search`
returned `answer.body.get("result") or []` with no status check, and a refusal
carries no result list, so a 401 and an empty result were the same value. The
visible symptom was `configure.py` reporting `could not create the project: 401`
after the bootstrap token was revoked, which names the wrong operation: the
project existed, the token did not work. Fixed, with checks in
`tools/identity/tests/check_api_refusals.py` that need nothing running. The
general shape is worth remembering: any API wrapper that reads a field out of a
body without looking at the status turns every refusal into a plausible answer.

**A naive timestamp carried into a `timestamptz` column moves, and a verify that
casts the same way agrees with it.** The legacy `waiver` column is `timestamp
without time zone` and `waivers.signed_at` is `timestamptz`, so something has to
say which zone the naive value is in. Left implicit it is read in the session
zone, and the lab's own zone is `America/Phoenix`, which moves every waiver seven
hours. The trap is the second half: an assertion written as
`w.signed_at = u.waiver` applies the identical cast to both sides and passes
whatever the session is set to. `020_migrate.sql` and `024_waivers.sql` read every
one of them `AT TIME ZONE 'UTC'`, because Rails 3.2 stores UTC.

Seven columns are affected, not one. The waiver date was found first and fixed
first, and `members.oriented_at`, `members.created_at`, `members.updated_at`,
`cards.issued_at`, `cards.created_at` and `cards.updated_at` had exactly the
same defect for a while afterwards, with a test in place that was written to
catch it and asserted on none of them. `members.joined_on` is safe on its own
terms: a cast from `timestamp` to `date` involves no zone. `config.time_zone = 'America/Phoenix'` in the
legacy `config/application.rb` is the display zone, and nothing there sets
`config.active_record.default_timezone`, which defaults to `:utc`. Read off the
deployed file on hsl-web on 2026-08-31 rather than off the committed copy, so
this is measured on the machine that wrote the rows. One case in
`tools/migration/tests/run.sh` runs the whole import in `America/Phoenix` and
asserts the instant, and with the UTC read removed it fails.

**A `RAISE EXCEPTION` in its own `DO` block does not stop the next statement,
and that cost a real defect.** `022_roles.sql` turns off `role_grant_rules`. It
first shipped with a guard in one `DO` block and `ALTER TABLE ... DISABLE
TRIGGER` in the statement after it. `RAISE EXCEPTION` aborts only its own
statement, so psql in autocommit went on to the next one and turned the trigger
off, and committed it, in the very script that had just refused to do it. The
hand check that passed it used `ON_ERROR_STOP=1`, which is the only setting
under which it looked right.

Everything is one `DO` block now: the guard, the disable, both inserts, the
re-enable, and a check that the trigger really came back on. A `DO` block is a
single statement, so an exception anywhere in it rolls back the `ALTER` as well,
whether or not the caller opened a transaction and whatever psql was told about
errors. `tools/migration/tests/check_the_guard.sh` runs the file alone, with no
`ON_ERROR_STOP`, and asserts the trigger reads `O` and no row was written. Run
against the old two statement shape that check reports `role_grant_rules is 'D'`.

**Seven sentences in commit messages are wrong, and a commit message cannot be
edited.** An audit on 2026-08-29 read `9d35357..f2b9e47` against the tree and
found these. Each entry names the commit, says what it claims, and gives what
the measurement returns. The files themselves carry the corrected numbers, so
this is here for somebody reading `git log`.

`a277a20` says "006_policies_and_comments.sql wrote the table comments". It
wrote six of them. Seventeen relations carry a table or view comment and eight
migrations write them: 000, 001, 002, 004, 006, 010, 011 and 013. The header of
`006_policies_and_comments.sql` is accurate where the message is not.

`a277a20` says the two deliberately broken comments in `db/tests/comments.sql`
are assembled with `chr()` "because typing either one would put it in a file the
prose gate reads". That holds for the em dash and not for the wrapped path. The
comment block above them types `contract-review- notes.md` in plain text, and on
2026-08-29 `python3 tools/voice-check/voice_check.py db/tests/comments.sql`
reported clean over it. The spaced hyphen rule in `tools/voice-check/rules.py`
wants whitespace on both sides of the hyphen, and a wrapped path has none before
it, so the SQL detector refuses that shape inside the database while the prose
gate allows it everywhere else.

`dbf2e0e` rewrote the comment on the contract job in `.github/workflows/ci.yml`
from "The three warnings" to "The five warnings" and says nothing about doing
it. The two `no-unused-components` warnings that make it five do not exist until
`9780c3f` declares `NoSuchPath` and `WrongMethod`, so `dbf2e0e` shipped a tree
whose CI comment stated a count that was not yet true. The line belonged in
`9780c3f`.

`dbf2e0e` says "Fourteen checks of the gate's own, eight planting a violation
and six requiring silence". At that commit it is nine and five. The five that
require silence are `test_an_adapter_importing_the_domain_is_kept`,
`test_an_adapter_importing_the_domain_one_import_deep_is_kept`,
`test_the_two_services_importing_the_same_outside_module_is_kept`,
`test_an_import_no_directory_here_provides_is_left_alone` and
`test_a_directory_nothing_imports_through_is_left_alone`. Every other check in
the file ends on a nonzero exit. The one that reads as quiet and is not is
`test_a_declared_third_package_puts_the_chain_back_in_the_graph`, whose headline
assertion names `app.door_gateway -> shared.wire` on a contract the gate reports
broken.

`9780c3f` says "Four places said three and all four are corrected here or in the
change that follows". Three places said three as of `dbf2e0e`: `HANDOFF.md` line
123, `docs/api/contract-review-notes.md` line 18 and
`docs/decisions/0001-openapi-toolchain.md` line 128. The fourth, `ci.yml`, had
been rewritten one commit early, per the entry above.

`9780c3f` says "the contract grew by about 136 lines in two places". It grew by
143 across eight hunks. `docs/api/members-v1.yaml` is 2023 lines at `dbf2e0e`
and 2166 at `9780c3f`, and `git show 9780c3f -- docs/api/members-v1.yaml`
carries eight `@@` headers. What the sentence goes on to conclude, that every
line citation in the review notes moved, holds.

`801c83f` describes the portal's signed out front door, the `prompt=create`
join, the PKCE helpers split out of `identity.js` and the landing rules in the
component sheet. None of that is in its diff. `git show --name-only 801c83f`
names no file under `apps/`, and the file it says it added arrived in `c6f6e80`
seventeen seconds earlier, whose own message does not mention any of it. What
`801c83f` carries is the mail server, the branding, the lockup and the
`configure.py` splits. Two messages were written in the wrong order and pushed
that way.

`801c83f` says that after activation "the next screen is the members portal".
Two walks through the real screens on 2026-08-31 got a 2-Factor Setup screen
first, offering an authenticator app, a device factor, Skip and Next, and
reached the portal only after Skip. Section 6 item 7 already holds the multi
factor prompt as an open question, and this is the same thing measured from the
member's side.

`f2b9e47` says of the mock suite "The suite prints 14 and nobody had changed
it". The suite is what changed. `bd55232` added
`test_a_member_is_never_handed_a_door_controller_address`, taking
`tools/mock/tests/check_contract.py` from 13 checks to 14. What nobody had
changed was the `HANDOFF.md` row, and the count that commit corrected it to is
right.
`8348475` says ADR 0014 "carries the measurement that pg_restore cannot read an
archive on a pipe, so a copy has to exist somewhere". pg_restore reads an
archive on a pipe. Measured on 2026-08-29 in `postgres:18`, pg_restore 18.6,
with `restore.sh`'s own flags and the archive arriving only over
`docker exec -i`: exit 0, and every one of 5000 rows came back, with
`/proc/self/fd/0` a pipe inside the container. What is true is narrower.
`/dev/stdin` named as a file argument fails, and `-j` from stdin is refused,
which costs nothing here because `--single-transaction` refuses `-j` anyway.
ADR 0014 rejected the option with the best property under rule 13 on that false
premise, and it now says so and reopens it.

**Docker on a Mac ignores the mode on a bind mount and Docker on Linux does
not.** The import boundary gate's own suite builds a throwaway tree with
`tempfile`, which creates its directory 0700, and mounts it into an image that
runs as uid 1000. On a laptop all fourteen checks passed. On the runner eleven
of them failed with `Could not find tools/import-boundaries/contracts.ini`,
which reads as a missing file and is a permission denied wearing its coat.

Measured on 2026-08-30, each part separately. The image reports
`uid=1000(oro)`. `tempfile.TemporaryDirectory()` reports mode 0700. Inside a
Linux container, uid 1000 reading a 0700 directory owned by another user gets
`Permission denied`, and the same read at 0755 and 0644 succeeds. Docker Desktop
presents a shared directory to the container as readable whatever its real mode,
which is why the laptop could not see any of this.

`harness.py` chmods the tree before it mounts it, and says why where it does.
The gate itself was never affected: the working tree `run.sh` mounts is world
readable in an ordinary checkout. What this cost was one red build on main and
the reminder that a suite green on a laptop has been run on one operating
system.

**A SQL comment built from quoted chunks can name a file that does not exist.**
`db/migrations/014_column_comments.sql` writes each comment as a run of single
quoted strings that Postgres concatenates, which is the house style and is fine.
What is not fine is where the wrap falls. Python's `textwrap` breaks on hyphens
by default, so `docs/api/contract-review-notes.md` came out as one chunk ending
`contract-review-` and the next beginning `notes.md`, and the trailing space that
joins the chunks landed inside the path. The comment in the database named
`docs/api/contract-review- notes.md`. Three paths were broken that way. Neither of the two passes over the comment
text could have caught it, because the wrap happened when the text was written
into the file and both of them read it flowing. The pass that read the migration
found it, and even there it is easy to miss: on the page the hyphen sits at the
end of a line, which is where a hyphen belongs.

`db/tests/comments.sql` now refuses any comment matching an alphanumeric, a
hyphen, a space and an alphanumeric, or carrying any character outside ASCII,
which covers the em dash and the emoji rule 11 bans as well. It watches itself
find both, on a table it makes and drops, and it assembles those two offending
comments with `chr()` rather than typing them, because typing either one would
put it in a file the prose gate reads.

**A workflow file, a Makefile and a portal script are all subject to rule 6,
and all three have hit it.** `.github/workflows/ci.yml` reached 299 of the 300
lines and was split on the seam section 3 already named: the five jobs that
start no container stayed, the rest moved to `ci-stacks.yml`. `Makefile`
reached 301 and the three identity targets moved to `make/identity.mk`, which
`include` pulls back in, and `.mk` was added to the suffixes
`tools/ceilings/check_ceilings.py` counts so that split is a split rather than
a dodge. `apps/members/render.js` reached 321 and the page around the views
moved to `chrome.js`.

Trimming a comment to fit is the wrong trade in all three cases, because the
comments are why anybody can read those files at 2am. Look for the seam the
file already has: each of these three had a divider comment sitting exactly
where the split belonged.

**CentOS 6 forbids sudo without a terminal, and `ssh host "command"` gives
none.** `Defaults requiretty` is in that distribution's shipped sudoers and it is
on hsl-web, measured on 2026-08-31: every attempt answers `sudo: sorry, you must
have a tty to run sudo`. So a script that signs in as a person and elevates
cannot work there, however it is written. `ssh -t` satisfies the rule and then
mangles binary, because a tty rewrites line endings, so a dump travelling that
way arrives corrupt. Base64 survives it, measured, and that is a pipeline nobody
should put a backup through. The clean answers are one line of sudoers scoped to
one account, `Defaults:name !requiretty`, or running as somebody who is already
root. The backup that exists was taken the third way: a script run by hand from
a root shell the operator opened themselves.

**A redirect inside `su postgres -c` is performed by postgres, and a mode 700
directory owned by root refuses it.** Caught by reading rather than by running,
in the script that took the backup, before it ran. `su postgres -c "pg_dump ... >
/root/owned/file"` writes nothing and leaves an empty file that a size check has
to catch. The redirect belongs to the caller: `su postgres -c "pg_dump ..." >
file`, where root does the writing and postgres only produces bytes. The same
shape bites `scp` afterwards, because a directory root created is a directory the
person who runs `scp` cannot read.

**`format()` and ordered aggregates do not exist in Postgres 8.4.** The query in
the deploy runbook that counts every table used both, so it could not have run on
the machine it was written for. `format()` arrived in 9.0 and `ORDER BY` inside
an aggregate call arrived in 9.0. What works on 8.4 is asking for
`schemaname || chr(47) || tablename` and doing the loop in the shell. Nothing
else in this repository targets 8.4, and the legacy replica is 9.6, so this is
the one place the difference shows.

**`pg_restore` refuses an archive from a newer `pg_dump` outright, and reads
older ones.** Measured on 2026-08-31 and 2026-09-01. `pg_restore` 14.18 reads
what 8.4.20 wrote, 149 table of contents entries, and answers `unsupported
version (1.16) in file header` to what 18 wrote. So the compatibility window has
a hard edge in one direction and the check for it is cheap: `pg_restore --list`
against the archive says immediately. A dump travelling down a pipe is fine, also
measured: forcing a non seekable stream and reading the result back gave both a
full listing and a working selective restore.

**A legacy role flag on somebody who left is a security finding, not a data
error.** The legacy system recorded a departure in `exit_reason` and never
cleared the `admin` boolean, so one row says both things and an import that
believes the boolean grants a live admin role to somebody who walked out years
ago. `010_preflight.sql` refuses while any such row exists and names each one.
The same reasoning already applied to a card belonging to nobody, and it took an
audit to notice it applied here too.

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
- The prose gate has 78 tests and lints itself clean, including its own ban lists.
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
- A later pass the same day carried the rest of the member record and found
  three more false claims, all of them saying the legacy `instructor` boolean
  becomes a role. It cannot: `docs/glossary.md` makes an instructor per tool and
  `db/seed/001_reference.sql` seeds no instructor role and no certifications, so
  there is nothing for a global boolean to become. The claim was in this file,
  in `data-model.md` section 6.1, and in a `RAISE NOTICE` that told whoever ran
  the import against production to go and apply an exception that does not
  apply. That pass also found that the eighteen columns above are seventeen,
  because `oriented_by_id` is carried by the same file that counted it as lost.
- Every trigger claim in this file about the role import was taken from a real
  Postgres 18 rather than read off the SQL, including the four admin refusal,
  the lock the disable takes, and that it rolls back with its transaction.
- On 2026-08-31 and 2026-09-01 somebody signed in to hsl-web for the first
  time in this project's life, and the readings are in
  `docs/plan/hsl-web-survey.md`. Three of the seven assumptions the deploy
  runbook carried came back wrong, one of them fatal to the plan: that host is
  32 bit CentOS 6.8 on a 2.6.32 kernel, so Docker is not absent but impossible,
  and the runbook cannot be followed past step 2 there. Postgres is 8.4.20
  rather than 9.6. The database is 520 MB rather than an unknown, and it holds
  1061 members and 64 cards. Two assumptions this project had been building on
  for weeks came back right, and both were read off the file that machine runs
  rather than the copy this repository was given: no pepper, cost 10, and the
  Rails record timezone is UTC. Then the backup was taken, read back and
  checksummed against what the far side computed. Every number in the rows above
  that names hsl-web came from that sitting.
- Later on 2026-08-31 the eleven findings that audit left open were worked
  through in order, and two of them turned out to be wrong about themselves.
  Item 21 said recording a confirmed address needed a claim the token does not
  carry and a change to what the portal asks for. The portal already asks for
  the `email` scope, measured by signing one member in twice through the real
  screens under both scopes and reading the same eight claims back, and
  `/oidc/v1/userinfo` hands the address over to the member's own token today.
  What is actually in the way is a design property, and ADR 0016 prices it.
  Item 28 proposed an origin guard in `portal_config.py` that cannot work,
  because the suite passes the real portal origin for a stack that serves the
  portal somewhere else. And the citation checker item 27 asked for would have
  renumbered a correct citation into the wrong file on its first draft, because
  a bare line number three sentences after a SQL file was named belongs to that
  file. Each of those was caught by running the thing rather than by reading it.
- On 2026-08-31 six lanes audited the range `9d35357..HEAD`, each on its own
  throwaway stack, none touching the one somebody had open. Between them they
  stood the system up from an empty clone, registered through the real screens
  and read the code out of the catcher, drove the portal in a real browser, and
  ran every suite in the repository. What they found that mattered most was not
  a wrong number. `POST /me` answered 500 forever to a member whose record had
  been removed, so the read told them to write a record and the write broke,
  every time, with no way out. `tools/identity/mail.py` would have deactivated
  a lab's working relay and printed success. And `make identity-configure`
  died on a `NameError` on the one instance shape only a deployment has, while
  seventy identity checks were green, which is what `tools/names/` now exists to
  refuse. Every finding this file records was reproduced against a running
  system before it was written down, and the ones still open are in section 6.
