<!-- voice-check: reference -->

# Project ORO working rules

These rules bind any agent or person writing code in this repository. They exist
because this project replaces the system that unlocks a real building for a real
501(c)(3), and because two previous rewrites stalled. The rules are written to be
checkable. Most of them have a gate in CI, named at the end of each section.

Read `docs/conventions/` for the long form of anything here. This file is the
short form, and it is the part that must hold.

## What is actually built today

Rule 10 forbids documentation for code that does not exist, and this file names
gates that do not all exist yet. The current state is tracked in one place,
`HANDOFF.md` section 2, so there is one table to update rather than two that
disagree.

A rule whose gate is not built yet is still the rule. It is enforced by review
until the gate exists.

---

## 1. Attribution

**Never name an LLM as an author, co-author, contributor, or reviewer.**

This applies to commit messages, commit trailers, pull request bodies, issue
text, changelog entries, code comments, documentation, `AUTHORS`, and package
metadata.

Specifically banned strings anywhere in a commit message or PR body:

```
Co-Authored-By: Claude
Co-authored-by: Claude
Generated with Claude Code
Claude-Session:
🤖 Generated with
Assisted-By:
AI-Generated:
```

The human who ran the session is the author. They read the diff, they understand
it, and they answer for it in two years when the door stops opening. A model
cannot hold any of that. Recording it as an author is false provenance, and false
provenance in a version control history is worse than no provenance.

This is not a rule about hiding how the work was done. Say in a pull request
description that a tool helped, in prose, if it is useful context. Do not put it
in the authorship metadata.

*Gate:* `.githooks/commit-msg` rejects the banned strings locally, and
`.github/workflows/ci.yml` runs the same check over every commit in a pull
request so the hook cannot be bypassed by a push from another machine.

---

## 2. Never assume

Every factual claim you make about this codebase, its dependencies, or the
systems it talks to must trace to something you checked in this session.

- If you have not read the file, do not describe what is in it.
- Read version numbers, environment variable names, config keys, API paths, and
  column names from the source. Never from memory.
- "Should work", "presumably", "typically", and "standard practice is" are not
  evidence. Delete them or replace them with the thing you actually checked.
- When a fact is missing and you cannot check it, stop. Either ask, or write the
  gap down explicitly:

  ```
  ASSUMPTION: the production Postgres is 9.6, not 9.x generally.
  CONFIRM BY: psql -c 'select version()' on hsl-web.
  BLAST RADIUS: the migration script's use of generated columns.
  ```

  An assumption with a stated confirmation step is honest work. An unstated
  assumption is a defect with a delay fuse.

The current production database has no foreign key constraints anywhere, so
integer columns named `*_id` may point at rows that do not exist. Treat every
join against migrated data as capable of returning nothing.

*Gate:* review. This one is cultural, and it is the most important rule in the
file. There is no gate that can check it, and pretending otherwise would itself
break the rule.

---

## 3. Check the work

Nothing is done until it has been run.

- Write the test first (see rule 4), watch it fail, then make it pass.
- Run the thing. A change to an API is not verified by reading the diff; it is
  verified by calling the endpoint.
- When you claim a test passes, paste the output. When a test fails, say so and
  show it. Never report green from inference.
- Before saying a task is complete, re-read the original request and list what
  you did not do. Partial work reported as complete is the failure mode that
  makes people distrust generated code.
- Migrations get run against a real database before merge. `db/tests/run.sh`
  rebuilds the schema from nothing every time, so a migration that only works
  against an already migrated database fails.
- Anything touching the door gets exercised against the fake controller before it
  goes near hardware.

*Gate:* CI runs the full suite. A pull request that says "tested locally" with no
test in the diff gets closed.

---

## 4. Test driven, and the tests have to mean something

Write the failing test first. This is not negotiable for business logic,
authorization rules, the door protocol, or anything touching money or access.

What a meaningful test looks like here:

- It asserts on behaviour a person cares about, not on the shape of an internal
  call. "A member cannot read another member's phone number" is a test. "The
  repository method was called once" is not.
- Authorization gets a test per rule, per role, including the anonymous case and
  including the case that must be refused. A policy without a refusal test is
  untested.
- The two admin approval rule gets a test proving the proposer cannot approve
  their own proposal, at the database level, because that is where the rule
  lives.
- The door reconcile loop gets a test proving it is idempotent: running it twice
  against the same state produces the same result and no writes the second time.
