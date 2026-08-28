# Architecture

The system, why each piece is there, and what it would take to replace it.

This revises the original ORO proposal. The differences from that document are
listed in section 8, with a reason for each, so a reader who knows the original
can see exactly what changed and why.

---

## 1. The shape

```
                        the internet
                              |
                    +---------+---------+
                    |       Caddy       |   TLS for every hostname
                    +---------+---------+
                              |
        +---------------------+---------------------+
        |                     |                     |
   +----+-----+       +-------+-------+     +-------+-------+
   |  Zitadel |       |  members API  |     | static apps   |
   | identity |       | FastAPI       |     | members       |
   |          |       |               |     | admin         |
   +----+-----+       +-------+-------+     | door          |
        |                     |             +---------------+
   +----+-------------------+-------+
   |   Postgres: two databases     |   members has RLS on, forced
   |   identity  |  members        |   separate roles, no cross access
   +-------------------------------+
                              ^
                              | one link, shape per the table in 4.2
                              |
  - - - - - - - - - - - - - - + - - - - - - - - - - - - - - - - - - - - -
  door VLAN, at the lab. Nothing inbound from the internet, ever
                              |
                    +---------+---------+
                    |   door service    |   FastAPI + SQLite snapshot
                    |   API + adapter   |
                    +---------+---------+
                              | plain HTTP, this VLAN only
                    +---------+---------+
                    | Arduino controller|   EEPROM card table, 200 slots
                    +---------+---------+
                              |
                    readers, strikes, alarm
```

**One Postgres server, two databases.** Credentials and member data do not share
a database, with separate roles and no cross database access, so the API role
cannot read password hashes and the identity service can be replaced without
touching member data.

Two separate servers would be marginally stronger and it is not worth it here:
it doubles what has to be backed up, upgraded, and monitored, for a threat model
where anyone who has reached the host has already lost you the argument. One
server, one backup job, one version to upgrade. Stated as a trade rather than
presented as free.

## 2. The pieces

| Layer | Choice | Why | What replaces it |
|---|---|---|---|
| Identity | Zitadel | The only candidate that imports Devise bcrypt with no fork, no third party JAR in the credential path, and no bespoke login UI. Verified against its own `cmd/defaults.yaml`. | Logto, if the volunteers are a TypeScript group or the import proves difficult |
| Members API | FastAPI, SQLAlchemy 2.0, Alembic, synchronous | Holds the OpenAPI contract, the workflow rules, and the call into the door service. Same language as the door service, so one backend language | Fastify with Kysely, if the maintainers are a TypeScript group |
| Database | Postgres 18, RLS enabled and forced | Invariants live where they cannot be bypassed | Nothing |
| Door service | FastAPI plus a controller adapter | Section 4 | Nothing. This is the one bespoke component and it always will be |
| Apps | Static, built against the OpenAPI contract | No server side rendering, no framework lock in | Section 5 |
| Theme | `gantry-css`, framework agnostic | The consumers are Astro, Vue, React 19, and Rails ERB. Only CSS reaches all four | Nothing |
| Proxy | Caddy | Automatic certificates in a few lines, one binary, and it works on a LAN with internal certificates | Traefik, if per route middleware chains are ever needed |
| Orchestration | Docker Compose plus a `Makefile` | Three apps and four services do not need a task graph | Swarm, if two hosts must fail over without a human |
| Secrets | SOPS with age, in git, rendered to Docker secret files | Rotatable, reviewable, and the repository is the source of truth | Nothing until the lab has someone whose job is a secret store |
| CI | GitHub Actions for tests only, never holding deploy credentials | Tests where the code is. Deployment stays independent of any vendor | Woodpecker, self hosted |

**PostgREST is not deployed.** It was the original proposal's centrepiece and it
is rejected. It cannot express the approval workflow, cannot produce a designed
contract, and an app talking to Postgres over HTTP makes the layering rule in
rule 5 structurally false while the linter still reports green. A gate that
reports green on a violated rule is worse than no gate. Row level security, which
was the good half of that proposal, is kept. Full reasoning in
`.research/07-alt-api.md`.

## 3. Portable Docker, and what that forbids

