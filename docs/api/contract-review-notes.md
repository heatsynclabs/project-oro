# Contract review notes, members API v1

**This is not the review phase 1 asks for.** `docs/plan/order-of-operations.md`
phase 1 item 1 wants `docs/api/members-v1.yaml` "reviewed by someone who did not
write it, and merged", and HANDOFF.md section 2 records that review as the thing
phase 1 cannot exit without. That review needs a person who can answer for the
judgement calls in two years. What follows is a defect list handed to that
person so their hour goes on judgement rather than on finding typos. Nothing
here is merged, agreed, or a decision.

Read in this session: `docs/api/members-v1.yaml` in full, `docs/plan/api-design.md`,
`docs/plan/data-model.md`, all fifteen files in `db/migrations/`,
`db/seed/001_reference.sql`, `db/tests/directory.sql`, `docs/glossary.md`,
HANDOFF.md sections 2, 5, 6 and 7, ADR 0001 and ADR 0002. Every claim below
names the file and line range it came from.

`npx @redocly/cli@2.49.0 lint docs/api/members-v1.yaml` reports no errors and
five warnings, which is the count and the identity ADR 0001 records: one
`info-license`, two `operation-4xx-response` on the public status endpoints,
and two `no-unused-components` on the `NoSuchPath` and `WrongMethod` response
components at lines 1188 and 1205. The last two are the newest. They fire
because no operation references those components, and `info.description` at
line 58 argues that none can: a 404 for a path this document does not declare
has no operation to hang it on, and the 405 belongs to the path rather than to
any operation under it. None of the five is a finding and none is repeated
below.

Findings are ordered by what they would cost to fix once services and portals
exist, most expensive first.

Four of the fourteen are addressed. Findings 1, 3, 9 and 14 carry a note saying
what was done and where. None of the four is deleted, because the record of
what was wrong is what this file is for. The other ten are open and none of
them has been decided.

Line numbers are against the working tree, not against the commit that first
wrote them. They move every time the contract does, so a citation that lands in
the wrong place is a drift to fix rather than evidence that the finding is
stale.

One exception, and it is marked where it applies. Where a finding carries a note
saying the text after it is the record of an earlier state, the numbers inside
that block are frozen at that state and land on nothing now. Finding 3 says so in
as many words. Do not renumber those: they are what makes the before readable.

---

## 1. `/me/cards` hands a member an EEPROM address

**Defect. Addressed in commit `bd55232`.** `/me/cards` (line 203) returns
`MyCard` (line 1629) now, a shape with no `controller_slot` and no
`permission_mask`, and `tools/mock/tests/check_contract.py` carries
`test_a_member_is_never_handed_a_door_controller_address`, so pointing the
reference back at `Card` turns the contract suite red. What follows describes
the state before that commit and is kept as the record of it.

`/me/cards` returned an array of `Card`, and `Card` (line 1701)
carries `controller_slot` and `permission_mask`. The endpoint description says
tag numbers are masked to the last four characters and says nothing else about
which keys come back, so a client reading this document is told the slot is part
of the response.

`docs/plan/data-model.md` line 55 makes `controller_slot` the EEPROM address on
the door controller. The contract's own `info.description` at line 80 says
"Nothing here names the hardware. That is what keeps the door controller
replaceable." Those two cannot both hold on this endpoint.

The lab already decided this, in the wrong layer.
`tools/members-portal/tests/check_appearance.py` line 130 is a test named
`test_no_door_controller_slot_reaches_a_member`, and `apps/members/README.md`
line 178 records dropping "Slot 041" from the mockups for exactly this reason.
So the rule exists and is enforced on one of three portals, by a client side
test, while the contract all three are built against still declares the field. Rule 5 says a rule lives in one place and the authoritative place is
named. Here the authoritative document disagrees with the courtesy layer.

`permission_mask` is the same shape of problem one step quieter. `docs/glossary.md`
line 111 defines it as the one byte permission value in a slot, and the contract
repeats "Mask 1 is full access and mask 255 is no access" at line 1750, in a
response an admin reads. On `/me/cards` it is gone.

Cost later: removing a declared field after clients render it is a breaking
change to every generated type. Cost now: deciding which keys `/me/cards`
returns and saying so.