- Anything with a slot number gets a test proving `controller_slot` values are
  preserved on migration, because a slot is an EEPROM address on the controller
  and renumbering silently maps every member to the wrong door permission.

Coverage percentage is not a goal and is not reported as an achievement. A suite
that covers every line and asserts nothing is worse than no suite, because it
buys false confidence.

Coverage is collected and published. It is never gated. A threshold turns
coverage into the goal, and within a month somebody writes a test that executes a
module and asserts nothing in order to get past it.

Test the boundary, not the mock. Prefer a real Postgres in a container over a
stubbed query builder. Prefer a fake HTTP controller that speaks the real wire
protocol over a mocked client object.

*Gate:* CI. Plus a required test file alongside every new module.

---

## 5. Separation of concerns

Layers, and the only direction dependencies may point:

```
apps/*          the three portals and any future app
  |             may import: packages/*
  v
packages/*      ui, theme, api client, shared types
  |             may import: other packages/*
  v
services/*      door service, and any handwritten API service
  |             may import: nothing above it
  v
db/             schema, migrations, policies, seed data
```

Rules that follow from that:

- An app never talks to Postgres. It talks to the API.
- The API layer never speaks the door wire protocol. It calls the door service.
- The door service is the only thing that holds the controller password, and it
  is the only thing that opens a socket to the controller.
- Business rules live in exactly one place each. If the "approver must differ
  from proposer" rule is checked in the UI and in SQL, the UI check is a
  courtesy for the user and is labelled as such in a comment; the SQL check is
  the rule. Never let two places both believe they are authoritative.
- A package exports through its index. Reaching into another package's internal
  path is an import boundary violation, not a shortcut.
- Presentation does not fetch. Fetching does not render.

*Gate:* `eslint-plugin-boundaries` for TypeScript and `import-linter` for Python
enforce the direction of the arrows. A violation fails CI, it does not warn.

One tool per language, not two. `dependency-cruiser` was considered and dropped:
it overlaps almost entirely with the ESLint plugin, and two tools disagreeing
about one import is the fastest route to both being switched off.

---

## 6. No monolithic files

Hard ceilings, enforced:

| Thing | Ceiling | Notes |
|---|---|---|
| Source file | 300 lines | Excludes generated files and lockfiles |
| Function or method | 50 lines | If it needs more, it is two functions |
| Cyclomatic complexity | 10 | Per function |
| Function parameters | 4 | Past that, take an object |
| Nesting depth | 4 | Extract or invert the condition |

The ceilings are not the target. A 290 line file is usually still too long; it
just has not been caught yet. The number exists so the argument is over before it
starts.

Generated files, migrations, and vendored code are exempt and must be listed
explicitly in the lint config with a reason, not covered by a blanket glob.

A file that must exceed the ceiling gets an inline disable with a one line
justification naming the reason. "It is all related" is not a reason.

*Gate:* ESLint `max-lines`, `max-lines-per-function`, `complexity`, `max-params`,
`max-depth`. Ruff equivalents for the Python service.

---

## 7. Readable by a volunteer at 2am

The maintainers are the constraint on this project, not the machines. Every
choice gets judged against one question: can a member who has not seen this code
before fix it during an outage, at night, without asking anyone.

- Name things after what they are in the lab, not after patterns. `CardSlot`,
  not `EntityIdentifierValueObject`. The domain language is in
  `docs/glossary.md` and code should use it exactly.
- Prefer boring and obvious over clever and short. A loop that reads clearly
  beats a chain of four higher order functions.
- No abbreviations except the ones in the glossary. `certification`, not `cert`,
  unless the glossary says `cert`.
- Comments explain why, never what. If a comment restates the code, delete the
  comment. If the code needs a comment to say what it does, rewrite the code.
- Every non obvious constant gets a comment naming its source. `200` in the door
  service gets `# EEPROM user slot ceiling, Open_Access_Control firmware`.
- Errors say what happened, what the system did about it, and what the reader
  should do next. Never just the exception text.
- No abstraction earns its place until there are three real uses. Two is a
  coincidence.

*Gate:* review, plus the ceilings in rule 6, plus `docs/glossary.md` for naming.

---

## 8. Research before choosing

Do not pick a library, a pattern, or an architecture from memory.

Before any dependency or architectural decision:

1. Name at least three real alternatives.
2. Check each one's current state: last release, open issue count, license, and
   whether it is maintained by more than one person.
