# Order of operations

Build order, dependencies, and an exit criterion for every phase.

The order is identity, member management, admin, door. Payments are out of scope
and the schema reserves room for them.

**Do not start a phase whose predecessor's exit criterion is unmet, and do not
declare an exit criterion met without the evidence named beside it.** That
sentence is the whole point of this document. Three previous rewrites had plans;
what they lacked was a definition of done that somebody else could check.

---

## The three rules that sit above every phase

1. **A verified, restorable backup of the production members database exists, and
   the restore has been proven onto a staging copy.** Nothing starts before this.
   A backup nobody has restored is a hypothesis.
2. **The door keeps working.** Every phase is designed so that physical cards open
   the door even when everything in this repository is down. The legacy Rails app
   keeps driving the door until phase 5 says otherwise, and it is not touched
   before then.
3. **Every phase has named people, and a phase does not start while the roles it
   needs are empty.** See `docs/plan/people-and-custody.md`. This is the rule that
   addresses what actually killed the previous three attempts, which was never
   architecture. Treating it as advisory would make it decorative.

Each phase also ends with its **driver's seat drill**: a person who did not build
that phase performs its core operation from the written runbook while the person
who built it watches and says nothing. Every question asked out loud is a defect
in the runbook and gets fixed before the phase closes. It costs an hour, and it is
the cheapest thing in this plan.

## The failure this order is designed against

Three independent rewrites over eight years stalled at the same place: the point
where you have to take over the physical door and the money.

The 2018 Node rewrite built a door broker, a `DOOR` principal, and an active
cards endpoint shaped for the controller, then never wrote the twenty lines that
act on a message. The 2025 Swift rewrite produced the best annotated schema of the
four and wired its signup form to `console.log`. Both opened issues for the hard
parts and closed none of them.

The door is last in this order, which is the same position it held in every plan
that failed. So it gets two specific protections:

- **The adapter port, the fake controller, and the conformance suite are built in
  phase 1**, not phase 5. The riskiest unknown is retired first even though it
  ships last.
- **Phase 5 has a dated exit criterion**, and if it slips twice the plan gets
  re-cut rather than quietly extended.

---

## Phase 0. Foundations

Nothing here is a feature. All of it is what makes the rest checkable.

1. Repository, the rules file, the prose gate, the commit hook, and CI running
   all three on every pull request.
2. `compose.yaml` with Postgres and Caddy, a `Makefile`, and `.env.example`.
3. Backup and restore: `pg_dump -Fc` on a timer, restic to an S3 compatible
   endpoint, and the weekly automated restore drill.
4. A verified restore of the production database onto a staging copy.
5. The staging copy answers the questions the migration cannot start without:
   duplicate and blank emails, card ids outside 10 to 199, cards pointing at
   users that do not exist, the distribution of bcrypt cost prefixes, whether
   `contracts` holds anything anyone needs, and whether any card carries
   permission mask 20.

**Exit:** `make up` on a clean machine gives a working stack. A restore drill has
run unattended and posted a green result to a channel a named person reads. The
staging queries above have been run and their answers are written into
`docs/plan/migration-findings.md`. The phase 0 driver's seat drill has been done:
somebody who did not build it brought the stack up and restored the database from
the runbook alone.

**Blocked by, and this is the real gate:** a shell on hsl-web. That is not a
technical problem, it is the credentials and custody problem this lab has not
solved since 2013, and the plan does not get to assume past it. It needs a named
grantor, two named recipients, and a date, per section 2 of
`docs/plan/people-and-custody.md`. Until those exist, phase 0 has not started, and
this document shows it as not started rather than in progress.

If access cannot be arranged, **that is the finding**, and it is worth more to the
lab than any architecture in this repository. Report it and stop.

## Phase 1. The contract, and the door port

The API is designed before anything is built against it. This is the phase that
determines whether the rest is cheap or expensive.

0. **Post the two approver proposal to Hack Your Hackerspace.** It gates phase 4
   and quorum at HYH is fragile, so a deferred vote slips a month at a time. Post
   it now and let the answer arrive before the build does.
1. The OpenAPI document for the members API, written, reviewed by someone who did
   not write it, and merged.
2. A mock server generated from it.
3. The database migrations: schema, constraints, comments, RLS policies.
4. Database tests for the policies and the rules. A test per policy per role,
   including anonymous, and a refusal test for every rule. **A policy without a
   refusal test is untested.**

   Plain `psql` scripts with expected output, run by `db/tests/run.sh`, not
   pgTAP. Both were tried. The plain version needs no extension installed, reads
   as a list of named assertions, and a volunteer can run one file by hand
   against a scratch database. That is worth more here than pgTAP's richer
   assertion vocabulary. Already built: 39 assertions, and the runner rebuilds
   the schema from nothing every time.
