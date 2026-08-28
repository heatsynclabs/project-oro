# Data model

Why the schema looks the way it does.

**The schema itself is in `db/migrations/`. That is the authority.** This document
does not repeat the DDL, because a schema written in two places drifts and the
copy in the prose always loses. Column comments live in the migrations too, via
`COMMENT ON`, so the schema documents itself.

| File | Holds |
|---|---|
| `db/migrations/001_schema.sql` | Lookups and `members` |
| `db/migrations/002_access.sql` | Cards, door events, waivers, certifications, the two approval tables |
| `db/migrations/003_rules.sql` | The triggers that enforce the rules |
| `db/migrations/004_security.sql` | Row level security, roles, the door path |
| `db/seed/001_reference.sql` | Tiers, roles, governance parameters |
| `db/tests/` | 39 assertions. `db/tests/run.sh` rebuilds from nothing and runs them |

Three independent rewrites over eight years converged on most of this model.
Where they agreed, that agreement is the strongest available signal. Where they
disagreed, the disagreement is named and settled below.

Sources: `.research/02-repos-rewrites.md`, `.research/05-archive-governance.md`,
`.research/11-door-and-hardware.md`, `.research/12-verified-firmware-constraints.md`.

---

## 1. The decisions that shape everything

### 1.1 A member is not an account

The legacy `users` table is both at once, and that is the root of most of the data
rot, and it is a documented fact about the current data rather than a
hypothetical: there are paying members who have never signed up on
members.heatsynclabs.org at all.

So the members system holds a **member**, identity holds an **account**, and they
join on a nullable `identity_subject`. A member can exist with no login: somebody
signs a waiver at the kiosk and they are a person in the system. An account
created later matches the existing member rather than making a duplicate.

That is what lets the waiver be the front door instead of the signup form.

Policies key on the member row reached through `identity_subject`, never on the
token's email, because emails change and were never verified. Devise
`:confirmable` was never enabled, so no legacy address was ever proven to belong
to anybody.

### 1.2 A card is not a slot

The legacy app writes `cards.id` verbatim as the EEPROM slot index. No mapping
table, no modulo. It works, and it cements a 2013 Arduino's 200 slot ceiling into
the primary key of a table that will outlive the hardware.

So `cards.id` is the card's own identity and `cards.controller_slot` is the EEPROM
address, nullable and constrained to 10 to 199. Migration sets `controller_slot`
to the legacy `cards.id`, byte for byte, preserving every existing door mapping.
When the controller is replaced, the slot column changes or goes away and nothing
above it notices.

**Slot 200 is not merely out of range, it is destructive.** The firmware's bounds
check is `>` rather than `>=`, so 200 passes, and its offset of 1024 wraps through
the AVR's 10 bit address register onto addresses 0 to 4, which hold the persisted
alarm state. Slots 0 to 9 are reserved for testing by the Access Card Procedure.
Hence 10 to 199, enforced in the database rather than in a form.

Tag numbers are stored uppercase and constrained to it. Mixed case defeats the
reconciler's diff, so every pass would see a difference and rewrite every slot
while reporting success. That silently reintroduces the EEPROM wear problem the
diffing exists to prevent.

### 1.3 Roles are rows

The legacy schema has `admin`, `instructor`, `accountant`, and `hidden` as boolean
columns. All three rewrites replaced this with a join table, for the same reason
each time: a boolean cannot record who granted it or when, and adding a role means
a migration.

`instructor` in particular is wrong as a global flag. Somebody who instructs on
the laser is not thereby an instructor on the mill. The 2018 rewrite got this
right and enforced it in `routes/user_certs.js`, checking `instructors` for
`(caller, cert_id)` before allowing a grant. That rule carries forward.

Revocation is a recorded row, never a `DELETE`. "Who used to be an admin, and who
removed them" is exactly what an audit asks, and a deleted row cannot answer it.
That forces a surrogate primary key: a composite `(member_id, role_id)` would make
it impossible to grant a role back to somebody it was revoked from, which happens
whenever a person rotates off operations and later returns.

### 1.4 A tier is a row with a price