3. Write the comparison down in `docs/decisions/` as an ADR, using the template
   there. State the decision, the runner up, and the one condition that would
   flip it.
4. Prefer a well maintained existing project over anything written here. The
   bespoke code in this system should be the door service and nothing else.

An ADR is short. Half a page. Its value is that in three years someone can see
that the choice was considered rather than defaulted into.

Reversing a decision is fine and expected. Reversing it without writing down what
changed is not.

*Gate:* a bot comments on any pull request that adds a production dependency,
listing what is new and asking which ADR covers it.

Deliberately a comment and not a failing check. A hard gate here always degrades:
a transitive bump, a `pnpm up`, and a dev dependency added to fix a build all
trip it, so within a month people learn a magic phrase that makes it pass and the
gate stops meaning anything. A human reads a comment. A red X gets routed around.

---

## 9. Cite what you borrowed

If a design, an algorithm, a schema, or more than a few lines of code came from
an open source project, say so where the code lives, and comply with its license.

- A borrowed file or function carries a header comment: the project, the URL, the
  license, and the commit or version it came from.
- Architectural inspiration goes in the ADR that chose it. "This is the shape
  Supabase uses internally" is a citation and should name what was taken and what
  was left.
- `ATTRIBUTIONS.md` at the repo root lists every dependency, its license, and
  every borrowed pattern with a link. It is generated for dependencies and hand
  maintained for patterns.
- Copyleft licenses get checked before the dependency lands, not after.
- Never copy code without its license header. Never relicense someone's work by
  omission.

The existing HeatSync work counts. The Rails app, the Arduino firmware, the
stalled rewrites, and the GANTRY design system all have authors, and where this
project takes their schema, protocol, or tokens, it says so.

*Gate:* a license checker in CI over the dependency tree, and a review check that
new vendored code carries a header.

---

## 10. Documentation that stays true

Documentation lives next to the thing it documents and is part of the same
change.

- Every package and service has a `README.md` answering: what it is, how to run
  it, how to test it, and what it depends on. Four questions, in that order.
- Every API endpoint is described in the OpenAPI document, and the document is
  generated or verified against the running service so it cannot drift.
- Every database table and column carries a SQL `COMMENT ON`, so the schema
  documents itself and the documentation cannot be lost.
- Runbooks for anything a volunteer might have to do at 2am live in
  `docs/runbooks/`, written as numbered steps with expected output at each step.
  The directory is created with the first runbook, not before it.
- A change that alters behaviour and does not touch documentation is incomplete.
- Never write documentation for code that does not exist yet. Aspirational
  documentation is the most expensive kind of lie in a codebase.

Do not document the obvious. A README that explains what `npm install` does is
noise that trains people to skip READMEs.

*Gate:* CI fails when the OpenAPI document does not match the running service,
and when a table exists without a comment.

---

## 11. Copy that does not read as machine written

The lab has a voice, documented in `docs/conventions/voice.md`, taken from the
HeatSync brand guide. It applies to UI strings, error messages, documentation,
commit messages, and code comments. All of it, not just the marketing surfaces.

### Hard bans

**No em dashes or en dashes.** Anywhere. Prose, alt text, code comments, commit
messages, generated output, SVG titles.

And do not route around it. Replacing an em dash with `--` or ` - ` in running
prose is the same tell wearing a hat, and it is worse because it looks like
someone knew the rule and dodged it. Restructure the sentence. Use a comma, a
colon, or a full stop. If a clause needs to be set off and none of those work,
the sentence wants to be two sentences.

**No emoji.** Never in UI, never in documentation, never in commit messages, and
above all never as an icon. An emoji standing in for an icon renders differently
on every platform, carries no accessible name, cannot be styled, and cannot
inherit a token colour. Use an inline SVG from the icon set. This is a
correctness rule, not a taste rule.

### The tells to avoid

These are the measurable signatures of generated prose. They are banned because
they are bad writing, and the fact that they also identify the writer as a
machine is the secondary problem.

- "It is not just X, it is Y." Pick one and say it.
- The rule of three. Three parallel items, over and over, in every paragraph.
  One triad per document, at most.
- Uniform sentence length. Vary it. A short sentence. Then a longer one that
  actually carries a clause worth reading.
