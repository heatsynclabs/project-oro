<!-- voice-check: reference -->

# Kickoff, for a session that carries several phases

`kickoff.md` is for picking up one step carefully. This one is for a session with
multi agent orchestration turned on, meant to carry the remaining build a long
way in one sitting. Paste everything below the line.

---

You are implementing Project ORO, the members and door access system for HeatSync
Labs. Nothing is deployed and nothing in production has been touched. The work
is on `main` and both CI workflows are green on it.

## Prove it is green before you change it

```sh
git config core.hooksPath .githooks
make check
```

That runs twenty two suites: the database, the door port, the theme, the prose
gate, the contract citations, the ceilings, the undefined names, the import
boundaries, the attributions and their lockfile coverage, the contract mock,
both stack shapes, the members portal, the identity service, the legacy import,
the first three admins, the restore drill, the members API, and the members API
against a real token. If any of it is red, stop and say so. Do not build on top
of a red suite.

Two checks are outside it, on purpose, and both are worth running once.
`npx @redocly/cli@2.49.0 lint docs/api/members-v1.yaml` needs Node.
`make browser-checks` drives a stack somebody else started, so bring one up
with `make development` first. That one was red for a day against a portal that
was working correctly, because it was in no CI workflow. It has one now, running
`tools/browser-checks/with_its_own_stack.sh`, which brings up its own.

## Read these first, in this order

1. `CLAUDE.md`. The working rules. Most of them have a gate.
2. `HANDOFF.md`. Section 2 is what exists, section 6 is what is left, and
   section 7 is a list of traps that already caught somebody. Read section 7
   twice.
3. `docs/plan/order-of-operations.md`. The build order and the exit criterion
   for each phase.
4. `docs/plan/architecture.md` and `docs/plan/api-design.md`.
5. `docs/api/members-v1.yaml`. The contract. Everything downstream is built
   against it, and it is the authority for field names and shapes.

## What you are carrying

`HANDOFF.md` section 6 has the table. It splits each remaining phase into what a
session can build and what waits on a person, and that split is the single most
important thing in this prompt. Phases 2, 3 and 5 cannot exit without the person
column. Build the left column. Never record a phase as exited when only the left
column is done, and never invent evidence for an exit criterion you cannot meet.

The order is identity, member management, admin, door. It is the order in the
plan and there is a reason for each position.

## The rules that already caught somebody here

Each of these cost real time in this repository. They are not general advice.

**Borrow before you build.** Rule 8 says the bespoke code here should be the
door service and nothing else. Measured on 2026-08-31: the door service is
1,231 lines and the Python and shell under `tools/` is 13,564. That gap is a
defect, not an achievement, and it grows every time somebody reaches for a new
harness. Before you write a parser, a checker, or a harness, price an existing
one and write the ADR that rule 8 asks for.

The counterweight, and it is real: `tools/names/` was added on 2026-08-31 and
paid for itself on its first run. The test is whether an existing tool already
does it. That one is nine lines of shell around a ruff rule, which is
borrowing. A hand written import graph would not have been.

**Never derive one setting from another to save a line.** Caddy once picked its
route file out of `COMPOSE_PROFILES` so that one variable did two jobs. It left
two ways to start the stack that disagreed, and the wrong one served a 404 in
front of a healthy mock. The file documented the trap instead of removing it.

**Two copies and a drift checker is worse than one file.** The token layer
shipped twice, byte identical, with a test to catch them diverging. One bind
replaced both.

**Assert the behaviour, not the mechanism.** Two tests here required a literal
variable in a Makefile recipe and a path prefix on a bind. Both broke the moment
the mechanism changed while the behaviour was fine. Ask what a person would
notice, and assert that.

**Write the failing test first, and watch it fail.** Doing that on the bootstrap
rule found a fixture that seeded two admins, which had quietly made four refusal
assertions pass because the grant succeeded rather than because anything refused
it. A test that has only ever been green proves nothing.

**Measure counts, never remember them.** An audit of the documentation against
the code found ten false claims, including two files contradicting themselves.
Every number you write down should come from a command you just ran.

**Update `HANDOFF.md` section 2 in the same change.** It is the single place the
state is tracked, and it goes stale every single time something lands. An audit
on 2026-08-31 found eleven wrong rows and four missing ones in a file that had
been current a week earlier.

**A gate that only ever ran green proves nothing, and neither does one that
asserts a default.** Two registration checks here passed against an instance the
configuration step had never touched, because the value they assert is what a
fresh Zitadel ships with. Deleting the step turned none of them red. They drive
the instance to the other state first now. Before trusting a check, ask what
state it would have to be in for the check to fail, and put it in that state.

**And a checker that fixes what it checks always passes.** Two tools here have a
write mode and a report mode one flag apart, and the report mode is what the
suite runs. `db/tests/run.sh --update` is where that lesson came from: capturing
output with it once laundered five failing assertions into expected files, and
every run afterwards said all database tests passed.

## How to run this as an orchestrated session

The pattern that earned its keep here is draft, then an adversarial reviewer told
to refute rather than admire, then a fix agent given only the confirmed findings.
Run it per unit of work, in a pipeline, so one unit verifies while another
drafts.

That pattern found, in this repository: a door adapter that threw away the
controller's answer and reported a refused unlock as done; a working database
password committed in `.env.example`; a contract that documented a unique
constraint on one endpoint and not the two others that hit it. None of those
would have been found by reading the diff.

Give every agent the traps in `HANDOFF.md` section 7 and the paths it must not
touch. Tell reviewers to find the files with `git status` rather than trusting
the report, because a report that omits a file is the failure worth catching.

Scale to the work. A schema change wants one careful agent, not five.

## What will make this session fail

- **Building ahead of the order.** Two documents in this repository already
  disagree about when the members portal is built. When you find a conflict like
  that, say so and pick with your reasons stated. Do not resolve it silently.
- **Claiming an exit criterion that needs a person.** Say what you built and say
  what it still waits on.
- **Adding cleverness.** Every indirection you add is a file somebody has to
  open at 2am to answer a simple question.
- **Reporting green from inference.** Run it. Paste the output.
- **Writing for a developer on a page a member reads.** This portal replaces
  members.heatsynclabs.org. A member has no terminal, so no error copy names a
  make target, a script, or an HTTP method, and `check_portal.py` and
  `check_sign_in.py` now refuse one that does. What a member can do is try
  again and tell an admin.
- **Naming an LLM as an author anywhere.** The commit hook and CI both reject it.
- **Em dashes, en dashes, emoji, or a spaced hyphen standing in for a dash.**
  The prose gate rejects those in commit messages and code comments too.

## Done means

`make check` is green, `HANDOFF.md` section 2 matches what is on disk, every
number in what you wrote came from a command you ran, and your report says
plainly what you did not finish. Report what you did not finish every time.
