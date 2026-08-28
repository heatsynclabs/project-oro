# ADR 0005: how the file and function ceilings are enforced

- **Status:** accepted
- **Date:** 2026-08-28
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in it yet, and this record is not complete until a build lead signs it.

## Context

Rule 6 of `CLAUDE.md` sets five ceilings: a source file at 300 lines, a function
at 50, cyclomatic complexity at 10, four parameters, and four levels of nesting.
It names ESLint and Ruff as the gates. `HANDOFF.md` has carried the row saying
the gate is not built since phase 0, and `CLAUDE.md` says above rule 1 that a
rule whose gate is not built yet is still the rule, enforced by review until the
gate exists. Review has already missed some.

The decision is which tool measures which ceiling, because the obvious answer,
one linter, turns out not to exist.

## Options considered

Every version, date and licence below was read on 2026-08-28 from the project's
own release metadata or its `LICENSE` file, and every finding count comes from
running the tool over the 43 Python files this repository held at the commit
that introduced the gate. That number moves with every session, so it is written
here as what was measured rather than as what is true today.

### Option A: ruff

- **Last release:** 0.16.5, 2026-08-27. 2,154 open issues.
- **Licence:** MIT, read from `astral-sh/ruff/LICENSE`.
- **Maintainers:** Astral, a company. Five contributors over 600 commits each.
- **Fit:** enforces complexity (`C901`), parameters (`PLR0913`) and nesting
  depth (`PLR1702`). Ran in 0.01 seconds and found three violations. No
  transitive dependencies, and it publishes a multi architecture container.
- **Cost:** it has no rule for module length and none for function length.
  `PLR0915` counts statements, not lines, and reports 23 for the 53 line
  function in this repository, so a threshold anywhere near 50 never fires.

### Option B: pylint

- **Last release:** 4.0.7, 2026-08-09. 1,082 open issues.
- **Licence:** GPL-2.0-or-later, read from `pylint-dev/pylint/LICENSE`. The only
  copyleft candidate, checked before landing per rule 9. Run as a separate
  process it would not affect this repository's own licensing.
- **Maintainers:** five contributors over 300 commits each.
- **Fit:** four of the five, including the 300 line file ceiling, which ruff
  cannot do. Found the same three violations with the same numbers.
- **Cost:** 2.04 seconds against ruff's 0.01, seven transitive dependencies, and
  it still misses the 50 line function ceiling.

### Option C: flake8 with flake8-functions and mccabe

- **Last release:** flake8 7.3.0, 2025-06-20. flake8-functions 0.1.0,
  2026-08-14, whose previous release was 2023-04-10.
- **Licence:** MIT for all three.
- **Maintainers:** flake8 has several. flake8-functions had one committer in the
  last twelve months, and it is the only part of this combination that supplies
  the ceiling nothing else does.
- **Fit:** `CFQ001` is the only rule on any candidate that measures a function in
  lines.
- **Cost:** it measures logical lines. It reports 46 for the function this
  repository counts as 53, so setting it to 50 does not enforce rule 6 as
  written, and at 50 it reports nothing here at all. Four moving parts, one of
  them barely maintained, for a ceiling it does not actually hold.

### Option D: radon

- Rejected without a full comparison. It exits 0 whatever it prints, so gating on
  it needs xenon on top, and its complexity numbers disagree with the other
  three: it rates the same function 16 where ruff, pylint and mccabe all rate it
  11. A gate whose number nobody else reproduces is an argument waiting to
  happen. Rule 4 already allows collecting a metric without gating it, so radon
  is the right tool if somebody wants complexity published.

## Decision

**Ruff for the three ceilings it measures, and `tools/ceilings/check_ceilings.py`,
125 lines of it, for the two that no candidate measures.**

Ruff is chosen over pylint on speed, licence and dependency count, and none of
those is the reason it wins. It wins because whatever is chosen, something still
has to count lines, and once that exists the second linter buys one ceiling for
two hundred times the runtime and a copyleft licence.

Writing the line counters rather than buying them is a departure from rule 8's
preference, and it is the narrow case rule 8 leaves room for: three real
alternatives were priced and none of them does it. Both counts are the naive
ones, `wc -l` and `end_lineno` minus `lineno`, because those are the counts a
person makes when they open the file and read the line numbers, and a ceiling
somebody cannot check by eye is a ceiling they will argue with.

The line counter also reaches what a Python linter never will. The 300 line
ceiling in rule 6 is written about a source file, not about a Python file, and
the two files over it today are an OpenAPI document and a stylesheet.

Ruff runs as a pinned container rather than a pip install. Every other tool this
repository runs arrives that way, `make check` already needs Docker for the
database suite, and it means neither CI nor a volunteer's laptop grows a Python
environment.

## The condition that would flip this

If ruff gains a module length rule and a physical function length rule, delete
`tools/ceilings/check_ceilings.py` and move both numbers into `ruff.toml`. That
is a single commit and it should be taken the week it becomes possible.

## Consequences

- Rule 6 is a gate rather than a convention, for the first time. The first run
  found four violations. `HANDOFF.md` had named two of them and had the ceiling
  right on both. The two it had not named were a complexity of 11 and a nesting
  depth of 5, and neither is visible by eye, which is the argument for a gate in
  one sentence.
- `PLR1702` is a preview rule, so `ruff.toml` sets `preview = true` and the
  nesting ceiling depends on a rule Astral has not stabilised. If it is
  withdrawn, that ceiling goes back to review and the file has to say so.
- The exemption list is a file with a reason on every line, and a path that is
  no longer over the ceiling fails the check, so an exemption cannot outlive the
  thing it was written for.
- Two files are exempt today: the API contract and the token layer. Both reasons
  are in `tools/ceilings/exemptions.txt`.
- Reversing this costs one job and two files.

## What was borrowed

Ruff, MIT, run unmodified as a published container image. Nothing is vendored
and no code is copied. The digest is pinned in `tools/ceilings/run.sh` and
recorded in `ATTRIBUTIONS.md`.

## Open questions

None for Python. The same five ceilings over JavaScript are
[ADR 0006](./0006-import-boundaries.md), which also carries rule 5.
