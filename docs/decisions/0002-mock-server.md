# ADR 0002: Mock server for the members API contract

- **Status:** accepted
- **Date:** 2026-08-27
- **Deciders:** TBD. The same gap ADR 0001 records. `people-and-custody.md` has
  no names in it, and by the rule in that file this ADR is not decided until one
  is written here. It is recorded as accepted because the mock is built and
  `make mock-test` passes against it, and a tool nobody signed for is worse than
  a tool with a name against it.

## Context

Phase 1 step 2 of `order-of-operations.md` asks for a mock server generated from
`docs/api/members-v1.yaml`, and the phase does not exit until one serves it. The
reason is in `api-design.md` section 7: the members portal is built against the
mock and finished before the service exists, which is what proves the contract
is usable rather than merely legal.

ADR 0001 left this open in as many words. Redocly CLI validates the document and
does not serve it, so the mock is a separate choice.

Two constraints come from elsewhere and neither is negotiable. `architecture.md`
section 3 says a member clones this repository onto a machine they own and runs
it, so no vendor account and no web console may sit in the path. ADR 0001 says
the toolchain is pinned, because a tool that changes its behaviour on somebody
else's release schedule turns an unrelated pull request red.

## Options considered

Checked on 2026-08-27 against the npm registry, the GitHub API and the Docker
Hub tags API. Every date, licence and commit count below came from one of those.
Every claim about behaviour came from running the tool against
`docs/api/members-v1.yaml` on this machine, because what a mock does with a
document is not in its metadata.

### Option A: Prism (`@stoplight/prism-cli`, image `stoplight/prism`)

- **Last release:** 5.16.0 on npm, published 2026-07-17.
  `curl -s https://registry.npmjs.org/@stoplight/prism-cli`. The newest Docker
  Hub tag is 5.15.10, published 2026-04-20, so the image trails the package by
  one minor version.
- **Licence:** Apache-2.0, from the npm metadata and from the GitHub API for
  `stoplightio/prism`, which report the same SPDX id.
- **Maintainers:** Stoplight, inside SmartBear. Three npm publishers. On the
  repository the largest contributor is a dependency bot at 678 commits, and the
  humans behind it are `XVincentX` at 315, `karol-maciaszek` at 108, `pytlesk4`
  at 76, `chohmann` at 51 and `EdVinyard` at 49, so no single person carries it.
  5,017 stars, 146 open issues, last push 2026-08-26.
- **Fit:** it parsed the 3.1.1 document and mounted all 23 operations. It serves
  the examples written in the document, so `/me/card-eligibility` answers with
  the exact object `api-design.md` section 3.1 argued for. It enforces the
  document's security scheme, so a call with no bearer token gets the 401
  problem detail this contract declares. A `Prefer: code=409, example=selfApproval`
  header selects a named error example by name, which is how a portal gets built
  against the refusal path.
- **Cost:** three defects, all found by running it and all recorded under
  consequences below. The image is published for `linux/amd64` only, its default
  multiprocess mode exits with a TypeError before serving anything, and a
  reference that closes a cycle renders as `{"$ref": null}`.

### Option B: Mockoon CLI (`@mockoon/cli`)

- **Last release:** 9.8.0, published 2026-07-31.
  `curl -s https://registry.npmjs.org/@mockoon/cli`.
- **Licence:** MIT, from the npm metadata and from the GitHub API for
  `mockoon/mockoon`.
- **Maintainers:** one person. A single npm publisher, `255kb`, who also has 735
  commits on the repository against 28 for the next human. 8,381 stars, 44 open
  issues, last push 2026-08-26.
- **Fit:** it installs and runs natively on arm64, with no emulation and no
  engine warning, which is more than Prism manages. It honours the `/v1` prefix
  from the document's server URL, so its paths match the production ones exactly.
- **Cost:** it discards the examples. `/v1/me/card-eligibility` came back with
  one invented requirement and an empty `process` string, where the document
  states four requirements and a sentence describing the nomination process.
  Every string field came back empty, dates came back in a format the schema
  does not allow, and the invented email addresses land on real domains, which
  rule 13 bans in fixture data. It also served `/v1/me` with no token at all, so
  the refusal path cannot be built against it. The hand written examples are
  most of what the contract review produced, and a mock that throws them away
  gives the portal nothing to render.