## 2. `?fields=` is unconstrained, and the directory is where that bites

**Defect.** This is the phase 3 exit criterion, stated as a contract question.

`Fields` (line 1058) is one shared parameter, typed `{type: string}`, described
as "Comma separated `Member` field names". It is applied to `/members`,
`/members/{id}` and `/admin/members`. Nothing in the machine readable document
says the permitted set differs between the directory and the admin list, and
nothing bounds it to what the directory can actually produce.

The directory reads `member_directory`, and after `db/migrations/011_close_read_holes.sql`
line 53 that view has eight columns: `id`, `name`, `pronouns`, `email`, `phone`,
`current_skills`, `desired_skills`, `joined_on`. `Member` declares roughly thirty
properties. `fields=emergency_phone,postal_code,standing` is a legal request
against this contract and has no answer in the view.

The prose is careful. Line 339 says "The base table is not reachable from this
endpoint." The schema does not say it, and the mock server serves the schema.
Somebody implementing `fields` generically, over one `Member` projection shared
by all three endpoints, writes the leak and passes the lint.

One thing the reviewer should check rather than take from me. HANDOFF.md
section 7, in the entry that begins "A view is not covered by the policies
underneath it", says `member_directory` "now sets that option", meaning
`security_invoker = true`. Migration 009 line 14 does set it true. Migration
011 line 67 then sets it back to false and replaces the view with one that
gates itself on `current_member_id() IS NOT NULL`, and 011 line 47 drops the
`member_reads_directory` policy that made invoker mode work. The final state is
a definer view that filters itself. That is defensible and it is not what
HANDOFF section 7 describes, so at least one of the two is stale and the
reviewer should not rely on that entry while judging this finding.

Cost later: narrowing a free text parameter to an enumerated set after clients
send arbitrary values breaks them.

## 3. Six embedded `Member` objects the database will not fill

**Defect. Every property with this problem now says so in the contract, and
the shape decision underneath is untouched. There are seven of them, not six:
the list below missed one, and two of the six it names carried no description
rather than the wrong one.** What follows the note describes the state before
that edit and is kept as the record of it, line numbers included.

The count came from reading the document rather than from this finding. Six
copies of "Only `id` and `name` are populated" were in it, one of them wrapped
across two lines so that a plain grep found five. Those six were not the six
properties listed below, and the difference is the whole correction.

What was done, per occurrence, because the answer turns on who reads the
response rather than on which schema carries the property:

- **Corrected.** `Member.oriented_by` and `RoleGrant.granted_by`, both read by a
  member on `/me`. `MemberCertification.granted_by`, read on
  `/me/certifications`. `Waiver.recorded_by`, read on `/me/waiver`.
  `MyCard.revoked_by` was already done. Each of them now names
  `member_reads_self` and `admin_reads_all` in `db/migrations/004_security.sql`,
  names `db/migrations/011_close_read_holes.sql` as what dropped the third
  policy, says which operation can fill the field where one can, and points
  back here.
- **Described for the first time.** `RoleGrant.revoked_by` and
  `MemberCertification.revoked_by` carried no description at all, so this was
  invisible on them rather than misstated. They now say what their siblings say.
  A field that will be empty and says nothing is worse than one that says it.
- **Left alone.** `Card.revoked_by`, which this finding already excluded and
  which is only ever read under `/admin/cards`. And `Approval.target_member`,
  which carried the same sentence and which this finding never mentioned:
  `Approval` is returned by the three operations under `/admin/approvals` and by
  nothing else, so `admin_reads_all` does let the reader resolve it.
- **`Waiver.recorded_by` is the seventh**, and the list below does not have it.
  It carries a `Member` object, a member reads it on `/me/waiver`, and
  `member_reads_own_waiver` in `004_security.sql` gets them the waiver row
  without getting them the admin's.

Nothing is decided by any of that. Whether these fields ever get filled still
needs a `SECURITY DEFINER` name lookup designed and tested, or every screen that
renders "granted by" changing shape, and it is one decision covering all seven.

These properties are declared on responses a member reads about themselves:

- `Member.oriented_by` (line 1409)
- `RoleGrant.granted_by` (line 1298) and `RoleGrant.revoked_by` (line 1312),
  reached through `Member.roles`
