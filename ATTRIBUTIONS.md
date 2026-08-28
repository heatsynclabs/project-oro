<!-- voice-check: reference -->

# Attributions

Every project this one borrows from, what was taken, and under what licence.
Rule 9 of `CLAUDE.md`.

Two halves. The **prior work** table is hand maintained and covers designs,
schemas, protocols, and code taken from named projects. The **dependencies**
table will be generated from the lockfiles by `tools/attributions/generate.py`,
which is not written yet because there is no lockfile to read. Until then the
dependencies section below says so rather than looking complete.

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
| [actions/checkout](https://github.com/actions/checkout) v7.0.1 | commit `3d3c42e5aac5ba805825da76410c181273ba90b1` | MIT, GitHub | Checking out the repository in every job in `.github/workflows/ci.yml`. Version, tag commit and licence read from the GitHub API on 2026-08-27 |
| [Redocly CLI](https://github.com/Redocly/redocly-cli) 2.49.0 | the npm version, in the workflow and in `HANDOFF.md` | MIT, Redocly Inc. | Validating `docs/api/members-v1.yaml`, in CI and by hand. Chosen in [ADR 0001](./docs/decisions/0001-openapi-toolchain.md), which records how the version and licence were read |
| [Prism](https://github.com/stoplightio/prism) 5.15.10 | image digest `sha256:586d1f0f94f8d0eaf20b26b8b41f985f2a2d494bea297bd3988c3de3eb87094e`, in `compose.development.yaml` | Apache 2.0, Stoplight | Serving the contract as a mock, for the members portal and for CI. Chosen in [ADR 0002](./docs/decisions/0002-mock-server.md) |

Every other image the stack runs is named in `compose.yaml` by tag:
`postgres:18` and `caddy:2-alpine`. Neither is vendored and neither is modified.

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

Generated. Do not hand edit below this line.

<!-- BEGIN GENERATED DEPENDENCIES -->
Not yet generated. Run `python3 tools/attributions/generate.py` once the first
lockfile exists.
<!-- END GENERATED DEPENDENCIES -->
