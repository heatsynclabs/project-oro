# API design

Two APIs, drawn deliberately apart.

- The **members API** is the system of record. Members, roles, cards,
  certifications, waivers, approvals.
- The **door API** is a device driver with an HTTP face. It knows about doors,
  slots, and a card table. It knows nothing about tiers, dues, or waivers.

They are separate because they have different availability requirements, different
blast radii, and different lifetimes. The members API can be down for an hour. The
door API is on a VLAN in a building with people in it.

This document is the contract. It is written before either service, per rule 12,
because everything downstream of an API is cheap to change and the API is not.

---

## 1. Principles

**Design the resource, not the screen.** The three portals are the first three
clients, not the only ones. A tool interlock, a kiosk, a stats display, and the
public site are all coming.

**One canonical representation per resource.** Not a members list shape and a
different member detail shape. The list returns the same object with fewer fields,
selected by `?fields=`, so a client never learns two shapes for one thing.

**Refusals say why.** An authorization failure returns a sentence a person wrote,
naming the rule. Never a bare 403, and never an empty 200 that a client has to
guess about.

**Errors are RFC 9457 problem details.** One shape, everywhere, both services.

```json
{
  "type": "https://oro.heatsynclabs.org/errors/quorum-not-met",
  "title": "Not enough card members present",
  "status": 422,
  "detail": "The bylaws require at least 5 card members present. This meeting recorded 3.",
  "instance": "/card-proposals/88"
}
```

**Versioned from the first commit.** `/v1/` in the path. The OpenAPI document is
generated from the service and a CI job fails when it differs from the committed
one, so it cannot drift.

**Nothing in the contract names the hardware.** The word Arduino appears nowhere
in either API. That is what makes the controller replaceable.

---

## 2. Authentication

Both APIs validate OIDC access tokens from the identity provider offline, against
its published JWKS. Neither ever sees a password.

Access tokens are ten minutes, refresh tokens rotate. A token carries `sub`,
`email`, and `name`, and no role claims. Roles live on the member row and are
looked up per request, so revoking admin takes effect on the next request rather
than the next login. That is a deliberate cost: one extra lookup, in exchange for
revocation that actually revokes.

| Client | Grant | Notes |
|---|---|---|
| members portal | authorization code with PKCE | public client, no secret |
| admin portal | authorization code with PKCE | plus an admin role checked by the API |
| door app | authorization code with PKCE | audience includes the door API |
| door service | client credentials | machine account, reads the card table |
| interlocks | client credentials | one account per device, individually revocable |

The door service caches the JWKS on disk. It must be able to verify a token during
an internet outage, and a JWKS fetch that fails closed would take the door app
down every time the upstream link blinks.

---

## 3. Members API

Base: `https://api.heatsynclabs.org/v1`

### 3.1 Self service

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/me` | member | Own member record, roles, tier, standing |
| PATCH | `/me` | member | Own editable fields. Contact, visibility, pronouns, skills |
| GET | `/me/cards` | member | Own cards. Tag numbers masked to the last 4 |
| GET | `/me/certifications` | member | Own certifications with granter and expiry |
| GET | `/me/waiver` | member | Whether a valid waiver is on file, when signed, and where it is kept |
| GET | `/me/door-events` | member | Own entries. Paginated, most recent first |
| GET | `/me/card-eligibility` | member | Eligible yes or no, the date, and what is missing |

`/me/card-eligibility` is a small endpoint that removes a recurring support
conversation. It answers the question members actually ask.

```json
{
  "eligible": false,
  "eligible_on": "2026-10-14",
  "requirements": [
    {"rule": "tier",     "met": true,  "detail": "Basic, card eligible"},
    {"rule": "tenure",   "met": false, "detail": "Two months required. Joined 2026-08-14."},
    {"rule": "standing", "met": true,  "detail": "Good standing"},
    {"rule": "waiver",   "met": true,  "detail": "Signed 2026-08-14"}
  ],
  "process": "A current card member nominates you, posts the proposal publicly at least two weeks before Hack Your Hackerspace, and a majority of at least five card members present votes."
}
```

`PATCH /me` never accepts `tier_id`, `standing`, `roles`, or `paid_through`. A
member cannot promote themselves, and the field is absent from the schema rather
than validated away, so the difference is visible in the OpenAPI document.

### 3.2 Directory

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/members` | member | The directory. Only members who are listed, only fields they made visible |
| GET | `/members/{id}` | member | One member, same visibility rules |

Gated on being a member, **not** on orientation. The legacy app gated the
directory on an admin having typed a date into a field, which locked paying
members out for a volunteer's inaction.

