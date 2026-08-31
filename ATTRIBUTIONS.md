<!-- voice-check: reference -->

# Attributions

Every project this one borrows from, what was taken, and under what licence.
Rule 9 of `CLAUDE.md`.

Two halves. The **prior work** table is hand maintained and covers designs,
schemas, protocols, and code taken from named projects. The **dependencies**
table is generated from the lockfiles by `tools/attributions/generate.py`, which
builds the image each lock installs into and reads every package's own metadata
out of it. There are two locks, `services/api/requirements.txt` and
`tools/import-boundaries/requirements.txt`.

Every licence claim below was read from the repository at the commit named. Where
a repository has no licence, that is recorded as a fact and as an action item,
not glossed over.

---

## Prior work

### HeatSync Labs projects

| Project | Licence | What this project takes |
|---|---|---|
| [heatsynclabs/Open-Source-Access-Control-Web-Interface](https://github.com/heatsynclabs/Open-Source-Access-Control-Web-Interface) | Creative Commons Attribution 3.0, stated in `README.md` | The production data model that the migration reads: the 15 table schema, the `member_level` semantics, the card id to EEPROM slot mapping, the `space_api.json` response contract, and the CanCan authorization matrix as the starting point for the new policies. |
| [heatsynclabs/members_api](https://github.com/heatsynclabs/members_api) | Apache License 2.0, Iced Development, LLC | The 2018 target schema is the direct ancestor of ours. Taken: UUID primary keys with a `legacy_id` column for migration, `citext` for email, the `groups` and `memberships` pair for roles, the `updated_at()` trigger pattern, and the shape of `seedfromold.js` as the model for the legacy import. |
| [heatsynclabs/members_ui](https://github.com/heatsynclabs/members_ui) | Apache License 2.0, Iced Development, LLC | Screen inventory and flow, as prior art for what a members portal has to cover. |
| [heatsynclabs/Open_Access_Control_Ethernet](https://github.com/heatsynclabs/Open_Access_Control_Ethernet) | **No licence file.** Header credits Will Bradley and Short Tie, 2013, branched from `zyphlar/Open_Access_Control_Ethernet`, upstream by Arclight and Danozano. | The controller wire protocol that the door service speaks, and the EEPROM slot model. No firmware code is copied. |
| [heatsynclabs/new-hsl](https://github.com/heatsynclabs/new-hsl) | **No licence file.** | The GANTRY v1.1 design tokens in `src/styles/tokens.css`, which our token layer is a superset of, and the event category colour mapping. |
| [heatsynclabs/hsl-members-site](https://github.com/heatsynclabs/hsl-members-site) | MIT, HeatSync Labs, 2025 | Reviewed as prior art. Nothing copied. |
| [mindblender/hsl_door_api_poller](https://github.com/mindblender/hsl_door_api_poller) | MIT, Jeff Sittler, 2024 | A consumer of `space_api.json`, so it defines a contract we must not break. Nothing copied. |
| [virgilvox/hackerspace-management](https://github.com/virgilvox/hackerspace-management) | MIT, 2026 | Reviewed as prior art. |
| `hsl-forge` brand skill package | Internal HeatSync Labs work product | The GANTRY v2.0 token layer, the logo set, and the voice rules and word lists that `tools/voice-check/` extends. |

### Licence gaps to close

These are real and they block nothing today, because HeatSync Labs owns the
repositories and this is a HeatSync Labs project. They should still be fixed,
because an unlicensed public repository is all rights reserved by default and
that is not what anyone intends.

1. **This repository has no licence file.** It is public, so it is all rights
   reserved by default, which is not the intent. MIT matches `hsl-members-site`,
   `hackerspace-management` and the door poller. Needs a board decision.
2. **`new-hsl` has no licence file.** Our token layer descends from its
   `src/styles/tokens.css`. Ask the board to add one. MIT matches the rest of the
   organisation.
3. **`Open_Access_Control_Ethernet` has no licence file.** Its upstream, the
   Google Code `open-access-control` project, needs its licence identified before
   anyone claims a licence for the fork. Until that is resolved, this project
   implements the protocol from observed behaviour and from the documentation in
   the field manual, and copies no firmware source.
4. The CC BY 3.0 on the Rails app is a documentation licence being used on
   software. It is not a good fit and it should be revisited if that code is ever
   reused rather than retired.

Tracked in `docs/decisions/` and raised with the board before cutover.

---

## Pinned tooling

Hand maintained, because none of this is in a lockfile and the generator below
reads lockfiles. Everything here is pinned to a commit or a digest rather than a
moving tag, so a tag repointed at different code cannot change what runs.

| Tool | Pinned to | Licence | Used for |
|---|---|---|---|
| [actions/checkout](https://github.com/actions/checkout) v7.0.1 | commit `3d3c42e5aac5ba805825da76410c181273ba90b1` | MIT, GitHub | Checking out the repository in every job in `.github/workflows/ci.yml` and `.github/workflows/ci-stacks.yml`. Version, tag commit and licence read from the GitHub API on 2026-08-27 |
| [Redocly CLI](https://github.com/Redocly/redocly-cli) 2.49.0 | the npm version, in the workflow and in `HANDOFF.md` | MIT, Redocly Inc. | Validating `docs/api/members-v1.yaml`, in CI and by hand. Chosen in [ADR 0001](./docs/decisions/0001-openapi-toolchain.md), which records how the version and licence were read |
| [Prism](https://github.com/stoplightio/prism) 5.15.10 | image digest `sha256:586d1f0f94f8d0eaf20b26b8b41f985f2a2d494bea297bd3988c3de3eb87094e`, in `compose.development.yaml` | Apache 2.0, Stoplight | Serving the contract as a mock, for the members portal and for CI. Chosen in [ADR 0002](./docs/decisions/0002-mock-server.md) |
| [Zitadel](https://github.com/zitadel/zitadel) 4.17.1 | image digest `sha256:3ac6910685d48f32481f01f45e3e6215efe5a9df2c069591b481e9a101712db5`, in `compose.yaml` | **AGPL-3.0**, Zitadel. Read from the GitHub API on 2026-08-28, and see the note below | The identity service. Chosen in [ADR 0004](./docs/decisions/0004-identity-service.md) |
| [Ruff](https://github.com/astral-sh/ruff) 0.16.5 | image digest `sha256:8355b79edf35788aef97ac9b1ff3b758604a5d67963ead617c45c72e1d92871f`, in `tools/ceilings/run.sh` | MIT, Astral. Read from the repository `LICENSE` on 2026-08-28 | Three of the five ceilings in rule 6. Chosen in [ADR 0005](./docs/decisions/0005-file-and-function-ceilings.md) |
| [import-linter](https://github.com/seddonym/import-linter) 2.14 and [grimp](https://github.com/seddonym/grimp) 3.16 | the PyPI versions, pinned with hashes in `tools/import-boundaries/requirements.txt` and installed into an image built from `tools/import-boundaries/Dockerfile` | BSD-2-Clause for both, David Seddon, with 44 and 15 contributors behind him. Read from the GitHub API on 2026-08-29 | The layer arrows in rule 5, over the Python in `services/`. Chosen in [ADR 0006](./docs/decisions/0006-import-boundaries.md) and delivered by [ADR 0011](./docs/decisions/0011-import-linter-arrives.md). Nobody publishes an image for it, checked on 2026-08-29 against ghcr.io and Docker Hub, so this repository builds one |
| [bcrypt-ruby](https://github.com/bcrypt-ruby/bcrypt-ruby) 3.1.20 | the gem version, in `tools/identity/tests/generate_hashes.sh`, installed into a throwaway `ruby:3.3-alpine` | MIT, Coda Hale and Jeremy Kemper | Writing the fixture hashes the phase 2 password proof runs on. It is the library the legacy Rails application hashes with, which is the whole reason it is this one and not another |
| [uv](https://github.com/astral-sh/uv) 0.12.7 | the PyPI version, named in the header of `services/api/requirements.txt` | `MIT OR Apache-2.0` on PyPI, Apache-2.0 on the GitHub repository record, Astral. Both read on 2026-08-28 | Compiling `services/api/requirements.in` and `tools/import-boundaries/requirements.in` into locks carrying a hash for every wheel on every platform. It runs when a dependency changes and is not in any image. Chosen in [ADR 0012](./docs/decisions/0012-python-dependencies.md) |
| [python](https://hub.docker.com/_/python) 3.13.15 slim | image digest `sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f`, in `services/api/Dockerfile` and in `tools/import-boundaries/Dockerfile` | Python Software Foundation licence for Python itself, on a Debian trixie base. Digest read from `docker buildx imagetools inspect` on 2026-08-28 and read again unchanged on 2026-08-29 | The base of the members API image, the JWKS server its suite runs, and the image the import boundary gate runs in |

Every other image the stack runs is named by tag: `postgres:18` and
`caddy:2-alpine`. Neither is vendored and neither is modified. `ruby:3.3-alpine`
is not one of them: nothing deploys it, and it is run by hand only when somebody
regenerates the identity fixtures.

**On the AGPL.** Zitadel is run as a published container, unmodified, as a
separate process the stack talks to over HTTP. Nothing in this repository links
against it or embeds it, and no source of ours is derived from it, so the
licence's copyleft reaches nothing here. If somebody ever patches that image,
that changes, and the obligation to offer the modified source starts at the same
moment. Rule 9 says copyleft is checked before the dependency lands rather than
after, and this is that check.

**On the LGPL.** psycopg 3, the Postgres driver the members API imports, is
LGPL-3.0-only. It arrives as a published wheel, unmodified, installed beside the
service rather than vendored into it, and nothing here is derived from its
source. The lab runs the image rather than handing it to anybody, so the
licence's copyleft reaches nothing in this repository. Two things would change
that: copying psycopg into this tree, and publishing an image in which nobody
can replace the library. [ADR 0012](./docs/decisions/0012-python-dependencies.md)
records the check and names pg8000, which is BSD, as the thing to price again if
either happens. Rule 9 says copyleft is checked before the dependency lands
rather than after, and this is that check.

The jobs otherwise run scripts that live in this repository, on the runner's own
Docker, Python and Node, so the CI configuration stays portable enough to be
re-implemented on Woodpecker without rewriting the checks themselves. That is the
exit named in `docs/plan/architecture.md` section 2.

---

## How to add an entry

When you take a design, an algorithm, a schema, or more than a few lines of code
from anywhere:

1. Add a row above, naming what was taken. Not "inspired by", the specific thing.
2. Put a header comment on the borrowed file or function with the project, the
   URL, the licence, and the commit or version.
3. If the licence requires a notice, put it in `licenses/` and reference it.
4. If the licence is copyleft, raise it before the code lands, not after.

Architectural inspiration goes in the ADR that chose it, and the ADR says what
was taken and what was left. "This is the shape Supabase uses internally" is a
citation only when it names the parts.

---

## Dependencies

Generated. `tools/attributions/generate.py` replaces everything between the two
markers and touches nothing else on this page, so anything a person writes about
these packages belongs above the first marker. Run it when a lockfile changes,
in the same sitting that recompiles that lock. It needs docker and the network,
because it builds the image the lock installs into.

The four direct dependencies of the members API are chosen in
[ADR 0012](./docs/decisions/0012-python-dependencies.md), which also carries the
copyleft check on psycopg. Nothing the import boundary gate installs is
copyleft, and none of it reaches a deployment: that image is built to read the
source tree and is never shipped.

<!-- BEGIN GENERATED DEPENDENCIES -->

### `services/api`, from `services/api/requirements.txt`

Read on 2026-08-30, out of an image built from `services/api/Dockerfile`. 21
packages: 4 named in `services/api/requirements.in`, and 17 that arrived with
one of those.

Every version is the one the lock pins. Every licence was read with
`importlib.metadata` out of the installed package's own metadata, and the
fourth column names the field it came from. A licence in bold wants the check
rule 9 asks for before the dependency lands.

tzdata is in the lock and not in this image. The lock is compiled `--universal`
and an image is one platform, so a package another platform needs is pinned
here and installed elsewhere. No licence was read for it.

| Package | Version | Licence | Where the licence was read | Asked for, or brought in by |
|---|---|---|---|---|
| annotated-doc | 0.0.5 | MIT | License-Expression | fastapi |
| annotated-types | 0.8.0 | MIT | License-Expression | pydantic |
| anyio | 4.14.2 | MIT | License-Expression | starlette |
| cffi | 2.1.1 | MIT-0 | License-Expression | cryptography |
| click | 8.5.0 | BSD-3-Clause | License-Expression | uvicorn |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause | License-Expression | pyjwt[crypto] |
| fastapi | 0.141.1 | MIT | License-Expression | asked for |
| h11 | 0.16.0 | MIT | License | uvicorn |
| idna | 3.19 | BSD-3-Clause | License-Expression | anyio |
| psycopg | 3.3.4 | **LGPL-3.0-only** | License-Expression | asked for |
| psycopg-binary | 3.3.4 | **LGPL-3.0-only** | License-Expression | psycopg[binary] |
| psycopg-pool | 3.3.1 | **LGPL-3.0-only** | License-Expression | psycopg[pool] |
| pycparser | 3.0 | BSD-3-Clause | License-Expression | cffi |
| pydantic | 2.13.5 | MIT | License-Expression | fastapi |
| pydantic-core | 2.46.5 | MIT | License-Expression | pydantic |
| pyjwt | 2.13.0 | MIT | License-Expression | asked for |
| starlette | 1.6.0 | BSD-3-Clause | License-Expression | fastapi |
| typing-extensions | 4.16.0 | PSF-2.0 | License-Expression | fastapi, psycopg-pool, pydantic, pydantic-core, typing-inspection |
| typing-inspection | 0.4.4 | MIT | License-Expression | fastapi, pydantic |
| tzdata | 2026.3 | not read: only where `sys_platform == 'win32'` | not installed here | psycopg |
| uvicorn | 0.52.4 | BSD-3-Clause | License-Expression | asked for |

### `tools/import-boundaries`, from `tools/import-boundaries/requirements.txt`

Read on 2026-08-30, out of an image built from
`tools/import-boundaries/Dockerfile`. 8 packages: 2 named in
`tools/import-boundaries/requirements.in`, and 6 that arrived with one of
those.

Every version is the one the lock pins. Every licence was read with
`importlib.metadata` out of the installed package's own metadata, and the
fourth column names the field it came from. A licence in bold wants the check
rule 9 asks for before the dependency lands.

| Package | Version | Licence | Where the licence was read | Asked for, or brought in by |
|---|---|---|---|---|
| click | 8.5.0 | BSD-3-Clause | License-Expression | import-linter |
| grimp | 3.16 | BSD 2-Clause License | License | asked for |
| import-linter | 2.14 | BSD 2-Clause License | License | asked for |
| markdown-it-py | 4.2.0 | MIT | classifier | rich |
| mdurl | 0.1.2 | MIT | classifier | markdown-it-py |
| pygments | 2.21.0 | BSD-2-Clause | License-Expression | rich |
| rich | 15.0.0 | MIT | License | import-linter |
| typing-extensions | 4.16.0 | PSF-2.0 | License-Expression | import-linter |

<!-- END GENERATED DEPENDENCIES -->