`member_level` is an integer whose value doubles as the dollar amount, read by two
pieces of code that disagree at the edges. Values 2 to 9 return `nil` from
`member_level_string`, a plain bug. The PayPal whitelist accepts seven specific
amounts and silently drops the rest, so a teacher paying the documented half rate
of $12.50 can never have a payment recorded.

Tiers become a table with a price in cents and a `card_eligible` flag, so the
bylaws rule that card access needs the $50 level is data rather than a constant in
code. The legacy integer survives on the member row as `legacy_member_level`, so
the migration stays auditable.

### 1.5 A waiver is a reference, not a copy

The system records **that** a member has a signed waiver, when it was signed, and
**where the document is kept**. It holds nothing that is on the document: no
name, no address, no phone, no emergency contact, no guardian, no signature, no
IP.

An earlier draft stored all of that. It was wrong. The lab already keeps waivers
somewhere, currently a Google Form and its sheet, and copying their contents into
a second system creates a second store of personal information to protect, keep
current, and eventually leak, in exchange for nothing. The question the software
needs to answer is "has this person signed one", and a boolean plus a pointer
answers it.

`storage` says which system holds it, `reference` says how to find it there. Both
are opaque to this system, so moving from a Google Form to something else later
is a data change rather than a schema change.

It also settles a problem the earlier design had. That draft required a hash of
the signed document, which an imported waiver could never supply, because a
spreadsheet row is not a document. No such column exists now and there is nothing
to hash.

Emergency contact moves back onto the member, which is where the current app
keeps it, and where it stays current.

### 1.6 A member edits their own profile

Matching the current app, a member may change their name, display name, pronouns,
phone, postal code, emergency contact, the four social links, their skills, how
they heard about the lab, and whether their email and phone are visible in the
directory.

They may also set their own **membership tier**. That is how the current app
works, and it is right for this lab: membership is a donation rather than a
subscription, so a person declares a level and arranges payment separately. It
grants nothing, because card access is decided by a vote of cardholders and not
by what somebody typed into a form.

What a member may not change: standing, paid through, orientation, the identity
their account is joined by, and the legacy columns. A trigger refuses those and
names why, rather than the API being the only thing standing in the way.

Changing your own email clears its verified date, and you cannot set that date
yourself.

### 1.7 One approval mechanism, covering admin access only

`approvals` gates granting a role that can itself grant roles. That is the whole
of it.

**Card access is deliberately not modelled as a workflow.** The bylaws process
for it happens in a room and on a mailing list: a cardholder nominates, the
proposal is posted publicly two weeks ahead, and card members vote at Hack Your
Hackerspace. Encoding that as a state machine with quorum counting and vote
tallies would be building a governance system, which is not what this project is
for. The system records the outcome: a card exists, or it does not, with the
usual `issued_at` and `revoked_at`.

The eligibility rule that the members site does need, two months at a card
eligible tier, lives in `governance_parameters` so it can be corrected without a
migration.

---

## 2. Governance numbers are data, not constraints

The obvious design puts the bylaws numbers in `CHECK` constraints: quorum five,
fourteen days notice, two months tenure. That is wrong, and the wrong version
looks more rigorous, which is why it needs saying at length.

The card access waiting period changed from six months to two, and the public
site still says six. Under a hardcoded constraint that correction is a migration
written by a developer, tested, and deployed. It should be somebody editing a
number.

That rebuilds a failure the lab has already named in its own review of bespoke
systems: building for exactly what you think you need today makes it far more
costly to change later than a system where somebody can swap a setting. Putting
the bylaws in SQL puts them where non technical members can never reach them,
which is the opposite of what a do-ocracy needs.

So the numbers live in `governance_parameters`, each with a **required `source`**
citing the bylaws section or vote that set it, plus a history table. A trigger
reads them at validation time. The guarantee is the same as a constraint: an
approved proposal that did not meet quorum cannot be recorded by any path,
including a script. What changes is that amending the bylaws is an admin editing a
number rather than a deployment.

A trigger is weaker than a constraint in exactly one way, worth stating:
`ALTER TABLE ... DISABLE TRIGGER` turns it off, while a `CHECK` must be dropped.
Both need the table owner, and neither is reachable by the application role.

**What stays a hard constraint:** `approver_is_not_proposer`. That is not a
policy parameter. It is the definition of what a second person means, and no
bylaws amendment makes self approval acceptable.