Row visibility is a policy on `members`: a member may read rows where
`listed_in_directory` is true. **Column visibility is not, and cannot be**, because
row level security is row level. `email_visible` and `phone_visible` are enforced
by the `member_directory` view, which is the only thing the directory endpoints
read. The base table is not exposed through them.

Saying this precisely matters: an earlier draft claimed the policy prevented a new
endpoint leaking a hidden phone number. It does not. The view does, and only for
endpoints that use the view.

### 3.3 Administration

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/admin/members` | admin | Everyone, filterable, including unlisted and lapsed |
| POST | `/admin/members` | admin | Create a member with no account. The kiosk waiver path |
| PATCH | `/admin/members/{id}` | admin | Tier, standing, orientation, notes |
| POST | `/admin/members/{id}/waivers` | admin | Record that a waiver was signed, and where the document is |
| POST | `/admin/cards` | admin | Issue a card. Assigns the lowest free slot |
| PATCH | `/admin/cards/{id}` | admin | Label, permission mask |
| POST | `/admin/cards/{id}/revoke` | admin | Revoke. Reason required |
| POST | `/admin/certifications/{id}/grant` | instructor for that certification, or admin | Grant one |
| GET | `/admin/approvals` | admin | The two approver queue for admin access changes |

### 3.4 Hosting and instructing

A stated requirement, and one of the top three needs the lab has identified: any
member who is hosting or instructing must be able to check that a person signed a
waiver, without seeing what is on it.

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/waiver-status?member_id=` | member with a hosting or instructing role | Boolean plus the signed date. No personal information |
| GET | `/waiver-status?email=` | same | Same, for someone not yet a member |

This is what replaces an all or nothing Google Sheet. It returns a boolean and a
date and nothing else, because the system holds nothing else: the document stays
wherever the lab already keeps it, and `waivers` records only that it exists and
how to find it. A host checking somebody in does not need, and should not get,
that person's address.

### 3.5 The two approver flow

Covers **granting** any role whose `grants_roles` is true. Nothing else.

**Revoking is single actor, deliberately.** A rule that makes removing a
compromised admin need two people is a rule that fails at the worst possible
moment. The revocation is recorded with who did it and why, which is the control
that actually matters there. `approvals.kind` still accepts `revoke_role` so the
table can record one if the lab later wants that, but nothing requires it and
nothing consumes it today.

A dual control requirement on routine work gets routed around within a month, so
it stays on the one thing worth the friction.

```http
POST /v1/admin/approvals
{ "kind": "grant_role",
  "target_member_id": "…",
  "role_id": "admin",
  "reason": "Taking over operations from D. Kim" }

201 { "id": 88, "status": "pending", "expires_at": "2026-09-26T…" }
```

```http
POST /v1/admin/approvals/88/approve      # a different admin

200 { "id": 88, "status": "approved", "applied": true }
```

The proposer approving their own gets:

```json
{
  "type": "https://oro.heatsynclabs.org/errors/self-approval",
  "title": "You cannot approve your own proposal",
  "status": 409,
  "detail": "Admin access changes need a second admin. You proposed this one.",
  "instance": "/admin/approvals/88"
}
```

The API check produces that sentence. What makes the rule *true* is in the
database and it is more than one constraint: `approver_is_not_proposer`, a
composite foreign key tying the grant to the exact approval that authorised it, a
unique index so one approval cannot authorise two grants, and a trigger requiring
the approval to be approved, unexpired, of the right kind, and decided by two
people who both actually hold an admin role. See `data-model.md` section 3.

That detail matters because the obvious version does not work. A single
`approver_is_not_proposer` check only constrains rows in the `approvals` table. It
does nothing to stop `INSERT INTO member_roles (member_id, role_id) VALUES
($1, 'admin')`, which is the exact 2am script the rule exists to stop. Per rule 5
the SQL is authoritative and the service check is a courtesy, and that claim is
only honest if the SQL genuinely refuses. A test proves both refuse the same
case, and a separate test proves a direct insert with no approval is refused.

**This is a new policy.** It is not in the bylaws. The API documentation says so
in the endpoint description, because a system that quietly invents governance is
how a rewrite loses a vote.

### 3.6 Issuing a card

Deciding who gets a card is the lab's bylaws process: a cardholder nominates,
the proposal is posted publicly two weeks ahead, and card members vote at Hack
Your Hackerspace. **That happens in a room, and this system does not run it.**
Building a state machine for it would be building a governance platform.

What the system does is record the outcome and provision the hardware.

