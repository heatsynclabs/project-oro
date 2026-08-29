# ADR 0006: the import boundary gate waits for something to gate

- **Status:** accepted
- **Date:** 2026-08-28
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in it yet.

## Context

Rule 5 of `CLAUDE.md` draws the layers and names two gates for them:
`eslint-plugin-boundaries` for TypeScript and `import-linter` for Python. Phase 0
owes both. This record says what happens to that debt, because "not built yet"
and "decided not to build yet" read the same in a handoff and are not the same
thing.

Two measurements changed the answer, and both were taken on 2026-08-28.

**There is no TypeScript.** `git ls-files '*.ts' '*.tsx' '*.mts' '*.cts'` returns
nothing. The only JavaScript is three files in `apps/members`, 331 lines
together, and `grep -nE '^(import|export)|require\(' apps/members/*.js` returns
nothing at all: they are classic scripts loaded by three `<script src>` tags.

**Almost no Python is importable.** `git ls-files | grep __init__` returns five
files, all under `services/door`. Every other suite puts its own directory on
`sys.path` and imports by module name, so an import graph over this repository
today is one package wide.

## Options considered

Versions, dates and licences read from each project on 2026-08-28.

### Option A: import-linter, which rule 5 already names

- **Last release:** 2.14, 2026-08-28. 72 open issues.
- **Licence:** BSD-2-Clause.
- **Maintainers:** effectively one person with a long tail of contributors.
- **Fit:** the right shape. It reads a real import graph, so it catches an
  indirect violation, and it can express layers, independence and no cycles.
  Run against `services/door` with a layers contract it built the graph in 0.007
  seconds over 25 files and reported the contract kept.
- **Cost:** it can only see `services/door`, which is one of five trees rule 5
  draws arrows between. Its engine, grimp, has no wheel for Python 3.14 on macOS
  arm64, so installing it compiled from source and took 75 seconds.

### Option B: ruff's `flake8-tidy-imports` rules

- Same ruff already chosen in [ADR 0005](./0005-file-and-function-ceilings.md),
  so it costs nothing to install.
- **Fit:** `TID251` bans a named module, and a `.ruff.toml` in a subdirectory
  applies to the files under it, so a directional ban is expressible with a
  message of our own wording.
- **Cost:** it matches module names rather than reading a graph, so a violation
  one import deep is invisible to it. It cannot express no cycles, and it cannot
  express rule 5's "a package exports through its index". The policy ends up
  scattered across one config file per directory rather than written down once.

### Option C: eslint-plugin-boundaries, which rule 5 also names

- **Last release:** 7.2.0, 2026-08-09. 14 open issues.
- **Licence:** MIT.
- **Maintainers:** one person. The npm maintainer list has exactly one name.
- **Fit:** it works. In a scratch tree it allowed an app to import a package and
  refused an app importing a service, with the message the config asked for.
- **Cost:** installing it writes a `package-lock.json` of 100 packages and 22MB
  of `node_modules` into a repository that has neither, and it would then have
  nothing to check. It reasons about import and require statements, and there
  are none.

## Decision

**Neither gate lands today. `import-linter` stays the choice for Python and
`eslint-plugin-boundaries` stays the choice for JavaScript, and each lands with
the first code that gives it something to refuse.**

For JavaScript that is the first module with an `import` in it, which arrives
with the admin portal in phase 4 or with `gantry-vue`, whichever comes first.
Landing it now would add a lockfile and a hundred packages to review and patch
in exchange for a gate that cannot fail, and rule 10 forbids documenting a gate
for code that does not exist.

For Python that is `services/api`, in phase 3, which is the first thing that will
sit under a layer arrow with something above it. Pin grimp explicitly when it
lands, because its install is the part that will bite somebody.

Ruff's `TID` rules were the tempting middle. They are rejected because a boundary
check that misses an indirect import is a gate that reports green on a violated
rule, and `docs/plan/architecture.md` section 2 already rejected PostgREST for
exactly that: "A gate that reports green on a violated rule is worse than no
gate."

## The condition that would flip this

The first `import` statement in any file under `apps/` or `packages/`, or the
first commit under `services/api/`. Either one makes the corresponding gate
land in the same pull request.

## Consequences

- Rule 5 stays enforced by review for now, which `CLAUDE.md` already allows in
  the section above rule 1, and which this record makes visible rather than
  silent.
- `HANDOFF.md` section 2 carries the row, and it now says decided rather than
  not started.
- The layer that most needs the gate, `services/api` calling downward and
  nothing calling up into it, gets it on the day it is first written, which is
  the cheapest moment to find out the arrows are wrong.
- Reversing this is one config file and one job, in either language.

## What was borrowed

Nothing yet. Both tools are named and neither is installed.

## Open questions

Whether `services/door` should get an `import-linter` contract of its own before
`services/api` exists. It is the one tree the tool can already see, and its
`domain` over `adapters` layering is the rule most worth holding. The argument
against is that a gate installed for one package teaches nobody the shape of the
whole, and phase 3 is not far. Decide it when `services/api` starts.