- Summary closings that restate what was just said. Stop when you are done.
- Rhetorical question openers. "Ever wondered how the door works?"
- Hedging stacks. "This might potentially be able to help somewhat."
- Bold or italics mid sentence for emphasis. Rewrite the sentence instead.
- "In today's fast paced world", "in a world where", and every relative.
- Section headers that are a noun phrase plus a colon plus a restatement.

### Banned vocabulary

unleash, unlock, elevate, empower, revolutionise, transform your, game changer,
cutting edge, state of the art, seamless, robust (of a community), leverage as a
verb, synergy, ecosystem, innovate, innovation, disrupt, world class, best in
class, passionate about, dive in, delve, journey (of a person learning
something), thrilled to announce, excited to share, we are proud to, whether you
are a beginner or a pro, endless possibilities, one stop shop, thriving
community.

Two more, specific to this lab: **community** used as a decorative adjective, and
**innovation**. HeatSync members build things. They do not innovate.

### Also banned, for this project specifically

- Militarised framing. No battle tested, war room, arsenal, tactical, mission
  critical as filler, or target used of a person. This is a community workshop.
- Exclusion by implication. Never phrase experience, tools, income, or identity
  as a prerequisite. "Even if you have never soldered" is fine. "For serious
  makers" is not.
- Softened safety copy. If certification is required, write required. Never
  "we recommend" when the rule is "you may not".
- Numbers nobody checked. 3,200 square feet and 2009 are the two safe constants.
  Everything else gets verified before it ships.

*Gate:* `tools/voice-check` runs over markdown, UI copy, code comments, and
commit messages in CI.

Two escape hatches, and they are different sizes. A file whose job is to document
the bans, like this one, carries `voice-check: reference` in its first 40 lines.
That turns off the voice checks and the attribution check, so the banned trailers
can be quoted in order to be banned. The accessibility checks stay on. A passage quoting somebody else's
words, which research and archive notes are full of, is wrapped in
`<!-- voice-check: quote -->` and `<!-- /voice-check: quote -->`, which suspends
the voice rules for that block and nothing else. Prefer the block: the file level
pragma also turns off the attribution check for the whole file, which is almost
never what you want.

The rhythm checks are warnings and stay warnings. Sentence length variance on a
short README is noise, and a gate that fails a build over prose rhythm gets
disabled within a week.

---

## 12. Order of operations

The API contract is designed and agreed before any app is built against it. Not
sketched, agreed: written as an OpenAPI document with example requests and
responses, reviewed, and merged. Everything downstream of it is cheap to change.
It is not.

The build order and its exit criteria live in `docs/plan/order-of-operations.md`.
Do not start a phase whose predecessor's exit criterion is unmet, and do not
declare an exit criterion met without the evidence named beside it.

Two gates come before everything:

1. A verified, restorable backup of the production members database exists, and
   the restore has been proven onto a staging copy.
2. The door keeps working. Every phase is designed so that physical cards open
   the door even when everything else in this repository is down.

---

## 13. Data, access, and the things that are not ours

This system holds member names, addresses, phone numbers, emergency contacts,
payment records, signed waivers, and a log of who entered a building and when.
Treat all of it as belonging to the member, not to the project.

- Never commit a secret, a dump, a real email address, or a real card number.
  Seed and fixture data is invented, and it is obviously invented.
- Never copy production data onto a laptop. Work against seeded local data or an
  anonymised staging copy.
- Door logs are access records for a physical building. They are readable by the
  member they concern and by admins, and by nobody else, and that is enforced in
  the database rather than in a page.
- Privileged actions are logged with who did them and when, and the log is
  append only.
- The door controller password, the database password, and the identity service
  master key are the three secrets that matter most. Each has exactly one holder
  process. Write down which, in the ADR that introduces it.

*Gate:* secret scanning in CI, and a pre-commit hook. Plus a fixtures lint that
fails on anything resembling a real email domain in seed data.

---

## 14. When you are stuck or wrong

- If the request is ambiguous in a way that changes the work, ask. One question,
  early, beats a day of the wrong thing.
- If you find a real problem with the task as specified, say it in a sentence or
  two, then keep building under a stated assumption.
- If you get something wrong, fix it and move on. Do not narrate the error at
  length, do not apologise repeatedly, and do not add a defensive comment to the
  code explaining the previous mistake.
- If a previous decision now looks wrong, open an ADR that supersedes it. Do not
  quietly do it differently in one corner of the codebase.
- Report what you did not finish. Every time.