5. **The door adapter port, the fake controller, and the conformance suite.** No
   real hardware, no real service. Just the interface, a fake that speaks the
   real wire protocol, and the tests both must pass.
6. `gantry-tokens` extracted, with the two measured defects fixed: the `--ink-*`
   family moved into the ground blocks, and `[data-ground]` painting by default.
   A CI contrast checker over the theme by ground cross product.

**Exit:** the OpenAPI document is merged and a mock server serves it. The policy
suite passes for member, admin, and anonymous. The conformance suite passes
against the fake. The contrast checker passes and would have caught
`--ink-warn` on hazard.

**Why the door port is here:** so that phase 5 is assembly rather than discovery.

## Phase 2. Identity

1. Zitadel and its own Postgres in the compose stack, behind Caddy at
   `id.heatsynclabs.org`. Its own database, separate from member data.
2. Set the bcrypt cost deliberately after measuring it on the target host. Do not
   inherit the default unexamined; that is the most likely cause of a bad first
   day during a login wave.
3. Register the clients: three public PKCE apps, one machine account for the door
   service.
4. Ten minute access tokens, rotating refresh tokens.
5. Brand the hosted login and consent screens with GANTRY.
6. **Prove the password import, in two parts, because nobody has the plaintext.**

   The obvious criterion, "import twenty real hashes and sign in as each", cannot
   be executed. Signing in requires the passwords, and the whole point of a hash
   is that we do not have them. Written that way it would have been quietly
   downgraded to "the import ran without errors", which proves nothing about
   whether anyone can actually log in.

   So it splits:

   **(a) Mechanism, with synthetic accounts.** Generate bcrypt hashes with
   `bcrypt-ruby` at cost 10 with no pepper, matching the legacy configuration
   exactly, for passwords we choose. Include the awkward cases: a password over
   72 bytes, one with non ASCII characters, one with a trailing space, and one at
   the minimum length. Import them and sign in as each. This proves the hash
   format, the import path, and the verifier agree, and it is fully automatable.

   **(b) Reality, with volunteers.** Import the real hashes from the staging copy,
   then ask a cohort of actual members to sign in to staging with the password
   they already use. Ten people covering a range of account ages. They keep their
   password; we never see it. This is the only thing that proves the real data
   works, and it needs humans who volunteer, which makes it a scheduling task
   rather than an engineering one.

   Import every real hash regardless, and report the distribution of cost prefixes
   and any row Zitadel refuses, by legacy id, before anyone signs in.

**Exit:** part (a) passes for every awkward case. At least ten real members have
signed in to staging with their existing passwords, spanning the oldest and
newest accounts. Every hash the import refused is listed by legacy id with a
decision recorded for each. The whole deployment is reproducible from the compose
file plus a database dump, with no console click that is not also in
configuration.

**The condition that stops this phase:** if the import does not verify cleanly,
stop and switch to Logto rather than working around it. The decision and its flip
condition are in the identity ADR.

*Note.* The pepper question is settled: `config.pepper` is commented out and
`config.stretches` is 10 in the committed `devise.rb`. Confirm the deployed file
matches, since it is committed and a hand edit on the host would be invisible.

## Phase 3. Member management

The members API and the members portal, together, because a contract is only
proven by a client using it.

1. Implement the members API against the merged OpenAPI document. CI fails if the
   generated document differs from the committed one.
2. The service connects as a non superuser and sets the member identity per
   transaction, so the policies apply to it too and there is no bypass to take.
3. Members portal: profile, membership status, cards, certifications, waiver
   status, card eligibility.
4. The migration script, run repeatedly against staging until it is boring.
5. Seed data that is obviously invented, so nobody mistakes a fixture for a real
   member.

**Exit:** a member signs in with their existing password, sees their own record,
and cannot see another member's hidden phone number, proven by a test rather than
by looking. The migration runs end to end on staging with every assertion in
`docs/plan/data-model.md` section 6.2 passing, including that every card keeps its
slot.

## Phase 4. Admin

1. Admin portal: member list, member detail, roles, certifications, cards.
2. The two approver flow for admin access changes, enforced by the database
   constraint and mirrored by a service check that produces a readable refusal.
3. Card issue and revoke, with a reason required on revoke. Deciding who gets a
   card is the lab's existing bylaws process and happens in a room; the system
   records the outcome rather than running the vote.
4. Waiver status for hosts and instructors: the boolean, without the personal
   information behind it.

**Exit:** an admin proposes a role grant, cannot approve it themselves, and a
second admin approves it, proven at the database level and in the UI. A card
proposal recorded with four cardholders present is refused by the database.

