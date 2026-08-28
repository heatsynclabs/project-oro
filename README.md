# Project ORO

Members and door access for [HeatSync Labs](https://www.heatsynclabs.org), a
community workshop in Mesa, Arizona.

This replaces the Rails 3.2.8 application at `members.heatsynclabs.org` and the
software around the Arduino that unlocks the building. The Arduino itself stays.

**Nothing is deployed and nothing in production has been touched.**

## Status

Planning and database. The schema, the rules it enforces, and their tests exist
and run. No services, no apps, no deployment.

| | |
|---|---|
| Built | Schema, row level security, 125 database assertions, a prose gate with 74 tests, a commit hook |
| Not built | The API service, the door service, the three portals, the theme packages, CI |

`HANDOFF.md` tracks this in detail and is the file to update when something
lands.

## Run it

Needs Docker and Python 3.8 or newer. Nothing else.

```sh
./db/tests/run.sh          # schema from nothing, 125 assertions, about 6 seconds
./db/tests/run.sh --update # regenerate expected output, deliberately

python3 tools/voice-check/test_voice_check.py
python3 tools/voice-check/test_regressions.py
python3 tools/voice-check/test_behaviour.py

python3 tools/voice-check/voice_check.py docs/ CLAUDE.md db/ tools/
```

`run.sh` creates a throwaway `postgres:18` container, applies every migration
and seed in order, runs each test file in a transaction that rolls back, and
removes the container.

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
db/tests/            125 assertions, run by db/tests/run.sh

docs/plan/           architecture, API contract, data model, build order
docs/conventions/    voice
docs/decisions/      architecture decision records
docs/glossary.md     domain words. Code uses these exactly

tools/voice-check/   prose gate, run in CI and on every commit message
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