```http
POST /v1/admin/cards
{ "member_id": "…", "tag_number": "0000C4D9", "label": "front desk spare",
  "note": "approved at HYH 2026-09-10" }

201 { "id": "…", "controller_slot": 42, "active": true }
```

The slot is assigned by the API as the lowest free value in the addressable
range. `note` is free text and is where the vote gets referenced.

Revoking requires a reason, and enqueues a sync rather than waiting for the
timer, because a stolen card that keeps working until the next tick is a
different thing from a routine revocation.

### 3.7 The public endpoint that cannot break

`GET https://members.heatsynclabs.org/space_api.json` is read by the public site
from two components and by an ESP8266 status LED. The address and the shape are a
contract.

The members API serves it from the status the door service pushes upward, not by
reaching into the VLAN. It is the one endpoint with no authentication.

Staleness is bounded and visible rather than hidden. If the last heartbeat is
older than the bound, the payload keeps the last known lock state and the members
API records the staleness in its own logs and monitoring. It does not assert the
lab is closed, because a confidently wrong sign sends somebody across town while
a stale one is recoverable. The bound itself is a board decision, listed in
`docs/plan/people-and-custody.md` section 8.

Carry forward exactly, byte for byte, proven on a test hostname before the route
flips:

- `open` is true when either door is unlocked.
- `status` is `doors_open=both|door1|door2|none`.
- `Cache-Control: no-cache, no-store, max-age=0, must-revalidate`.
- The `/space_api/simple.json` variant returning the raw lock booleans.

**There is a hard size ceiling on this payload, and it is in firmware on a wall.**
`hsl_door_api_poller.ino` parses the response with `DynamicJsonDocument doc(1024)`,
a 1 KB buffer. The live document is roughly 900 bytes. Anything that grows it,
including a SpaceAPI v14 upgrade or adding `state` or `sensors`, overflows that
buffer, and the device does not report an error. It silently stops updating, so
the lab's open sign quietly goes stale and nobody knows why.

So: keep the 0.12 document at the existing path, under 900 bytes, byte for byte.
Serve v14 at a **new** path for new consumers. The poller gets reflashed on its
own schedule, or never, and either is fine.

Do not reproduce the literal `&amp;` double escape inside the feeds URL, but
check first whether anything depends on it.

`/space_api/alert_if_not/:status` is not carried forward. It is a public GET with
a side effect of emailing the Google Group, which anyone can trigger.

---

## 4. Door API

### 4.0 Transport, decided here rather than in the door phase

The door service and the controller share an isolated VLAN. Where the members API
runs is deliberately undecided, so this contract has to work whether the members
API is a container on the same lab network or a host somewhere else entirely.

That rules out the obvious shape. A public `door.heatsynclabs.org` with
synchronous request and response is an inbound path into the VLAN, which the VLAN
decision exists to prevent, and it would only work when the members API is remote
and reachable. Writing that contract and discovering the conflict during the door
phase is exactly the failure this plan claims to prevent.

So: **the door API is an internal contract, and the transport is pluggable.**

| Where the members API runs | Transport |
|---|---|
| On the lab network | Direct HTTP to the door service, permitted by one firewall rule naming one source address and one port |
| Anywhere else | The door service holds one outbound connection to the members API. Nothing inbound |

The contract below is identical over both. Two consequences fall out of that, and
both are design decisions rather than accidents:

**Commands are asynchronous.** A synchronous "the door opened at 18:04:12" cannot
be delivered over a channel the door service dials out on. So a command is a
resource: `POST` creates it and returns `202` with a status URL, and the caller
polls or waits. This is also more honest over a direct connection, because the
controller is a single threaded device behind a serialising lock and "accepted"
and "performed" were never the same instant.

**Status is pushed, not pulled.** The door service posts its status upward on a
heartbeat. The members API caches it and serves `space_api.json` from that cache
with an explicit staleness bound. Nothing reaches down into the VLAN to ask.

The cost, stated: if the outbound link is down, the public open sign goes stale.
It does not go wrong, because the contract carries `as_of`, and past a bound the
members API serves the last known state marked stale rather than asserting the
lab is closed. A stale sign is recoverable. A confidently wrong one sends someone
across town.

Interlocks are on the lab LAN, not the internet, and they call the door service
directly on the VLAN. They get their own firewall rule and their own machine
account, one per device, individually revocable.