### Option C: Microcks

- **Last release:** 1.15.0, published 2026-08-05, from the GitHub releases API.
- **Licence:** Apache-2.0, from the GitHub API for `microcks/microcks`.
- **Maintainers:** `lbroudoux` has 2,067 commits and the next human has 52. 2,027
  stars, 84 open issues, last push 2026-08-25.
- **Fit:** it is the only candidate that also runs contract tests against a real
  service, which is work phase 3 has to do anyway.
- **Cost:** its reference `install/docker-compose/docker-compose.yml` declares
  four services: `mongo:4.4.29`, `quay.io/keycloak/keycloak:26.0.0`, a Postman
  runtime image, and the application itself. Standing up MongoDB and a second
  identity provider beside the Zitadel this project already chose, in order to
  serve one document, is more to operate than the thing it serves. Not deployed
  here. It was eliminated on the compose file alone, and that is the whole
  evidence behind this entry.

### Also checked, and eliminated before comparison

`muonsoft/openapi-mock` is the obvious Go single binary candidate. Its last
release is v0.3.9 from 2023-03-11 and its last push is 2024-06-27, so it has had
no release in three years and no commit in two. `strider2038` has 310 commits
and the next contributor has 5. MIT, 528 stars, 22 open issues. One person, and
not currently worked on.

## Decision

We chose **Prism, run from the pinned Docker image**.

The constraint that eliminated the others is the examples. The value of
`members-v1.yaml` is not that it is legal OpenAPI, it is the hand written
examples and refusal sentences that a review argued over, and the portal is
being built to render those. Mockoon replaces them with generated filler and
Prism serves them verbatim. Nothing else about the comparison mattered as much:
Mockoon is better on architecture support and worse on the one job.

Refusals decided it a second time. `api-design.md` says a refusal names its rule,
and step 2 exists so the portal is finished before the service. A portal that
cannot be pointed at a 401 or at the self approval 409 is not finished. Prism
produces both, one from the document's security scheme and one from a `Prefer`
header naming the example.

The runner up is **Mockoon CLI**. If the document ever grows enough response
level examples that Prism's generation stops mattering, or if the amd64 image
becomes a real obstacle on the machine a volunteer owns, it is where to look
next. Its single maintainer is the reason it is not first even on its merits.

The image is used rather than `npx`, and that is a second decision inside the
first. Prism 5.16.0 declares `engines: {node: '>=24.18.0'}`, and the machine this
was built on runs Node 22.12.0, so `npx` printed an `EBADENGINE` warning and ran
anyway. Pinning a version whose supported runtime a volunteer may not have is
pinning the wrong half. The container carries its own Node, and `db/tests/run.sh`
already makes Docker a requirement, so the image adds nothing new to install.

## The condition that would flip this

If the newest `stoplight/prism` tag on Docker Hub is still 5.15.10 a year from
now, the image is no longer being published alongside the package, and the pin
has to move to `npx` where every volunteer's Node version becomes part of the
answer. At that point re-open this. Check it with:

```sh
curl -s 'https://hub.docker.com/v2/repositories/stoplight/prism/tags?page_size=5&ordering=last_updated'
```

## Consequences

**What gets easier.** `make mock` serves the contract on
`http://127.0.0.1:4010` with no account, no console and no configuration file.
`make mock-test` starts one, makes thirteen assertions against it over HTTP, and
removes it. The members portal can be built and finished before
`services/api/` exists, which is what phase 1 step 2 is for.

**What we now have to operate.** One pinned image and two shell scripts.
`tools/mock/image.sh` holds the version and the digest, and it is the only place
either appears.

**The defects, each found by running it.**

* The image has one manifest and its platform is `linux/amd64`. On the arm64
  machine this was built on it runs under emulation and takes about seven
  seconds to start answering. On an arm64 host with no emulation configured it
  will not run at all. `tools/mock/run.sh` names the platform explicitly so
  Docker stops warning about it on every start.