- `MyCard.revoked_by` (line 1580), returned by `/me/cards`
- `MemberCertification.granted_by` (line 1730) and `revoked_by` (line 1740),
  returned by `/me/certifications`

Each is a `Member` object, and the five that have not been touched say only
`id` and `name` are populated.

`Card.revoked_by` (line 1662) is deliberately not on that list. `Card` is
returned by three operations and all three sit under `/admin/cards`, where the
reader is an admin and `admin_reads_all` does let them read the row. It was on
the list before commit `bd55232`, because `/me/cards` returned `Card` then and
the reader was a member.

After `db/migrations/011_close_read_holes.sql` line 47 drops
`member_reads_directory`, the only SELECT policies left on `members` are
`member_reads_self` and `admin_reads_all`, both in
`db/migrations/004_security.sql` lines 37 and 41. A member cannot read another
member's row at all. So a non admin calling `/me` cannot be given the name of the
admin who granted their role, and a member calling `/me/cards` cannot be given
the name of whoever revoked their card, unless something new reads those names
past the policy.

ADR 0002 already records that Prism serves these as `{"$ref": null}` because
they close a reference cycle, and treats that as a mock defect the portal stubs
around. The sharper reading is that the mock and the database agree: these
fields are empty for a member, and only the contract says otherwise.

Cost later: high. Either a `SECURITY DEFINER` name lookup gets designed and
tested, or every screen that renders "granted by" changes shape.

## 4. Five collections return a bare array and one returns an envelope

**Defect, and the most mechanically expensive one here.**

`/me/cards`, `/me/certifications`, `/members`, `/admin/members` and
`/admin/approvals` all return `type: array` directly. `/me/door-events` returns
`DoorEventPage` (line 2013), an object with `items` and `next_cursor`.

Adding pagination to a bare array later means changing a JSON array into a JSON
object. Every client breaks on the same day. `/admin/members` is the one that
will need it: line 388 says it returns "Every member, including unlisted and
lapsed", and that set only grows, unlike the directory whose line 345 argument
about a few hundred rows is sound.

The `Limit` and `Cursor` parameters already exist as components. Whether every
collection gets the envelope now, even where the page is always complete, is a
judgement for the reviewer. It is much cheaper today than in phase 4.

While there: sort order is stated on `/me/cards` ("newest first") and
`/me/door-events` ("most recent first"), and is unstated on the other four.

## 5. Nothing in this contract handles a first sign in

**Defect.**

`GET /me` (line 136) declares 200 and 401 and nothing else. The 401 is defined
as "No token, or a token this API could not validate" (line 1101). A valid token
belonging to a person with no member row is neither of those.

That state is real and the database expects it.
`db/migrations/008_system_paths.sql` line 15 defines `link_or_create_member`,
described at line 49 as "First sign in. Claims an existing member row by email
when it has no identity yet, otherwise creates one. The only path that writes a
member without an admin." `current_member_id()` returns NULL for a subject with
no row (`012_close_remaining.sql` line 59), and `waiver_status` raises "No member
matches the identity on this transaction" in that case (`011` line 22).

No operation in this document calls that function, and neither
`api-design.md` section 3.1 nor the `memberToken` description (line 1034) says
what happens on the first request after a member signs in for the first time.
Every portal's boot path depends on the answer.

Cost later: it is the first request all three clients make.

## 6. `CardEligibility` promises a breakdown the database does not compute

**Defect.**

`CardEligibility` (line 2026) requires a `requirements` array with one entry per
rule, each carrying `met` and a `detail` sentence, and the enum at line 2050 is
`[tier, tenure, standing, waiver]`.

`card_eligibility(uuid)` in `db/migrations/012_close_remaining.sql` line 141
returns three scalars: `eligible`, `eligible_on` and a single `reason` text. It
short circuits, so it reports only the first rule that failed. It never reads
`waivers` at all, so the `waiver` requirement has no source.

Two further disagreements in the same schema. Line 2035 says `eligible_on` is
"Null when something that is not about time is missing"; the function sets
`ready_on` and returns it non null on the tier failure branch (line 171) and the
standing branch (line 175). And `Tier.card_eligible` (line 1321) is described as
"Whether this tier may be nominated for card access" while `Tier.sort_order`
(line 1318) says "The card access minimum is compared on this, not on price".
The function compares `sort_order` (line 170) and ignores the flag, so the
contract documents two fields as the rule and the database uses one.