---

## 3. The two approver rule, and why it needs four mechanisms

This is the most machinery in the schema, so it needs justifying.

A single `approver_is_not_proposer` check only constrains rows in `approvals`. It
does nothing to stop `INSERT INTO member_roles (member_id, role_id) VALUES
($1, 'admin')`, which is precisely the 2am script the rule exists to stop.
Claiming the rule lives in the database while the database does not know about it
is worse than admitting it lives in the service.

Four pieces, each with one job:

1. **Typed columns** on `approvals` instead of a jsonb payload. An untyped payload
   cannot be joined to what it authorises, so an approval to grant `board` to
   Alice could lawfully justify granting `admin` to Bob.
2. **A composite foreign key** from `member_roles (approval_id, member_id,
   role_id)` to `approvals (id, target_member_id, role_id)`. This is what makes an
   approval authorise one specific grant and nothing else.
3. **A partial unique index** on `member_roles (approval_id)`, so one approval
   cannot authorise many grants.
4. **Two small triggers.** `approval_is_by_two_admins` on `approvals` checks both
   parties hold an admin role, at decision time, so a proposer who later loses the
   role does not retroactively invalidate a decision somebody already made.
   `role_grant_rules` on `member_roles` checks the approval is approved,
   unexpired, and of the right kind.

Plus a fifth thing that is not about the rule but about the record: two more
triggers freeze what an approval proposed and what a role grant recorded, so a
decided approval cannot be repointed at a different member afterwards and a grant
cannot be quietly moved. Without those, the composite key faithfully follows a
target that was edited after the fact.

Verified in `db/tests/two_approver.sql`, 18 assertions, including every refusal.

### 3.1 The bootstrap hole, which only running it revealed

The first version deadlocked. The trigger required both proposer and approver to
hold the admin role, so on a fresh database no admin could ever be created.
Reading the SQL it looked correct.

The second version allowed a grant when zero admins existed. That fixed the empty
case and left a worse one: at exactly one admin, no approval by two admins is
possible, so **you could never get from one admin to two.**

The rule now binds only when two or more live admins exist, expressed as
`two_approver_rule_can_bind()`. That is not a workaround, it is a true statement
about the policy: a two approver rule cannot bind until two approvers exist. It
also covers disaster recovery, because if the lab ever drops to one admin, that
admin can appoint another instead of the system being permanently unadministrable.
It grants no power that is not already held, since a lone admin already controls
everything the rule protects, and every bootstrap grant raises a warning that
records it.

---

## 4. Row level security

Enabled and **forced** on members, cards, door events, waivers, and member
certifications. The API connects as `oro_api`, a non superuser, so the policies
apply to it too and there is no bypass to take.

Three details decide whether this works or leaks, and each has bitten real
systems.

**`SET LOCAL`, never `SET`.** A plain `SET` persists for the life of the session,
and the API uses a connection pool, so the next request to borrow that connection
inherits the previous member's identity. That is the classic way an RLS system
serves one member's data to another, and it does not show up in testing because a
pool under low load rarely reuses across users.

**A missing identity raises rather than returning nothing.** Otherwise
`current_member_id()` returns null, every policy evaluates false, and the caller
sees an empty result. An empty result reads as "this member has no cards", which
is a wrong answer delivered confidently. The function is also `SECURITY DEFINER`
because it reads `members`, which has RLS forced, so the lookup would otherwise
recurse into the policy calling it.

**The door path needs an engineered bypass.** `FORCE ROW LEVEL SECURITY` applies
to the table owner as well, and a `SECURITY DEFINER` function runs as its owner,
so forced policies filter it like anyone else. An earlier draft claimed a function
"owned by a role no member policy touches" was exempt. Postgres does not give you
that. With no identity set the function returns nothing, the reconciler's shrink
guard correctly refuses to apply an empty desired state, and sync wedges
permanently while alerting forever.

So `door_reader` is a `NOLOGIN BYPASSRLS` role owning exactly one function. It
holds `SELECT` on `cards` and nothing else, which the function body needs in
order to resolve. The test connects as the door path with no identity set
and asserts the full active card table comes back.