**The proposal was posted at the start of phase 1, not here.** The two approver
rule is a new policy and it needs an HYH vote. Posting it three phases ahead of
the build means the vote arrives before the work does, rather than the work
arriving first and arguing on the proposal's behalf by having already been paid
for. That pressure is exactly what the lab resents when other people do it.

**If the vote fails**, and this is written now while it costs nothing: the trigger
and the `approver_is_not_proposer` constraint are dropped, the `approvals` table
stays as an audit log of privileged changes by a single actor, and the admin
portal drops the approve step. About a day of work is discarded, because the audit
trail is identical either way and only the gating changes.

## Phase 5. The door

Assembly, because the port, the fake, and the conformance suite already exist and
have been green since phase 1.

1. Implement the `oac_ethernet` adapter against the real wire protocol. It passes
   the same conformance suite the fake passes.
2. Deploy the door service on the door VLAN at the lab. Firewall rule written into
   the runbook: this host and nothing else reaches the controller.
3. The SQLite snapshot, the buffered event log, and a bootstrap snapshot shipped
   with the deploy so a fresh install on a partitioned network is not helpless.
4. Run the reconcile loop **read only** for a week beside the live system,
   reporting the diff it would apply and writing nothing. The diff posts daily to
   a channel a named person reads, and a day with no post is a red day.
5. **Freeze card management in the legacy app. This is the moment the new
   database becomes the system of record for cards, and it happens before any
   write is enabled, not after.**

   Without this step the two systems are both writing. An admin revokes a card in
   Rails, and the ORO reconciler, whose desired state came from a database that
   never saw the revocation, writes the card back to the controller on its next
   pass. The revocation silently undoes itself and the audit log in each system
   looks correct. That is the worst failure this project can produce, because it
   is a door that opens for somebody who was deliberately removed.

   Freezing means: the card create, edit, and upload routes in the legacy app are
   disabled, not merely unused, and the operations team is told on the day. A
   convention that people will stop using a screen is not a freeze.
6. Turn on writes. Verify by read back against `?a`.
7. Serve `/status`, and prove `space_api.json` parity on a test hostname, byte for
   byte against the current output, under 900 bytes so the wall poller's 1 KB
   buffer still parses it.

**Exit:** the reconcile loop has run clean for a week in read only mode, then a
week with writes, and the controller's table matches the database exactly at the
end of it. `space_api.json` on the test hostname is byte identical to production.
The door never blinked.

**Dated.** This phase gets a date when phase 4 exits. If it slips twice, re-cut
the plan rather than extending it quietly, because that is the failure mode of
every previous attempt.

## Phase 6. Cutover

1. Point `members.heatsynclabs.org` at the new portal, and route `/space_api.json`
   to the door service. The public site changes nothing.
2. Keep the Rails app running and **fully read only** for two weeks as a
   fallback. Card management was already frozen in phase 5; this extends the
   freeze to everything, so there is exactly one writer for the whole system and
   the fallback is a fallback rather than a second source of truth.
3. Decommission it. Separately, and regardless of this project's timeline, the
   legacy payment notification endpoint has a security defect that should be
   reported privately to whoever operates that application and fixed or disabled
   there. It is out of scope here and the details do not belong in a public
   repository.
4. Drop the dead credential columns.
5. Fix the stale public copy: six months to two months on the membership page, and
   the mailing address from 140 to 108 W Main St.

**Exit:** the Rails container is off, the door ran continuously through the whole
project, and the field manual gets its retirement note.

---

## Later, deliberately not now

Each of these has a reserved place and no implementation. Naming them is how they
stay out of scope without being forgotten.

- **Payments.** Schema reserved, no endpoints. When it arrives it gets a designed
  contract, not an endpoint bolted onto `/me`.
- **Tool interlocks.** `/authorize` exists in the door API design and serves from
  the local snapshot, so the hardware side can be built independently.
- **Passkeys and MFA.** A Zitadel setting, per member, with no application change,
  because no app ever handles a credential.
- **The public site adopting `gantry-css`.** It has its own repository, its own
  cadence, and a vote behind its current design.
- **Replacing the controller.** The adapter boundary exists so this is one
  component and not a project.

## What would make me re-cut this plan

Stated now, while it is cheap to say.

- The password import does not verify against real hashes. Phase 2 stops and the
  identity choice changes.
- The production restore reveals card ids outside 10 to 199, or cards mapped to
  users that do not exist, in numbers that make the migration a data cleanup
  project. Then cleanup becomes its own phase with its own owner.
- Phase 5 slips twice.
- Nobody but one person is contributing by the end of phase 3. That is the
  condition that killed the previous two attempts, and it is a people problem
  that no architecture fixes.