Cost later: either the SQL function grows to return the breakdown, or the
service recomputes eligibility from `governance_parameters` itself, and the
second one puts a business rule in two places, which rule 5 forbids.

## 7. Behaviour documented with no endpoint behind it

**Defect.** Rule 10 forbids documentation for code that does not exist, and this
is the same failure a step earlier: a contract describing operations it does not
declare.

- `/me/door-events` at line 274 says "an admin can read all of them". No admin
  door event endpoint exists. `admin_reads_all_door_events` in
  `004_security.sql` line 55 is real, so the capability exists and the contract
  is the only place a client could learn it does not.
- `RoleGrant` (line 1345) describes granting, expiry and revocation with a
  reason, and `Member.roles` returns them. There is no endpoint that grants an
  ordinary role, and none that revokes any role. `api-design.md` section 3.5
  makes revocation single actor and calls it "the control that actually matters
  there", and `007_write_policies.sql` line 78 has the policy for it. The two
  approver flow can grant admin. Nothing can take it away.
- `MemberCertification.revoked_reason` (line 1870) says "Required when a
  certification is revoked. The database refuses one without it", which is true
  (`002_access.sql` line 126). No revoke endpoint exists, and
  `012_close_remaining.sql` line 133 added a policy specifically so instructors
  could do it.
- `ApprovalStatus` (line 2064) enumerates `rejected` and `withdrawn`. No
  operation produces either. Note that `decided_rows_have_a_decider` in
  `002_access.sql` line 162 requires a decider for `rejected` and forbids one for
  `withdrawn`, so those two are not the same operation and a later addition has
  to know that.

Cost: adding paths is additive and cheap. `ApprovalStatus` is the exception,
because it is already in every generated client's type and narrowing an enum is
not additive.

## 8. Two admin operations need an id nothing returns

**Defect.**

`PATCH /admin/cards/{id}` and `POST /admin/cards/{id}/revoke` are keyed on the
card's uuid, and `CardId` at line 1080 says so plainly: "This is the card's own
identity, not its slot." The only operation in this document that returns a card
uuid to an admin is `POST /admin/cards`, at the moment of issue.

There is no `GET /admin/cards`, no `GET /admin/members/{id}/cards`, and no way to
look up a card by tag number. An admin revoking a lost card tomorrow has no
contract path to the id the revoke endpoint requires.

The same gap on members, one step smaller: there is no admin GET of one member.
`GET /members/{id}` is the directory endpoint and returns
`NotInDirectory` (line 1154) for anybody unlisted, which is most of the people an
admin needs to open. `PATCH /admin/members/{id}` can write a record nothing can
read.

## 9. `PATCH /me` declares a 403 its own request schema makes unreachable

**Defect. Addressed on 2026-08-30, in the change that implemented the
operation.** Strictness was picked. `additionalProperties: false` stays, the
403 is gone from `PATCH /me`, and the operation's description says why. A body
naming `standing`, `paid_through`, `oriented_at`, `oriented_by`,
`email_verified_at` or `identity_subject` is answered 422 naming the field, and
nothing is sent to the database.

The argument that settled it is not about tidiness. `enforce_profile_self_edit`
in `004_security.sql` line 88 returns early when the caller is an admin, so an
endpoint that forwarded whatever name it was given would let an admin point
`identity_subject` on their own record at another sign in, through a self
service path, with no approval behind it. Revocation is single actor and role
grants for admin need two, so that would be a way round the two approver rule.
`services/api/app/profile.py` carries the same reasoning where the code is, and
`test_the_identity_a_record_is_joined_by_is_not_a_field_either` in
`services/api/tests/check_profile_edit.py` holds it.

The trigger did not become a courtesy layer by this. It still refuses those
columns to every other writer, and it is the only thing that decides them.
What the API decides is what the operation takes, which is a different question
and a narrower list: `joined_on` is refused here and the trigger allows it.

What follows is the finding as it was written, and its line numbers are
frozen at that state.

