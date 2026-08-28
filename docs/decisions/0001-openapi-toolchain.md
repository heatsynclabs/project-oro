# ADR 0001: OpenAPI validator for the members API contract

- **Status:** accepted
- **Date:** 2026-08-27
- **Deciders:** TBD. `docs/plan/people-and-custody.md` has no names filled in yet,
  and by the rule in that file this ADR is not decided until one is written here.
  It is recorded as accepted because the tool is already in use on
  `docs/api/members-v1.yaml`, and a tool nobody signed for is worse than a tool
  with a name against it.

## Context

Phase 1 step 1 writes the OpenAPI document for the members API before any client
or service exists. Rule 3 says nothing is done until it has been run, and a
contract document is only run by validating it. Rule 12 makes this document the
thing everything downstream is built against, so a shape error in it is the most
expensive kind of error this project can make.

The document is OpenAPI 3.1.1. That narrows the field more than it looks: several
well known tools still parse only 3.0, and one of them fails silently rather than
saying so.

## Options considered

Checked on 2026-08-27, against the npm registry, PyPI, and the GitHub API. Every
number below came from one of those, not from memory.

### Option A: Redocly CLI (`@redocly/cli`)

- **Last release:** 2.49.0, published 2026-08-27. `npm view @redocly/cli time`.
- **Licence:** MIT. `npm view @redocly/cli license`, and the GitHub API reports
  the same SPDX id for `Redocly/redocly-cli`.
- **Maintainers:** Redocly Inc., a company. Five npm publishers. Top four commit
  authors on the repository are `tatomyr` (381), `RomanHotsiy` (380), a release
  bot (232), and `DmitryAnansky` (162), so no single person carries it.
  1,506 stars, 158 open issues, last push 2026-08-27.
- **Fit:** validates OpenAPI 3.1 directly, one command, no ruleset file needed to
  get a useful answer. `lint` and `bundle` come from the same binary, which
  matters in phase 3 when CI has to compare the committed document against the
  one generated from the running service. The abandoned tool below names it as
  its own replacement, so the field has already settled on it.
- **Cost:** the default ruleset is opinionated and warns on things this project
  decided against, so the warnings have to be read rather than counted.

### Option B: Spectral (`@stoplight/spectral-cli`)

- **Last release:** 6.16.3, published 2026-08-03. `npm view @stoplight/spectral-cli time`.
- **Licence:** Apache-2.0, from the npm metadata and the GitHub API.
- **Maintainers:** Stoplight, now inside SmartBear. Four npm publishers, two of
  them SmartBear addresses. The repository's top three commit authors are
  dependency bots, and the highest human is `P0lip` with 100 commits, which reads
  as a project in maintenance rather than active development. 3,189 stars, 271
  open issues, last push 2026-08-27.
- **Fit:** the strongest style rule engine of the three, and the rules are
  writable in YAML, so the house conventions in this contract could be enforced
  later. Supports 3.1.
- **Cost:** it does nothing useful without a ruleset file, so adopting it means
  adopting a second configuration file and a second thing to keep current. It
  also only lints. Phase 3 needs bundling and a diff, so Spectral would be one
  tool of two rather than one tool.

### Option C: `openapi-spec-validator` (PyPI)

- **Last release:** 0.9.0, published 2026-05-20. PyPI JSON API.
- **Licence:** Apache-2.0, from the GitHub API for `python-openapi/openapi-spec-validator`.
  The PyPI metadata carries no licence field, which is worth knowing before
  anything depends on it.
- **Maintainers:** effectively one person. `p1c2u` has 519 commits, the next
  human contributor has 22, and after the dependency bot the tail is small.
  407 stars, 51 open issues, last push 2026-08-17.
- **Fit:** Python, which is the language the API service will be written in, so
  it could run in the same virtual environment as the service and its tests with
  no Node in CI. Validates 3.1 correctly.
- **Cost:** schema validation only. It answers "is this a legal document" and
  nothing about whether the document is any good, so a missing operation
  description or an operation with no failure response passes silently. Single
  maintainer is a real risk for something a build depends on.

### Also checked, and eliminated before comparison

`@apidevtools/swagger-cli` was the obvious fourth candidate. Its last release is
4.0.4, published 2020-07-19, and `npm view @apidevtools/swagger-cli deprecated`
returns "This package has been abandoned. Please switch to using the actively
maintained @redocly/cli". Six years without a release, and it predates OpenAPI
3.1 entirely.

`@quobix/vacuum` (0.30.1, 2026-08-26, MIT) is fast and actively developed, but
`daveshanley` has 1,454 commits against 27 for the next human, so it is one
person's project. Rule 8 asks whether a dependency is maintained by more than one
person, and the honest answer here is no.

## Decision

We chose **Redocly CLI**.

The constraint that eliminated the others is phase 3. CI has to compare the
document generated from the running service against the committed one, which
needs bundling and diffing as well as validation, and Redocly is the only
candidate that does all three from one binary. Adding a second tool for the other
half would repeat the mistake rule 5 already names about linters: two tools that
disagree about one document end with both switched off.

The runner up is **Spectral**. Its rule engine is better, and if this project
ever wants the house conventions in this contract checked automatically rather
than by review, that is where it would go.

`openapi-spec-validator` was the tempting answer, because a Python tool in a
Python service's virtual environment is one less runtime in CI. It was rejected
because it validates the schema and nothing else. It reported this document OK
while Spectral found an operation with no description, and that is exactly the
class of defect a contract review is supposed to catch before a portal is built
against it.

## The condition that would flip this

If Redocly CLI stops being installable without a Redocly account, or its lint
command starts requiring one, this choice is wrong and Spectral plus a separate
bundler becomes correct. Somebody can check that in a year by running
`npx @redocly/cli lint` on a clean machine with no environment variables set.

## Consequences

- Node is now required in CI for the contract check, on top of Python for the
  service and Docker for the database tests. That is a third runtime.
- `npx @redocly/cli lint docs/api/members-v1.yaml` is the check. It is pinned to
  a version in CI rather than floating, because a linter that changes its rules
  on its own schedule turns an unrelated pull request red.
- Three warnings are expected and are not defects. `info-license` fires because
  the repository licence is undecided, which README.md already records as an open
  question. `operation-4xx-response` fires twice on the public status endpoints,
  which take no parameters and no token and have no meaningful client error.
  When a Redocly configuration file is added, turn those two rules off there with
  this reasoning beside them rather than editing the document to satisfy them.
- Reversing this costs an afternoon: the document is plain OpenAPI 3.1 and every
  candidate above reads it unchanged.

## What was borrowed

Nothing. This decision selects a tool and copies no code or design from it.

## Open questions

- Whether the mock server in phase 1 step 2 comes from the same toolchain.
  Redocly CLI does not serve a mock, so that is a separate choice and a separate
  ADR. Resolved by whoever builds step 2.
- Whether the house conventions in this contract are worth a Spectral ruleset
  later. Resolved by counting how many review comments on the next two contract
  changes are about a convention a rule could have caught.