The stack runs identically on a laptop, the lab's Dell R610, a Hetzner box, a
droplet, or a Raspberry Pi. Where it runs is a decision the board can make later
without any of it reaching the architecture.

The test: **a member clones the repository onto a machine they own, provides an
`.env` and an age key, runs `make up`, and has the system.** If any step needs a
web console, it fails.

So these are banned from the repository, each with its replacement:

| Banned | Why | Instead |
|---|---|---|
| Provider object storage for backups | Ties the restore path to one account | Any S3 compatible endpoint in `ORO_BACKUP_REPO`. Backblaze, Wasabi, MinIO on a lab NAS, or SFTP |
| Managed Postgres | The database would live outside the compose file, so a laptop cannot reproduce it | `postgres:18` in the compose file, one named volume |
| A provider load balancer | Terminates TLS off host, so the LAN case has no TLS at all | Caddy in the stack, terminating TLS itself |
| Provider CLIs, metadata endpoints, floating IPs | Unrunnable anywhere else | Nothing. One hostname variable |
| Provider DNS or container registry | A vendor account in the critical path | Any DNS, any registry named by `ORO_REGISTRY` |

GitHub runs the tests. GitHub does not hold deployment credentials and cannot
deploy. That is deliberate: the archive records a domain expiring under a
departed member's personal account and taking door access with it. Nothing in
this system may depend on an account the lab does not control, and the escape
hatch gets rehearsed rather than assumed.

## 4. The door

The door subsystem is the part that must not break, because it is physical access
to a building with people in it.

### 4.1 It runs on its own VLAN

The door service and the controller share an isolated VLAN at the lab. The door
service is the only host permitted to reach the controller, as a firewall rule
written down in the runbook rather than an assumption.

This is the only real mitigation available for the controller's actual
weaknesses, which are worth stating rather than softening: it speaks plain HTTP,
its password is a compile time constant sent in a query string, and its
privileged mode is one global boolean for the whole device rather than a session.
While that bit is set, anything on the VLAN is privileged. Segmentation contains
that. Nothing short of new hardware fixes it.

### 4.2 There is no tunnel, and the transport is decided now

No WireGuard, no Tailscale, no inbound hole from the internet. That removes a
vendor, a daemon, and a class of failure from the original plan.

The transport is settled here rather than in the door phase, because the door API
contract is written in phase 1 and a contract that cannot be implemented under the
stated topology is worse than no contract. Two permitted shapes, and the contract
is identical over both:

| Where the members API runs | Transport |
|---|---|
| On the lab network | Direct HTTP, one firewall rule naming one source address and one port |
| Anywhere else | The door service dials out and holds one connection. Nothing inbound |

Two consequences, both design decisions rather than accidents:

- **Commands are asynchronous.** `POST` creates a command resource and returns
  202; the caller polls for the outcome. A synchronous "the door opened at
  18:04:12" cannot travel over a channel the door service dials out on, and it
  was never truthful anyway, because the controller is single threaded behind a
  serialising lock.
- **Status is pushed upward on a heartbeat**, and the members API serves
  `space_api.json` from that cache. Nothing reaches down into the VLAN to ask.

The cost, stated rather than hidden: if the outbound link is down, the public open
sign goes stale. It carries `as_of` and past a bound it serves the last known
state marked stale, rather than asserting the lab is closed. A stale sign is
recoverable; a confidently wrong one sends somebody across town.

Interlocks are on the lab LAN rather than the internet, so they reach the door
service directly on the VLAN, with their own firewall rule and one machine
account per device.

### 4.3 It is an API with a controller adapter

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
happens to do. The adapter declares its own limits rather than the domain
hardcoding them:

```python
@dataclass(frozen=True)
class ControllerCapabilities:
    max_slots: int                    # 200, usable ids 10..199
    supports_bulk_write: bool         # False
    supports_per_session_auth: bool   # False. The privilege bit is global.
    supports_event_stream: bool       # False. It is polled.
```

`supports_per_session_auth: False` is what makes the global privilege bit an
adapter problem rather than a system wide one. A replacement controller sets it
true, the serialising lock stops being necessary, and neither the API nor the
domain changes.

