# People and custody

Who holds what, who answers what, and what happens when they stop.

This document exists because the previous three rewrites did not have one. Each
of them had a plan, an architecture, and a volunteer. What none of them had was a
second person and a written answer to "what if the first one stops".

**Every unfilled name below is a blocker, not a placeholder.** A phase does not
start while the roles it needs are empty. That rule is the only mechanism in this
plan that addresses the thing that actually killed the last three attempts, and
softening it would make this document decorative.

---

## 1. Roles

Each role names a person, a backup, and what breaks in their absence. Two people
per role is the minimum. One is the failure being designed against.

| Role | Holder | Backup | Without them |
|---|---|---|---|
| Build lead | TBD | TBD | The work stops. This is the role that stalled three times |
| Production access | TBD | TBD | Phase 0 cannot start |
| Secret custody | TBD | TBD | Section 3. Every secret is unrecoverable |
| Door and network | TBD | TBD | Phase 5 cannot start. The VLAN is theirs |
| Governance liaison | TBD | TBD | The two approver proposal never reaches HYH |
| Drill reader | TBD | TBD | Section 4. Failures are silent |
| Migration owner | TBD | TBD | Section 5. The blockers stay unowned |

Named holders go in this table and in `CODEOWNERS`, which does not exist yet and
gets created with the first real name. A role with one holder and no backup is
recorded as such, visibly, rather than left looking complete.

## 2. Production access is the first blocker, and it is not a technical one

Phase 0 requires a verified restore of the production database. That requires a
shell on hsl-web. That is the problem this lab has not solved since 2013.

The evidence that it is unsolved is structural, not personal. Server access has
at times been unavailable even to the person who wrote the application. Deploy
knowledge has tended to sit with one holder at a time, because documenting it
always lost to the next fire. Infrastructure has been registered under individual
accounts rather than organisational ones, and in April 2026 a lapse in that
arrangement took the door with it.

None of this is anybody's failing in particular, and naming individuals would
make it look like it was. It is what happens by default when custody is not
written down, which is the entire reason this document exists.

So this gets named rather than assumed:

- **Who grants access:** TBD. A board or operations decision under the bylaws.
- **Who receives it:** TBD, and a second person, because access held by one
  person is the same failure in a new hat.
- **By when:** TBD. Until this date exists, phase 0 has not started, and the plan
  should say so out loud rather than showing a green phase.
- **What is inventoried at the same time:** the registrar account, the DNS, the
  Operations KeePass, the GitHub organisation owners, and the certificate
  renewal path. Each gets a holder and a backup in the table above.

If this cannot be arranged, that is the finding. It is more useful than any
architecture in this repository, and it should be reported as the outcome rather
than worked around.

## 3. Secret custody

The stack uses SOPS with age. That is a good choice and it introduces a failure
the plan must not repeat: **if one person holds the age key, every secret in the
repository is cryptographically gone when they leave.** That is the lost KeePass,
rebuilt in a newer format, and it would be worse because it would look modern.

The rules:

1. **At least three age recipients** on every encrypted file. Two individuals and
   one offline key.
2. **The offline key is on paper**, in the lab's physical safe, with the date it
   was generated and who generated it. Not in a password manager, not in a cloud
   drive.
3. **Recipients are listed in `.sops.yaml`** once secrets exist. That file is in
   git, so who can decrypt production is a reviewable fact rather than folklore.
4. **Removing a recipient re-encrypts every file.** When someone leaves, that is
   the checklist item, and it is in the offboarding runbook.
5. **The recovery is rehearsed.** Once, before phase 2 ships, somebody who is not
   the author decrypts production secrets using only the paper key and the
   written procedure, while the author watches and says nothing.

That last one is the whole point, and it generalises. See section 6.

## 4. Every automated check names its audience

The plan contains a weekly restore drill, a reconcile diff during the parallel
run, and a CI suite. Each of these can fail silently forever if nobody is on the
other end. "Fails loudly" is not a destination. Loudly to whom, answered by whom,
by when.

| Check | Cadence | Posts to | Read by | If red |
|---|---|---|---|---|
| Restore drill | Weekly | TBD channel | Drill reader | Backups are not working. Stop feature work |
| Reconcile diff (parallel run) | Daily, phase 5 | TBD channel | Door and network | The diff is the exit criterion. A day with no post is a red day |
| CI suite | Per pull request | The pull request | Reviewer | Normal |
| Certificate expiry | 30 and 7 days out | TBD channel | Production access | Renew |
| Door service healthz | 5 minutes | TBD channel | Door and network | Section 7 of the door runbook |

**A missing report is a failure, not a pass.** Every one of these posts on green
as well as red, so silence is unambiguous. A drill that only speaks when it
breaks is indistinguishable from a drill that stopped running.

The drill reader's job is one glance a week. That is the honest size of it, and
it is worth stating, because the reason volunteer rotas fail is usually that
nobody knew how small the ask was.