### 4.1 The contract

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/healthz` | monitoring | Process, controller reachability, snapshot age |
| GET | `/status` | members API, direct transport only | Lock and alarm state, read from the controller, with `as_of`. On the outbound transport the door service pushes this instead |
| GET | `/doors` | member | The doors this installation has, and their capabilities |
| POST | `/doors/{id}/commands` | member with an active card | Queue an action. Returns 202 and a command resource |
| GET | `/commands/{id}` | the member who queued it, or admin | Command status: queued, sent, performed, failed, expired |
| POST | `/authorize` | machine | May this card use this tool, right now |
| GET | `/card-table` | machine | What the service believes the controller holds |
| POST | `/sync` | admin | Reconcile now. The loop also runs on a timer |
| GET | `/events` | members API | Buffered events since a cursor |

**`/doors` is the endpoint that makes the hardware replaceable.** A client asks
what exists and what it can do, rather than hardcoding two doors and eight
actions.

```json
{
  "doors": [
    {"id": "front", "name": "Front door",
     "actions": ["open", "unlock", "lock"], "state": "locked"},
    {"id": "rear",  "name": "Rear door",
     "actions": ["open", "lock"], "state": "locked",
     "unavailable_actions": [
       {"action": "unlock",
        "reason": "Disabled by lab decision, Hack Your Hackerspace, 2018-02-22"}]}
  ],
  "capabilities": {"bulk_write": false, "event_stream": false, "per_session_auth": false},
  "as_of": "2026-08-27T18:04:11Z"
}
```

Rear unlock is refused, and the refusal names the decision and its date. That is a
lab policy expressed as data, so when the lab changes its mind it is a
configuration change rather than a code change.

`capabilities` is the adapter reporting what the hardware underneath can do.
`per_session_auth: false` is the current Arduino admitting that its privilege bit
is global. A replacement sets it true and the serialising lock stops being
necessary, without the API changing.

### 4.2 Actions

A command is a resource, so it works over either transport in section 4.0.

```http
POST /v1/doors/front/commands
Idempotency-Key: 9f2c1e7a-...
{ "action": "open", "reason": "arriving for open hours" }

202 Accepted
Location: /v1/commands/8814
{ "id": 8814, "status": "queued", "door": "front", "action": "open" }
```

```http
GET /v1/commands/8814

200 { "id": 8814, "status": "performed", "door": "front", "action": "open",
      "accepted_at": "2026-08-27T18:04:11Z",
      "performed_at": "2026-08-27T18:04:12Z", "event_id": 90114 }
```

`status` is one of `queued`, `sent`, `performed`, `failed`, or `expired`. A
command carries a short expiry, because a door unlock that arrives four minutes
late is not a delayed success, it is a security event. The client shows "opening"
and resolves within a second or two on the direct transport, or within the poll
interval on the outbound one.

Failures are honest about what did and did not happen, because "did the door
actually open" is the only question that matters:

```json
{
  "type": "https://oro.heatsynclabs.org/errors/controller-unreachable",
  "title": "The door controller did not answer",
  "status": 503,
  "detail": "No response within 5 seconds. The unlock was not sent, so the door is unchanged. Cards still work. If this keeps happening, check that the controller is powered and on the lab network.",
  "instance": "/doors/front/commands"
}
```

Every action carries an idempotency key. The controller always returns HTTP 200
with errors as body strings, has no `Content-Length`, and signals end of body by
closing the socket, so a timeout genuinely cannot distinguish "not delivered" from
"delivered, response lost". A repeated `open` is harmless. A repeated slot write
must not double apply.

### 4.3 Offline behaviour

The door service holds its own durable copy of the card table in SQLite, in WAL
mode, on the door host. This is not an optimisation, it is required, for three
reasons.

1. **The reconciler cannot run safely without it.** With no local baseline there
   is no way to tell "the API says there are no cards" from "the API is broken",
   and that distinction is the difference between a working door and a mass
   lockout.
2. **Local authorization during a partition.** With a cached JWKS and a local card
   table, `POST /doors/{id}/commands` keeps working for members who already hold
   a card when the internet is down.
3. **`/authorize` for interlocks** is latency sensitive and will be called
   constantly.

Bounded honestly: refuse to serve from a snapshot older than 24 hours, and always
report which snapshot answered.

```json
{"allowed": true, "answered_from": "snapshot",
 "snapshot_taken_at": "2026-08-27T17:50:00Z", "snapshot_age_seconds": 842}