Every policy gets a test per role including anonymous, and a test of the case it
must refuse. **A policy without a refusal test is untested**, because a policy that
returns everything passes every positive test.

One consequence worth stating, because it was a stated payoff of the original
plan and it survives the move away from PostgREST: row level security makes a
read only view safe to hand out. A stats kiosk, a board dashboard, or a yearly
report gets a view and a role with `SELECT` on it, and no application code
changes. That mechanism belongs to Postgres, not to whatever serves the API.

Door events narrow current behaviour. Today any oriented member can read
`/door_logs`, so anyone oriented can see everyone's comings and goings. Restricting
that to the member concerned plus admins is a change to how the lab works, and
section 8 of `people-and-custody.md` puts it to the board as a decision rather
than letting it happen as a side effect of a schema.

---

## 5. What the legacy schema got wrong

| Legacy | Problem | Fixed by |
|---|---|---|
| No foreign keys anywhere | Orphan rows possible, joins must tolerate nulls | Real keys throughout, plus a migration report of every orphan |
| `cards.id` is the EEPROM slot | Cements a 200 slot ceiling into a primary key | `controller_slot` as a separate constrained column |
| No range check on card id | Slot 200 corrupts the alarm state | `CHECK (controller_slot BETWEEN 10 AND 199)` |
| `card_number` unique only in the model | A race can insert duplicates | Partial unique index on active cards |
| Mixed case tag numbers | Would defeat the reconciler diff | Uppercase, enforced |
| `member_level` encodes tier and price | Values 2 to 9 return nil | `tiers` table |
| Role booleans on the user | Cannot record who granted or when | `member_roles` |
| `instructor` is global | A laser instructor could sign off the mill | `certification_instructors` |
| `payments` unique on `(user_id, date)` | Two payments in a day unrecordable | Constraint dropped |
| `orientation` gates the member directory | A volunteer's inaction locks out a paying member | Directory gated on membership |
| `hidden` filtered with `= false` | Null is not false, so null rows vanish | `listed_in_directory NOT NULL DEFAULT true` |
| `door_logs` mixes three shapes under `key` | Unparseable without special cases | Typed columns plus `detail` jsonb |
| No email verification, ever | Trust never established | `email_verified_at`, null on import |
| `toolshare_users` | Dead legacy table | Not migrated |

---

## 6. Migration

Build fresh with seed data now, ingest the production dump later. `legacy_id` on
every migrated table, and `controller_slot` holding the old card ids, are what
make that safe.

### 6.1 Order

Lookups, then `members`, then the identity import writing subjects back, then
roles, cards, certifications, waivers, door events. Foreign keys force most of it.

Legacy `admin`, `instructor`, and `accountant` booleans have no approval behind
them, and inventing one would be a lie in the audit trail. So the import script,
when it is written in phase 3, will run with the role trigger disabled inside one
transaction, writing `granted_by = NULL` and recording that these predate the
policy. A deliberate, logged exception
rather than a nullable column quietly permitting it forever.

### 6.2 The assertions that abort the migration

These are the difference between a migration and a data loss event.

- **Every card keeps its slot.** `controller_slot` must equal the legacy
  `cards.id` for every row. A renumbered card opens the door for the wrong member
  and the audit log blames the wrong card. Not negotiable.
- No card outside 10 to 199.
- No two cards sharing a slot.
- Every legacy user arrived, or is listed as deliberately skipped.

The migration names offending rows. It does not truncate, renumber, or skip them.
Afterwards, a read back verify: dump the controller's table with `?a` and compare
row by row.

### 6.3 Decisions needed before the import runs

Each is a person's judgement, not code. Section 5 of `people-and-custody.md`
gives each one an owner.

- Duplicate and blank emails, resolved on staging with the existing merge tool.
  `citext UNIQUE` will reject them otherwise.
- What `contracts` actually is. The Vapor rewrite's author asked the lab and
  nobody knew.
- Cards pointing at users that do not exist. An active card belonging to nobody is
  a security finding, not a data error.
- Cards at slot 200 or below 10.
- Members with a `payee`, somebody paying on another member's behalf. There is
  archive precedent and it needs a home if any rows exist.
- Where waiver documents live, and what reference identifies one. The import
  needs a `storage` and a `reference` per row, not the documents themselves.