* The default `--multiprocess` mode reads `cluster.isPrimary` on a Node version
  where it is undefined, and the container exits 1 with a TypeError before
  serving anything. Both scripts pass `--multiprocess false`. Do not remove it
  without starting the container and calling it.
* `--dynamic` is unusable against this document. It answers `/me` with a 500,
  because json-schema-faker walks the `Member` reference inside `Member` until
  it fails, and where it does answer it invents lorem ipsum and properties the
  schema never declared. Static examples are the mode, and that is also the mode
  a portal wants, because the answers do not change between two reloads.
* A `$ref` that closes a reference cycle renders as `{"$ref": null}`. The rule
  is the cycle, not the self reference, and the difference matters to whoever
  adds the next schema. `Member.oriented_by` does point back at its own schema,
  but `RoleGrant.granted_by` and `RoleGrant.revoked_by` point at `Member` from a
  different schema and come out null too, because the walk from `Member` through
  `roles` to `RoleGrant` reaches `Member` again. A minimal document with no self
  reference anywhere reproduces it: `A.child` refers to `B`, `B.parent` refers
  back to `A`, and `parent` alone comes out as `{"$ref": null}` while `A.leaf`,
  a reference to an uninvolved third schema carrying the identical `readOnly`
  sibling, comes out whole. The same holds in the real document. `/me/cards`
  answers with a complete `revoked_by` member, because `Card` to `Member` closes
  nothing, and only the cycles inside that member are cut. Sweeping every
  declared GET path found 27 cut references across 8 of the 13, and `tier`,
  `standing` and `roles[].role` are populated in the same responses.
  `tools/mock/tests/check_contract.py` pins both halves of this, so a Prism that
  fixes it or a document that grows a new cycle fails there. Until then a portal
  stubs the fields where a cycle closes.
* Paths are served without the `/v1` prefix, because Prism mounts what is under
  `paths:` and ignores the path part of the server URL. A client sets its base
  URL to the mock's root and every path below it matches. There is a check
  pinning this, so a later version that starts honouring the prefix fails the
  suite rather than 404ing every call a portal makes.
* A per endpoint transformation is not represented. `/me/cards` says a tag
  number is masked to its last four characters, the masking lives in the
  endpoint description, and the schema carries one example, so the mock serves
  the unmasked number. Anyone building that screen should read the description
  and not the mock.

**Why it is not a service in `compose.yaml`.** That file is the deployment. A
fake members API answering with invented records has no business being one
`docker compose up` away from a hostname the lab publishes, and a compose
profile is one flag away from being started. There is a second, duller reason:
`.env.example` forbids a silent default, so a mock service would need a required
variable, and every existing `.env` would stop `make up` until somebody added
it. A tool the stack does not use should not be able to stop the stack.

**CI runs it.** `.github/workflows/ci.yml` has a Mock server job calling
`tools/mock/tests/run.sh`, alongside the database suite, the door conformance
suite, the Redocly lint of `members-v1.yaml`, the prose gate, and the commit
message check. That job is what stops an edit to the contract document breaking
all thirteen checks with nothing going red. It needs Docker, which the database
job already uses. The pinned image has one manifest and it is `linux/amd64`, so
it runs native on the runner and emulated on an arm64 laptop.
**Reversing this** costs an afternoon. The document is plain OpenAPI 3.1 and
every candidate above reads it unchanged, so a reversal replaces two shell
scripts and leaves `docs/api/members-v1.yaml` untouched.

## What was borrowed

Nothing. This decision selects a tool and copies no code or design from it.

## Open questions

* Whether `members-v1.yaml` should carry a response level example for the
  responses that hold a `Member`. That is `/me`, the directory, `/admin/members`,
  `/admin/approvals` and the members nested inside `/me/cards`,
  `/me/certifications` and `/me/waiver`. A written example is served verbatim, so
  it would fill the cut references and the unmasked tag number in one change and
  make the mock's answers match the prose. Resolved by whoever owns that
  document, which is not this change.