## 5. Migration has an owner or it does not happen

The strongest argument in this project's history, and it is correct: the
dealbreaker is never features, it is whether you can pragmatically migrate onto
the thing. There is the best system, and then there is the system you can
actually move to.

These are the known blockers. Each needs a name and a date before phase 3, and
none of them is engineering work.

| Blocker | What it needs | Owner |
|---|---|---|
| Duplicate and blank emails | Someone runs the existing merge tool on staging and decides the ambiguous cases | TBD |
| What `contracts` actually is | Someone asks the lab. The Vapor author asked and nobody knew | TBD |
| Cards pointing at users that do not exist | Someone decides whether each is a revoke or a repair. An active card belonging to nobody is a security finding | TBD |
| Card ids outside 10 to 199 | Someone checks production and decides per card. Cannot be automated: renumbering is what must not happen | TBD |
| Where waiver documents live | The system stores a pointer, so somebody has to say what it points at: a form, a sheet, a drawer | TBD |
| Where signed waivers live | A governance call on PII. Made once, early | TBD |

If these have no owner by the start of phase 3, phase 3 does not start. Deferring
them is how the 2018 rewrite ended with an API and no way to move onto it.

## 6. The driver's seat drill

A sharper point than the usual documentation advice, also from this project's
history: comments in code are the wrong target. The real test is going through
the setup and maintenance with somebody else in the driver's seat, taking notes
on what they get stuck on. It is the author's own assumptions that are the
missing piece, and those only surface when somebody else tries.

So this is an exit criterion, not a nicety. **Once per phase, a person who did not
build it performs that phase's core operation from the written runbook, while the
person who built it watches and does not speak.** Every question asked out loud is
a defect in the runbook and gets fixed before the phase closes.

| Phase | The drill |
|---|---|
| 0 | Bring the stack up on a clean machine and restore the database from backup |
| 2 | Decrypt production secrets with the paper key. Add a member to the identity service |
| 3 | Run the migration against a fresh staging copy end to end |
| 4 | Propose a role change and have a second admin approve it |
| 5 | Deploy the door service and run a reconcile, read only, then verify by read back |

This is the single cheapest thing in the plan and it is the one that would have
caught what killed the previous attempts. It costs an hour per phase.

## 7. The governance work runs ahead of the build, not behind it

The two approver rule is a new policy. Building it before the vote means sunk
cost argues in the room on the proposal's behalf, which is exactly the backwards
pressure the lab resents when other people do it.

So:

- **The proposal is written and posted at the start of phase 1**, not before phase
  4 ships. The vote arrives before the build does.
- **The failure branch is written down now.** If the membership votes it down: the
  trigger and the `approver_is_not_proposer` constraint are dropped, the
  `approvals` table stays as an audit log of privileged changes with a single
  actor, and the admin portal drops the approve step. That is roughly a day of
  work discarded, because the audit trail is the same either way and only the
  gating changes. Saying this now, while it costs nothing, is what stops sunk
  cost from doing the arguing later.
- **The board hears the scope decision in plain words.** Payment tracking is the
  board's stated number one need and it is out of scope for this build. That
  sentence goes in front of them directly rather than being inferable from a
  phase list.

## 8. What the board is actually being asked to evaluate

Most of this plan cannot be assessed by someone who does not write software, and
pretending otherwise is a way of smuggling decisions past people entitled to make
them. These are the questions that are genuinely theirs, in their language.

1. **Door logs become private.** Today any oriented member can see everyone's
   comings and goings. This plan restricts that to the member concerned plus
   admins. That is a change to how the lab works and it deserves a vote, not a
   side effect of a schema.
2. **Two people will be required to change admin access.** New rule. Needs a vote.
3. **Payment tracking is not in this build.** The thing the board said matters
   most is deferred. That is a legitimate choice and it must be stated, not
   discovered.
4. **Access to member data will be graded rather than all or nothing.** Hosts and
   instructors will be able to check that a waiver exists without seeing what is
   on it. This is an improvement on the current spreadsheet and it is also a
   decision about who sees what.
5. **Somebody has to pay for a host, or the lab hosts it.** Small either way, and
   it must sit under an account the lab owns.
6. **This needs at least two people for a year.** Not as an aspiration. As the
   condition under which it is worth starting.

## 9. When to stop

Written now, while it is cheap, because a project with no stopping condition
stops by attrition instead and leaves a half migrated database behind.

Stop and report, rather than continuing quietly, if any of these becomes true:

- Production access cannot be arranged within a month of asking.
- Only one person is contributing at the end of phase 3.
- The password import does not verify against real hashes and the fallback is
  also unattractive.
- Phase 5 slips twice.
- The controller VLAN cannot be arranged.

Stopping at any of these leaves the lab better off than it is today, because
phase 0 alone delivers a verified, restorable backup of the members database,
which does not currently exist. That is worth having even if nothing else ships,
and it is the reason phase 0 comes first.