`PATCH /me` declares a 403 at line 186 whose example says membership standing and
orientation are set by an admin. `MemberSelfUpdate` (line 1541) sets
`additionalProperties: false` and does not declare `standing`, `paid_through`,
`oriented_at`, `oriented_by` or `email_verified_at`. A request carrying any of
them is schema invalid, which the same operation already answers with 422.

So either unknown fields are rejected at the schema and the 403 is dead, or the
service accepts them and the 403 is the answer, in which case
`additionalProperties: false` is wrong. The trigger underneath
(`004_security.sql` line 98) raises for exactly that field list, so the refusal
sentence is real. It is the status code and the strictness that need deciding.

## 10. Refusals the database can raise and the contract does not declare

**Defect.** `api-design.md` line 29 says a refusal names its rule and is never a
bare failure. An undeclared refusal reaches a client as a 500.

`POST /admin/approvals/{id}/approve` declares 401, 403, 404 and 409. Two more
are reachable:

- `enforce_approval_is_by_two_admins` (`003_rules.sql` line 44) raises "The
  proposer of this approval is not an admin." when the proposer lost the role
  between proposing and being approved. That is a live case: revocation is
  single actor and deliberately fast.
- `enforce_role_grant_rules` (`013_bootstrap_three_admins.sql` line 115) raises
  "Approval N had expired when it was decided." The declared 409 `expired`
  example covers the approval being expired at approval time, which is the same
  sentence for a different check, and the reviewer should confirm one code
  covers both.

`POST /admin/approvals` declares no refusal for proposing a role whose
`grants_roles` is false, though `ApprovalCreate.role_id` at line 2137 says only
such a role belongs in this queue. No database constraint refuses it either, so
today that request would create a row nothing acts on.

## 11. `RoleGrant.approval_id` describes a rule that changed

**Defect, small, and the kind that outlives everyone who knew better.**

Line 1375 says `approval_id` is "Null on the grants made while the lab had fewer
than two admins and the two approver rule could not yet bind."

`db/migrations/013_bootstrap_three_admins.sql` replaced that. The escape is now a
quota of three grants over the life of the database, spent by use rather than
measured against the live admin count, and `bootstrap_admin_quota()` at line 25
returns 3. HANDOFF.md section 7, in the entry that begins "The bootstrap escape
is not a security hole", states the distinction and says why it matters: "A
threshold of three would hold the escape open for as long as the lab had only
two admins". The contract still describes the superseded threshold.

## 12. `has_valid_waiver` names one of its two false cases

**Defect, small, and it is a safety string.**

Line 1961 says `has_valid_waiver` is "False when there is no record at all."

The function (`011_close_read_holes.sql` line 38) computes
`bool_or(expires_at IS NULL OR expires_at > now())`, so it is also false when
every waiver on file has expired, and in that case `latest_signed_at` comes back
populated. A host reading a false beside a real signed date will reasonably
conclude the system is confused. Rule 11 bans softened safety copy, and this is
the read side of the same concern.

Related, and a question rather than a defect: the function returns no rows for a
member with no waivers and no rows for a member id that does not exist, so the
service synthesises the 200 the contract promises at line 923. That means
`/waiver-status` answers 200 for any uuid at all. That looks deliberate, since it
refuses to be an existence oracle, and it should be written down as deliberate.

## 13. A deleted member is indistinguishable from a live one

**Question for the reviewer.**

`Member` at line 1419 says the deletion timestamp is not exposed, and no
endpoint or filter mentions it. `admin_reads_all` (`004_security.sql` line 41)
carries no `deleted_at` filter, so `GET /admin/members` returns soft deleted
members mixed in with everyone else and the response cannot tell them apart.

Elsewhere the schema is careful about this: `current_member_id`, `is_admin`,
`admin_count` and `member_directory` were all amended to read `deleted_at`
(migrations 011 and 012). The admin list is the one place it is still open, and
the contract is where it would be decided.

## 14. Email verification has an exit and no entrance

**Question for the reviewer. Answered in commit `bd55232`, in the contract
rather than with an endpoint.** `email_verified_at` (line 1434) now says an
absent date is a valid state and never a gate, that no operation here refuses a
member for it, and that confirmation belongs to the identity service. Nothing
was added to send mail, because nothing in this project configures a sender.

