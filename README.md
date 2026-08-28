# Project ORO

Members and door access for [HeatSync Labs](https://www.heatsynclabs.org), a
community workshop in Mesa, Arizona.

This replaces the Rails 3.2.8 application at `members.heatsynclabs.org` and the
software around the Arduino that unlocks the building. The Arduino itself stays.

**Nothing is deployed and nothing in production has been touched.**

## Status

There is something to open in a browser now. `make development` brings up the
members portal on a laptop, and it reads a mock of the API contract rather than a
service, because the service is not built. Nothing is deployed.

| | |
|---|---|
| Built | The schema and its row level security, 171 database assertions. The members API contract as OpenAPI, and a mock that serves it. The door controller port with its fake and 104 conformance tests. The GANTRY token layer with a contrast validator. A stack of Postgres, Caddy and the identity service, with its four clients, its branding, the proof that it can hold the passwords members already have, and one whole sign in through its screens. A members portal, read only, against the mock. CI on twelve jobs, a prose gate with 77 tests, a commit hook |
| Not built | The API service, so nothing yet reaches the members database over HTTP. The migration carries members and cards and not yet certifications, waivers, payments or door events. The door service itself. The admin and door apps, though their identity clients are registered. `gantry-css` and `gantry-vue` |

`HANDOFF.md` tracks this in detail and is the file to update when something
lands.

## Run it

Needs Docker and Python 3.8 or newer. The API contract check also needs Node,
and nothing else does.

```sh
./db/tests/run.sh                     # schema from nothing, 171 assertions
./db/tests/run.sh --update            # regenerate expected output, deliberately

./services/door/tests/run.sh          # the door port, its fake, 104 tests
./packages/gantry-tokens/tests/run.sh # the theme, every ink on every ground

python3 tools/voice-check/test_voice_check.py
python3 tools/voice-check/test_regressions.py
python3 tools/voice-check/test_behaviour.py

./tools/ci/voice-gate.sh              # the prose gate over every tracked file

make mock-test                        # the contract mock, started, called, removed
make development-test                 # both stack shapes, in a throwaway project
make portal-test                      # the members portal through Caddy
```

`db/tests/run.sh` creates a throwaway `postgres:18` container, applies every
migration and seed in order, runs each test file in a transaction that rolls
back, and removes the container. Expect about ten seconds once that image is
local. The door suite and the theme suite need nothing installed at all.

The three `make` targets need Docker Compose, and each one builds and tears down
its own project, so none of them touches a stack you have up.

To bring the stack up, copy `.env.example` to `.env`, set every value in it, and
run `make up`. Nothing the deployment needs has a default, and the stack refuses
to start on a value nobody chose. The two ports only a laptop reads do have one,
and `.env.example` says which. `make help` lists the rest.

`make development` starts the same stack with additions for a browser to open:
the members portal at the root, the API contract served as a mock under `/v1`,
both behind Caddy on one origin, and the identity service on its own port. They
come from an override file, `compose.development.yaml`, so `make up` starts what
it always started. A laptop serves plain HTTP on `ORO_HTTP_PORT`, so a browser
opens it with no certificate to accept, and
`docs/decisions/0003-plain-http-for-development.md` says what that trades away.
A deployment is unchanged and still serves TLS.

Enable the commit hook once per clone:

```sh
git config core.hooksPath .githooks
```

## Layout

```
CLAUDE.md            working rules, each with a named gate
HANDOFF.md           current state, how to run things, known traps
ATTRIBUTIONS.md      what was borrowed, from where, under what licence

db/migrations/       the schema. This is the authority
db/seed/             tiers, roles, governance parameters
db/tests/            171 assertions, run by db/tests/run.sh

services/door/       the controller port, the fake, the conformance suite
packages/            gantry-tokens: the theme, and the contrast validator
apps/members/        the members portal, read only, against the contract mock

docs/api/            the members API contract, as OpenAPI
docs/plan/           architecture, API design, data model, build order
docs/conventions/    voice
docs/decisions/      architecture decision records
docs/glossary.md     domain words. Code uses these exactly

tools/voice-check/   prose gate, run in CI and on every commit message
tools/ci/            the two checks CI runs that need a git range
tools/mock/          the pinned mock server, and what proves it serves the contract
tools/development/   checks over both stack shapes
tools/members-portal/ checks over the portal, through Caddy
tools/identity/      the phase 2 password proof, and the hashes it runs on
tools/ceilings/      rule 6, in a pinned ruff and a line counter
tools/migration/     the legacy import, and a fixture a replica of the old app wrote

caddy/               TLS, the health route, and the routes each shape serves
compose.yaml         Postgres, Caddy and the identity service. Makefile wraps it
compose.development.yaml  what a laptop adds: the mock, the routes for it, and a
                     port on the identity service
db/init/             the identity role and its database, made once
.github/workflows/   CI. Twelve jobs, and a dormant deploy
```

## Reading order

| File | What it answers |
|---|---|
| `CLAUDE.md` | How we work here |
| `docs/plan/architecture.md` | What the system is, and what would replace each piece |
| `docs/plan/api-design.md` | The contract, written before the services on purpose |
| `docs/plan/data-model.md` | Why the schema is shaped this way |
| `docs/plan/order-of-operations.md` | Build order, with an exit criterion per phase |
| `docs/plan/people-and-custody.md` | Who holds what. The real blocker |

## Starting work

`docs/plan/kickoff.md` is a prompt for picking up the next step. It points at the
rules, the current state, and the traps, and it makes you say which step you are
taking before you write anything.

## Contributing

Open to members and to anyone else who wants to help.

Read `CLAUDE.md` first. It is short and most of it is enforced, not advisory.
Two rules catch people out:

- No LLM is named as an author, co-author, or reviewer, anywhere. The commit
  hook rejects it.
- No em dashes, no emoji, and no substituting a double hyphen for a dash. The
  prose gate rejects it.

Tests come with the change. Database rules are tested at the database level,
because that is where they are enforced.

Decisions go in `docs/decisions/` as short records. Reversing one is fine.
Reversing one without writing down what changed is not.

## Licence

**Not yet decided, and this needs fixing.** A public repository with no licence
is all rights reserved by default, which is not the intent. MIT matches the rest
of the organisation. This needs a board decision, and it is tracked in
`ATTRIBUTIONS.md` alongside the same gap in two other HeatSync repositories.

## Built on other people's work

Prior HeatSync work, without which this would be guesswork:

- **[Open-Source-Access-Control-Web-Interface](https://github.com/heatsynclabs/Open-Source-Access-Control-Web-Interface)**,
  the members app running the lab since around 2010. Its schema, its
  `space_api.json` contract, and its authorization matrix are the starting point
  for everything here.
- **[Open_Access_Control_Ethernet](https://github.com/heatsynclabs/Open_Access_Control_Ethernet)**,
  the door firmware, live since 2013. The controller wire protocol and the
  EEPROM slot model come from reading it. Forked from
  [zyphlar/Open_Access_Control_Ethernet](https://github.com/zyphlar/Open_Access_Control_Ethernet),
  upstream from the Open Access Control project.
- **[members_api](https://github.com/heatsynclabs/members_api)** and
  **members_ui** (Apache 2.0). The 2018 rewrite is the direct ancestor of this
  schema: UUID keys with a `legacy_id` column, `citext` email, roles as rows,
  and an `updated_at` trigger.
- **[hsl-members-site](https://github.com/heatsynclabs/hsl-members-site)**, the
  2025 rewrite, which produced the best annotated schema of the three and got
  membership levels right.
- **[hackerspace-management](https://github.com/virgilvox/hackerspace-management)**,
  the only one of them to model certification expiry and revocation. Adopted.
- **[new-hsl](https://github.com/heatsynclabs/new-hsl)**, the public site, and
  the GANTRY design tokens the theme extends.
- **[hsl_door_api_poller](https://github.com/mindblender/hsl_door_api_poller)**,
  which reads `space_api.json` with a 1 KB buffer and is why that payload has a
  hard size ceiling.

Ideas taken from outside the lab:

- **[SpaceAPI](https://spaceapi.io)**, the open standard behind `space_api.json`.
- **[PostgREST](https://postgrest.org)**. Rejected as the front door, but its
  central idea, that authorization belongs in the database as row level
  security, is kept and is the best part of this design.
- **[Supabase](https://supabase.com)**, for the overall shape: an auth service
  in front of an API in front of Postgres with row level security.
- **Hexagonal architecture** (Alistair Cockburn, 2005), for the door controller
  port and adapter, so the Arduino can be replaced without the API changing.
- **[pg_regress](https://www.postgresql.org/docs/current/regress.html)**, the way
  PostgreSQL tests itself. The database tests here are plain SQL scripts diffed
  against expected output, for the same reasons.
- **Architecture decision records** (Michael Nygard, 2011), for
  `docs/decisions/`.
- **[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)**, problem details for
  HTTP APIs, for the error shape.

Full licence details are in `ATTRIBUTIONS.md`.

## Thanks

To everyone who built and kept running the systems this replaces. The door has
worked for over a decade and the members app has outlived two attempts to
retire it, which is a better record than either usually gets credit for.

To the three previous rewrites. They all stalled, and they still did the most
useful thing available: three people, working separately, in three languages,
independently arrived at nearly the same data model. That agreement is the
strongest evidence this project had, and most of the schema here is downstream
of it.

To the members who wrote down what they actually needed, in meetings and on the
mailing list, sometimes years ago. Most of the requirements in `docs/plan/` are
not new. They were already stated by somebody who had felt the problem.