```

`/status` reads the controller directly, never a cached row, and carries `as_of`
so a stale answer is visibly stale rather than silently wrong. Status is the one
command the controller serves without authenticating, so it stays available when
everything else does not.

### 4.4 The reconcile loop

Brings the controller card table into agreement with the database by writing
only what differs. Runs on a timer and on demand.

Rules, each of which exists because of a specific failure mode:

- **Idempotent.** Read the controller with `?a`, diff against the desired table,
  write only differences. A second run writes nothing. This is a test, not an
  aspiration, and it protects the hardware: the firmware uses `EEPROM.write`
  rather than `EEPROM.update`, so an unchanged byte still costs an erase cycle,
  and a full rewrite every 15 minutes exhausts the rated 100,000 cycles in under
  three years.
- **Never shrink by more than a threshold.** If the desired table has 38 cards and
  the controller has 41, reconcile. If the desired table has 2, refuse, alert, and
  change nothing. A mass revocation caused by an API returning an empty list is
  the worst failure this system can have, and this guard is what prevents it.

  The guard has an explicit override, because a real mass revocation after a lost
  keyring looks the same as a broken API, and a guard with no way through turns a
  security response into a wedged sync. `POST /sync` accepts
  `{"confirm_shrink_to": 2}`, which applies once, is logged with the actor and the
  reason, and does not disable the guard for the next run.

- **Revocation enqueues a sync rather than waiting for the timer.** A stolen card
  that keeps working until the next tick is a different thing from a routine
  revocation, and the admin doing it should not have to know which.
- **Converge, never truncate.** Never `clearUsers` and rewrite. A partial failure
  after a clear leaves the building unlocked to nobody.
- **Verify by read back.** After writing, `?a` again and compare. The controller
  returns `cur:` for slot ids 201 to 999 that it actually rejected, so a write
  that reports success may not have happened.
- **Serialise everything.** One lock. The privilege bit is global device state, so
  two concurrent operations is a correctness bug.
- **Log out in the same request.** Use the trailing `&e=` form so login and logout
  are atomic and a crash cannot leave the controller open to the VLAN.

---

## 5. The adapter boundary

```
services/door/
  api/            HTTP. Knows no controller.
  domain/         Slots, cards, permissions, reconciliation. Pure, no I/O.
  adapters/
    base.py       The port every controller must satisfy.
    oac_ethernet/ The current Arduino.
    fake/         The same wire protocol, in memory.
```

The port is defined by what a door controller must do, not by what this Arduino
happens to do:

```python
class DoorController(Protocol):
    def capabilities(self) -> ControllerCapabilities: ...
    def status(self) -> DoorStatus: ...
    def read_card_table(self) -> list[SlotEntry]: ...
    def write_slot(self, slot: int, tag: str, mask: int) -> None: ...
    def clear_slot(self, slot: int) -> None: ...
    def perform(self, door: str, action: DoorAction) -> None: ...
```

Everything specific to the current hardware lives inside `oac_ethernet/` and
nowhere else: the query string format, zero padding to 3 and 8 characters, the
global privilege bit, reading until EOF because there is no `Content-Length`, the
97 byte request truncation caused by `String(100)` constructing the literal
`"100"`, the always 200 status code, and the 10 to 199 slot range.

The domain layer never sees a URL.

**Conformance tests run against every adapter, fake and real alike.** This is the
part that is usually skipped and it is what makes the fake trustworthy. A fake
that has drifted from the hardware is worse than no fake, because the suite is
green and the door is broken.

---

## 6. What is deliberately absent

- **Payments.** Out of scope. The schema reserves the tables, the API reserves no
  paths. When payments arrive they get a designed contract, not an endpoint bolted
  onto `/me`.
- **A generic query interface.** No `?filter=` with arbitrary SQL, no GraphQL. A
  named endpoint per real need. The set of clients is small and known.
- **Bulk endpoints.** Until something needs one. Three portals and a few hundred
  members do not.
- **Webhooks out.** Nothing subscribes yet. Adding them later is additive.
- **PostgREST.** Considered and rejected. It cannot express the approval workflow
  or produce a designed contract, and an app talking to Postgres over HTTP makes
  the layering rule in rule 5 structurally false while the linter still reports
  green. Reasoning in `.research/07-alt-api.md`. Row level security, which was the
  good half of that proposal, is kept.

---

## 7. How this gets built

1. Write the OpenAPI document for the members API. Review it. Merge it.
2. Generate a mock server from it and build the members portal against the mock.
   The portal is finished before the service exists, which is what proves the
   contract is usable.
3. Implement the service against the document. CI fails if the generated document
   differs from the committed one.
4. Same for the door API, but write the adapter port and the fake **first**, during
   the identity phase. The door ships last and gets de-risked first, because three
   previous rewrites stalled at exactly this point.

The contract is reviewed by a person who did not write it, before any client is
built against it. That review is the cheapest hour in the project.
