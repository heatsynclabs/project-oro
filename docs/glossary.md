# Glossary

The domain language. Code uses these words exactly, in these spellings, and does
not invent synonyms. Rule 7 of `CLAUDE.md`.

Where a term has a precise governance meaning, the bylaws win and the entry says
so. Where a term is a hardware fact, the firmware wins.

---

## People and membership

**member**
: A person with a membership record at the lab. Not the same thing as an account.
  There are paying members who have never signed up on the members site, which is
  why the person record and the login account are separate things in this system.

**account**
: A set of credentials that can sign in. Belongs to at most one member. A member
  may exist with no account.

**tier**
: What a member pays and what that entitles them to. The tiers are None, Unable,
  Volunteer, Associate, Basic, and Plus. Replaces the legacy `member_level`
  integer, which encoded the tier and the dollar amount in one column.

**dues**
: The monthly contribution. Framed as a donation to a community, not a
  subscription to a service, and the billing screens should read that way.

**good standing**
: Bylaws term. Current on dues, or on a current board approved scholarship. Use
  precisely. It gates card access eligibility and voting.

**lapsed**
: A member whose dues are overdue past the grace period. A state, not a judgement,
  and it is reversible by paying.

**orientation**
: The walk through a new member gets at the lab. Recorded with who ran it. In the
  legacy app it also gated the member directory and the equipment list, which was
  a mistake this system does not repeat.

**waiver**
: The signed liability release. Everyone who touches a tool signs one, member or
  not. Signing one creates a person record. It is the front door of the system.

**card access**
: 24/7 physical access via an RFID card. Lowercase. Earned, not bought. Bylaws:
  a paying member at $50 or higher, in good standing, for at least two months,
  nominated by a current cardholder, proposal posted publicly at least two weeks
  before Hack Your Hackerspace, approved by a simple majority of at least five
  cardholders present. The numbers live in `governance_parameters`, not in code,
  because they change.

**nominator**
: The cardholder who proposes someone for card access. Becomes that person's
  mentor and responsible party for a six month probationary period. The former
  limit of one nomination per member per year was deleted in July 2026.

**do-ocracy**
: Lowercase, hyphenated. The lab's operating principle: the people who do the
  work decide how it is done.

**Hack Your Hackerspace, HYH**
: The twice monthly meeting where card access votes happen. Short meeting, long
  work night.

**open hours**
: Lowercase. When the public can come in without being a member.

## Roles

Roles are rows, not boolean columns on a person. A member may hold several.

**admin**
: Can manage members, cards, and roles, subject to the two approver rule on
  privileged changes.

**accountant**
: Can record and reconcile payments. Cannot grant card access.

**instructor**
: Per tool, never global. Someone who instructs on the laser is not thereby an
  instructor on the mill, and only an instructor for a given certification may
  grant it.

**board member**
: An elected officer. Governance actions, not day to day operations.

## The door

**controller**
: The Arduino running `Open_Access_Control_Ethernet` on an isolated door VLAN,
  reachable only by the door service. It holds the
  card table in EEPROM and matches cards itself, with no network involved. It is
  the thing that actually opens the door.

**slot**
: A position in the controller's EEPROM card table, held in
  `cards.controller_slot`. Each slot holds 4 bytes of tag number and 1 byte of
  permission mask. The hardware addresses 0 to 199; the lab reserves 0 to 9 for
  testing, so **10 to 199 are assignable**. Slot 200 is not merely out of range,
  it wraps onto the persisted alarm state and corrupts it.
: In the legacy app the card's primary key *was* the slot, written to the
  controller verbatim. It no longer is: `cards.id` is a uuid with no hardware
  meaning. Migration copies the old card id into `controller_slot`, which is why
  those values are preserved exactly and never reassigned.

**tag number**
: The number on the RFID card itself, read over Wiegand-26. Stored as hex.
  Distinct from the slot.

**permission mask**
: The one byte permission value in a slot. Mask 1 is full access. Mask 255 is no
  access. `card_access_enabled` in the legacy app means holding at least one card
  with mask 1.

**privileged mode**
: The controller's single global boolean that unlocks every command except
  status. It is device wide, not per connection. Anything on the door VLAN is
  privileged while it is set, so every command sequence logs out in the same
  request.

**door service**
: The small service at the lab that speaks the controller's wire protocol. The
  only holder of the controller password, and the only thing that opens a socket
  to the controller. A synchroniser and a remote control, never a gatekeeper on
  the critical path.

**reconcile**
: The periodic job that reads the controller's card table, diffs it against the
  database, and writes only the differences, so drift heals itself. It diffs
  rather than rewrites because the firmware uses `EEPROM.write` and never
  `EEPROM.update`, so a blind rewrite every fifteen minutes wears the card table
  out in under three years. Idempotent by construction: a second run writes
  nothing.

**space_api.json**
: The public endpoint at `members.heatsynclabs.org/space_api.json` that says
  whether the lab is open. A SpaceAPI document. The public site and an ESP8266
  status LED both read it, so its address and shape are a contract that cannot
  break.

## The system

**approval**
: A change to admin access that needs a second admin. The proposer cannot approve
  their own. Covers granting a role that can itself grant roles; **revoking is
  single actor**, because a rule that makes removing a compromised admin need two
  people is a rule that fails at the worst moment. Enforced in the database, so
  no application path can skip it. It does not bind below two live admins, by
  design, because until then no two people could satisfy it. Every such grant
  raises a warning that records it.

**ground**
: A GANTRY design system term. The surface a block sits on. Setting
  `data-ground` on an element remaps the semantic colour tokens for it and
  everything inside, so text stays legible without hand picked colours. The four
  grounds are page, raised, plate, and hazard.

**GANTRY**
: The HeatSync design system. Industrial UI for the workshop floor. Nothing has a
  radius except circular UI, shadows are solid offset blocks rather than blurs,
  and amber is a fill rather than an ink.

**legacy**
: The Rails 3.2.8 application at `members.heatsynclabs.org` and its database. Use
  this word for it, not "the old system" or "v1", so search finds everything.

## Words this project does not use

| Do not write | Write instead |
|---|---|
| user | member, or account, depending on which you mean |
| cert | certification |
| perms | permission mask, or role |
| RFID badge | card |
| subscription | dues, or membership |
| customer, client | member |
| onboarding funnel | signup |
| the platform | the members system, or name the service |