Everything hardware specific lives inside `oac_ethernet/` and nowhere else: the
query string format, zero padding to 3 and 8 characters, reading until EOF
because there is no `Content-Length`, the 97 byte request truncation, the always
200 status code, and the 10 to 199 slot range.

Conformance tests run against **every** adapter, fake and real alike. A fake that
has drifted from the hardware is worse than no fake, because the suite is green
and the door is broken.

### 4.4 Physical access never depends on the network

The controller matches cards against its own EEPROM table with no network
involved. Verified in the firmware, not assumed: `processTagAccess` calls
`checkUser`, which reads EEPROM only, and the Ethernet address is static so a
dead switch does not stall boot.

Unplug the network, turn off the host, and cards still open the door. The door
service is a synchroniser and a remote control, never a gatekeeper on the
critical path. If that ever stops being true, physical access starts depending on
the network, and no convenience is worth that.

Two caveats found in the firmware and worth acting on separately: the DS1307 real
time clock is consulted on every logged event over a blocking I2C transaction, so
a dead clock can stall the loop, and permission mask 20 (limited hours) silently
denies cards when the clock battery dies. Check whether any live card carries mask
20, and check the battery.

### 4.5 The reconcile loop cannot cause a lockout

The door service holds its own durable copy of the card table in SQLite, in WAL
mode. This is required, not an optimisation. Without a local baseline there is no
way to distinguish "the API says there are no cards" from "the API is broken",
and that distinction is the difference between a working door and a mass lockout.

- **Idempotent, and this one is a hardware requirement rather than a preference.**
  Read with `?a`, diff, write only differences. A second run writes nothing, and
  that is a test.

  The original plan said "a reconcile loop rewrites the controller card table
  from the database every 15 minutes". That destroys the controller. The firmware
  calls `EEPROM.write` and never `EEPROM.update`, verified by reading it: seven
  calls to the former, zero to the latter. `EEPROM.write` on an AVR writes
  unconditionally, so an unchanged byte still costs a cycle. A full rewrite every
  15 minutes is 96 rewrites a day, 35,040 a year, against a rated endurance of
  100,000 cycles. The card table wears out in **under three years**, and it fails
  as cells that no longer hold a value, which presents as cards that intermittently
  stop working.

  Diffing is what makes the interval safe to choose freely. With a diff, a
  15 minute loop on a table that changes a few times a month writes almost never.
- Never shrink by more than a threshold. If the desired table has two cards and
  the controller has forty, refuse, alert, and change nothing.

  **The guard needs an override, or it becomes its own outage.** A legitimate mass
  revocation, which is exactly what happens after a break in or a lost keyring,
  looks identical to the API returning garbage. Without a way through, the guard
  turns a security response into a wedged sync while the cards it was supposed to
  revoke keep working. The override is an explicit admin action naming the
  expected new count, it is logged with who and why, and it applies once rather
  than disabling the guard.

- **Revocation triggers a sync immediately.** Waiting for the next timer tick
  means a revoked card keeps opening the door for up to the reconcile interval.
  For a routine revocation that is tolerable. For a revocation made because
  somebody's card was stolen it is not, and the system should not make an admin
  wonder which kind they just did. Revoking enqueues a sync; the timer is the
  backstop, not the mechanism.
- Converge, never truncate. Never clear and rewrite: a failure after the clear
  leaves the building locked to everyone.
- Verify by read back, because the controller answers `cur:` for slot writes it
  actually rejected.
- Serialise everything through one lock, and log out in the same request using
  the trailing `&e=` form so a crash cannot leave the controller open.

## 5. Apps and theme

Three static apps: members, admin, door. Phone first, built against the OpenAPI
contract, deployed as files behind Caddy.

The theme ships as three layers, because the consumers do not agree on a
framework and never will:

- **`gantry-tokens`**, the existing hand written CSS custom properties. No build
  step, no token compiler, and a CI validator instead. There are already 1,946
  `var(--*)` references across `new-hsl/src`; the token layer is the integration
  surface and formalising it beats fighting it.
