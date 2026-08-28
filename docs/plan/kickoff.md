<!-- voice-check: reference -->

# Kickoff prompt

Paste this to start implementation. It assumes a fresh session with no memory of
how any of this got here.

---

You are implementing Project ORO, the members and door access system for HeatSync
Labs. The repository is already set up. Nothing is deployed and nothing in
production has been touched.

**Read these first, in this order, before writing anything:**

1. `CLAUDE.md`. The working rules. They bind you and most of them are enforced.
2. `HANDOFF.md`. Current state, how to run things, and section 7, which is a list
   of traps that already caught somebody. Read section 7 twice.
3. `docs/plan/order-of-operations.md`. The build order and the exit criterion for
   each phase.
4. `docs/plan/architecture.md` and `docs/plan/api-design.md` for the phase you are
   working on.

**Verify the repository is healthy before you change it:**

```sh
git config core.hooksPath .githooks
./db/tests/run.sh
python3 tools/voice-check/test_voice_check.py
python3 tools/voice-check/test_regressions.py
python3 tools/voice-check/test_behaviour.py
```

All of it should be green. If it is not, stop and say so rather than building on
top of it.

**Your task is the next unmet step in `docs/plan/order-of-operations.md`.** Do not
skip ahead. Do not start a phase whose predecessor's exit criterion is unmet.
Work out which step that is and say which one you picked before you start.

**The rules that catch people out:**

- **Never name an LLM as an author, co-author or reviewer.** Not in a commit, not
  in a pull request, not in a comment. The commit hook rejects it.
- **No em dashes, no en dashes, no emoji**, and do not substitute a double hyphen
  for a dash. The prose gate rejects it. This applies to code comments and commit
  messages, not only documentation.
- **Never assume.** Read the version, the column name, the config key from the
  source. If you cannot check something, write down the assumption and what would
  confirm it.
- **Test first, and test the behaviour rather than the call.** A database rule is
  tested at the database level, because that is where it is enforced. A policy
  without a refusal test is untested.
- **`db/migrations/` is the authority for the schema.** `docs/plan/data-model.md`
  explains it and deliberately holds no DDL. Do not put schema in the prose.
- **No file over 300 lines**, no function over 50, complexity under 10.

**How to know you are done with a step:** the exit criterion in the plan is met,
with the evidence it names. Paste the output. If a test fails, say so and show it.
If you finished part of the step, say which part you did not do.

**When you are unsure whether something is in scope**, it probably is not. The
scope is identity, member management, admin, and door access. Payments are
explicitly deferred. A card access governance workflow was built once and removed
as out of scope; do not rebuild it.

Start by reading, then tell me which step you are picking and why, and what you
plan to do. Do not write code until we agree on that.