That answer was itself written with a false sentence inside it, which is worth
recording because it is the failure this file exists to catch. The description
named the legacy import and the bootstrap command as the two writers of the
column. Neither writes it. `tools/migration/020_migrate.sql` does not name the
column in its insert, and the bootstrap flag is `isVerified` on an identity
service account (`tools/bootstrap/identity_accounts.py`), which is a different
system holding a different record. No code here writes a date into that
column, and the only code that touches it at all is the trigger that clears it.
The description says that now, and names each file it was checked against.

`PATCH /me` at line 164 says changing your email clears its verified date, and
the trigger does exactly that (`004_security.sql` line 104). `email_verified_at`
is `readOnly` on `Member` and appears in no update schema. No operation in this
document sets it.

So a member who corrects a typo in their address moves permanently into an
unverified state, and nothing in the contract can move them out. Whether this
API should ever gain an entrance is still open, and the contract now says so in
place rather than leaving it to be discovered.

---

## Matters of taste, flagged and not asserted

- `POST /admin/certifications/{id}/grant` sits under `/admin/` and its own
  description (line 684) says an instructor who is not an admin may call it.
  `api-design.md` section 3.3 agrees. The path prefix reads as a permission and
  is not one.
- `Member.oriented_by` is a `Member` object on read and
  `MemberAdminUpdate.oriented_by` is a uuid on write. Generated clients get two
  types for one field. The same asymmetry sits on `tier` and `tier_id`, where it
  is at least named by two different keys.
- `Approval.expires_at` (line 2114) says "Thirty days after the proposal was
  made, unless an admin set otherwise". `ApprovalCreate` is
  `additionalProperties: false` and has no such field, so no admin can set it
  through this API.
- `Limit` (line 1083) is a shared component whose description says "How many
  events to return". Only `/me/door-events` uses it today. The wording will be
  wrong for the second user.
- The approval example at line 790 reads "Taking over operations from D. Kim".
  Seed and fixture data elsewhere is obviously invented, `Open Olive` and
  `Shy Sam` in `db/tests/directory.sql`. A plausible surname in the one example
  that will be served verbatim by the mock is worth a second look under rule 13.

## Checked and found sound

Recorded so the reviewer knows these were looked at rather than skipped.

- Authentication is applied consistently. `security` is declared globally at line
  107 and overridden to `[]` on exactly two operations, `/space_api.json` and
  `/space_api/simple.json`, both of which `api-design.md` section 3.7 says are
  public. No operation is unintentionally anonymous.
- Every error response in the document uses `application/problem+json` with
  `ProblemDetail`, and `ProblemDetail` requires `detail` (line 1252) rather than
  leaving it optional as RFC 9457 does. That is the right call for this project
  and it is argued in place.
- The 900 byte ceiling on `space_api.json`, its `Cache-Control` header and the
  refusal to carry `/space_api/alert_if_not/{status}` forward all match
  `api-design.md` section 3.7 and HANDOFF.md section 7, in the entry that begins
  "`space_api.json` cannot grow past about 900 bytes".
- Payments are absent as promised. `paid_through` is present, admin written, and
  labelled as such; the reserved `payments` table has no path.
- The two approver material is scoped to admin access, carries the NEW POLICY
  notice on all three operations, and the approve description at line 828
  correctly names the database as authoritative and itself as a courtesy.
- No email address appears anywhere in the document, and the door API is
  correctly absent: no command resource, no 202, no door status path. The door
  reaches this contract only through `/me/door-events` and the pushed status
  behind `space_api.json`, which is what `api-design.md` section 4.0 describes.
- Slot range 10 to 199, the tag number pattern `^[0-9A-F]{1,8}$`, the standing
  enum, the tier list and the role list all match the schema and the seed exactly.
- Every example in the document validates against its own schema. Redocly does
  not check that by default, so I read all twenty eight example payloads and the
  three scalar examples against the schemas they sit under.

The examples that are missing matter more than the ones that are there, and that
is already an open question at the foot of ADR 0002: no response carrying a
`Member` has a response level example, which is `/me`, both directory endpoints,
`/admin/members` and the members nested inside three others. Prism serves a
written example verbatim and falls back to the schema everywhere else, and
`apps/members/` is already built against it. Resolving that open question would
settle what is left of finding 3, and it would have caught finding 1 before
anybody read the schema, because an example is where a document says which keys
an endpoint actually returns.