- **`gantry-css`**, a pure CSS component library keyed on data attributes, no
  JavaScript. This is the framework agnostic core and it covers most of what the
  apps need. It drops into Astro, Vue, React 19, Tailwind 4, and Rails ERB
  without any of them agreeing on anything.
- **`gantry-vue`**, a thin wrapper over Reka UI for the handful of components
  that genuinely need interactive accessibility state: dialog, menu, combobox,
  tabs. A React package later, from the same CSS.

Web Components and Lit are rejected as the component model. Custom properties do
cross shadow boundaries, which was the question everyone asks, and that turned out
not to be the blocker. The blockers are the base layer rules that do not cross:
`*:focus-visible` and the `:where(input,textarea,select){font-size:16px}` iOS zoom
guard both fail to reach shadow content, measured in headless Chromium.

Two token defects to fix before any component is built on them, both measured:
the `--ink-*` status family is never remapped by `[data-ground]`, so `--ink-warn`
on a hazard ground is amber on amber at a contrast ratio of 1.00; and
`[data-ground]` remaps variables but paints nothing, so a bare grounded element
looks like the mechanism is broken when it is not.

## 6. Data and access

Covered in `docs/plan/data-model.md`. The three decisions that shape everything:

- A member is not an account. A member may have signed a waiver and never created
  a login, which is already true of paying members today.
- A card is not a slot. `cards.controller_slot` holds the EEPROM address, so the
  2013 hardware's 200 slot ceiling is not the primary key of a table that will
  outlive it.
- Two approval mechanisms, not one. Admin access changes need a second admin,
  which is a **new policy** this project introduces. Card access needs a vote of
  card members at Hack Your Hackerspace, which is the existing bylaws process.

## 7. Backups

The project gate is that a verified, restorable backup of the production members
database exists before any other work begins, and the restore has been proven onto
a staging copy.

`pg_dump -Fc` on a timer, restic to any S3 compatible endpoint, and **a weekly
automated restore drill that fails loudly**. A backup nobody has restored is a
hypothesis.

## 8. What changed from the original plan

| Original | Now | Why |
|---|---|---|
| DigitalOcean droplet | Portable Docker Compose, host undecided | Vendor independence, and the board can pick a host without blocking the build |
| PostgREST, zero application code | One FastAPI service, RLS kept underneath | PostgREST cannot express the approval workflow or produce a designed contract |
| WireGuard or Tailscale tunnel to the lab | No tunnel. Outbound only, door VLAN | Removes a vendor and a class of failure. Costs push based remote unlock |
| Vanilla JS, no framework | Static apps, CSS first theme, Vue only where accessibility state demands it | The consumers are split across four stacks. Only CSS reaches all of them |
| `cards.id` is the EEPROM slot | `controller_slot` is a separate constrained column | Lets the controller be replaced without a data migration |
| "The two admin rule", presented as existing | A new policy, labelled as new. Card access modelled as the real bylaws process | No two admin rule exists in the bylaws. Inventing governance quietly is how a rewrite loses a vote |
| Six months to card eligibility | Two months, read from `governance_parameters` | The membership voted the change; two research passes disagree on the date, so the seed row carries DATE UNCONFIRMED |
| Door service as one Python module | Door API plus a controller adapter and a conformance suite | The Arduino is expected to be replaced. The API should not have to change when it is |
| Secrets in GitHub Environments | SOPS with age in git, GitHub holds no deploy credentials | The system must not require GitHub to run or to be rebuilt |
| Door at phase 4, payments absent | Order is identity, members, admin, door. Payments deferred, schema reserved | Directed. The door gets its adapter and fake built early so it is de-risked before its phase |

## 9. What this is not

- **Not multi tenant.** One lab. `virgilvox/hackerspace-management` is the
  multi tenant design and this is not that.
- **Not a payments system yet.** Deferred by direction. The schema reserves the
  tables so adding it later is not a reshape.
- **Not a replacement for the mailing list.** Governance stays on Google Groups.
  That position was stated clearly in the archive and never withdrawn.
- **Not a CRM.** It holds members, access, and certifications. Donor management,
  volunteer scheduling, and inventory are separate problems that should not be
  absorbed by default.
