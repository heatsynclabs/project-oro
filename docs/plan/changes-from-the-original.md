# What changed from the original ORO document

A reader who knows `heatsync-members-door-complete.html` should be able to see
exactly what survived, what changed, and why. This is that list.

The short version: **the shape held, the plumbing changed.** One identity, member
data behind an API with row level security, a small door service at the space,
three static apps, everyone keeps their password. All of that is intact. Most of
the changes come from three places: your directives, evidence from the repositories
and the archive, and defects found by running the design rather than reading it.

---

## 1. Kept, unchanged

- **One identity every app signs into.** Zitadel, at `id.heatsynclabs.org`, with
  its own database. Verified against its own `cmd/defaults.yaml` that it imports
  a Devise bcrypt hash with no fork and no third party JAR.
- **Everyone keeps their password.** Confirmed from the source: `config.pepper` is
  commented out and `config.stretches` is 10, so the stored value is standard
  bcrypt. The original called this the easy case and it was right.
- **Authorization in SQL.** Row level security, enabled and forced. This was the
  best idea in the original document.
- **A small door service at the space.** Python, at the lab, holding the
  controller password.
- **Physical access never depends on the cloud.** Verified in the firmware, not
  assumed: `checkUser` reads EEPROM only, and the Ethernet address is static.
- **The `space_api.json` contract.** Same address, same shape, byte for byte.
- **Rear unlock stays refused**, per the 2018 decision.
- **Caddy**, **GANTRY**, the three apps, and the sign in round trip.

## 2. Changed, and why

| Original | Now | Why |
|---|---|---|
| DigitalOcean droplet | Portable Docker Compose, host undecided | Directed. Also removes every vendor from the critical path |
| PostgREST, "zero application code to rot" | One FastAPI service, RLS kept underneath | PostgREST has no authentication, emits Swagger 2.0 from a schema derived rather than designed contract, and cannot express the approval workflow |
| WireGuard or Tailscale tunnel | No tunnel. Door VLAN, outbound only | Directed. Removes a vendor, a daemon, and a class of failure |
| Vanilla HTML, CSS, JS, no framework | CSS first theme, Vue only where accessibility state demands it | The consumers are split: Astro plus Vue, React 19 plus Tailwind 4, and Rails ERB. Only CSS reaches all of them |
| `cards.id` is the EEPROM slot | `controller_slot` is a separate constrained column | Your adapter instruction made this possible. Stops a 2013 Arduino's 200 slot ceiling being the primary key of a table that outlives it |
| "The two admin rule", presented as an existing lab rule | A new policy, labelled as new, covering admin role changes only | No two admin rule exists in the bylaws, the Rules page, or the legacy app. The two signature rule people remember is about money |
| Card grants through the two admin queue | Card issue is an ordinary admin action; the vote happens at HYH and the system records the outcome | The two approver rule covers admin access, which is what was asked for. Modelling the bylaws vote as a workflow would be building a governance platform |
| Six months to card eligibility | Two months, read from `governance_parameters` | The membership voted the change. The public site is stale |
| Door service as one Python module | Door API, a controller port, an adapter, and a conformance suite | Directed. The Arduino is expected to be replaced; the API should not change when it is |
| Secrets in GitHub Environments | SOPS with age in git, GitHub holds no deploy credentials | The system must not need GitHub to run or to be rebuilt |
| "Rewrites the controller card table every 15 minutes" | Read, diff, write only differences | The firmware calls `EEPROM.write` and never `EEPROM.update`. A blind rewrite every 15 minutes exhausts the rated 100,000 cycles in under three years |
| Two Postgres instances | One server, two databases | Halves what has to be backed up, upgraded, and monitored, for a threat model where reaching the host already lost the argument |
| Door at phase 4 | Door at phase 5, but its port, fake, and conformance suite built in phase 1 | Three rewrites stalled at the door. The riskiest unknown gets retired first even though it ships last |
| Payments implied throughout | Explicitly out of scope, schema reserved | Directed |
| Quorum and notice as `CHECK` constraints | `governance_parameters` plus a trigger | The card rules changed three times in eight months. Each would otherwise be a developer writing a migration |

## 3. Defects in the original that would have shipped

Each was found by reading the source or by running the design.

1. **The reconcile loop destroys the controller.** Section 2 above.
2. **Slot 200 corrupts the alarm state.** The plan says a 200 user ceiling and
   "the lowest free card id below 200". The firmware's bounds check is `>` not
   `>=`, so 200 passes, and its offset wraps through the AVR's 10 bit address
   register onto the persisted alarm bytes. Assignable range is 10 to 199.
3. **Privileged mode is one global boolean, not a session.** The plan treats
   `?e=PASS` then commands then `?e=0000` as a session. While that bit is set,
   anything on the network is privileged, and a crash mid sequence leaves it set.
4. **`space_api.json` cannot grow.** The ESP8266 in the wall parses it with a
   1 KB buffer and the document is already about 900 bytes. A SpaceAPI v14
   upgrade overflows it, and the device does not error, it silently stops
   updating.
5. **The two admin rule does not exist.** Building it as described would have
   encoded a governance rule nobody voted on.

## 4. The mockups: what still stands, and what needs redrawing

The mockups are good and most of them survive. These are the screens that need to
change, with the reason.

### Members portal

- **Profile card.** Stands.
- **Membership card.** "Status Paid", "Last payment Aug 12", "On file PayPal,
  monthly", and "Update payment method" all assume payments are in scope. They
  are not. Standing shows, set by hand, and the payment method control comes out
  until payments are built.
- **Door access card.** Shows "Slot 041". The slot is now an adapter detail, and
  putting an EEPROM address in front of a member is exactly the hardware leak the
  adapter exists to prevent. Show the card and its state; the tag is masked to the
  last four.
- **The line "Grants and revokes need two admins by lab rule" is wrong** and needs
  replacing. Card access is decided by a vote of card members at Hack Your
  Hackerspace, not by two admins.
- **Certifications card.** Stands, and gains expiry and revocation, which the
  mockup does not show and which matter for a laser and a welder.
- Worth adding: **card eligibility**. The system knows the date and what is still
  missing, and it answers the question members actually ask.

### Admin portal

- **The approvals queue holds admin access changes only.** The mockup shows
  `grant_card` and `revoke_card` in it. Card access is not a two admin decision,
  it is a vote of card members at Hack Your Hackerspace, so issuing a card is an
  ordinary admin action with a note recording the vote. The queue keeps its
  second admin requirement for role changes, which is what it is for.
- **Members directory.** Stands. The "Level" column becomes the tier name.
- **Member detail.** Stands. "Propose role change" is right. "Propose card grant"
  becomes "Nominate for card access", and the UI says what that commits the
  nominator to: they are the mentor and responsible party for six months.

### Door app

- **Status and controls.** Stand.
- **Rear unlock disabled.** Stands, and improves: it is now data with a reason
  attached rather than a hardcoded refusal, so the day the lab changes its mind is
  a configuration change.
- **Actions are asynchronous now.** The mockup implies a synchronous result. A
  command returns 202 with a status resource, so the button needs a pending state
  that resolves. This is what lets the same contract work whether the members API
  is on the lab network or somewhere else.
- **Recent remote actions.** Stands.

### Sign in and OAuth

Unchanged. Three Zitadel hosted screens wearing the lab brand, and every future
app reuses them.

## 4a. The original's 22 steps, and where each one went

Nothing was dropped silently. Every step in the original "Step by step" section
maps to something here, is deliberately rejected with a reason, or is out of
scope by direction.

| # | Original step | Here | Note |
|---|---|---|---|
| 1 | Verified backup, prove it restores | Phase 0 | Unchanged, still the hard gate before anything |
| 2 | Repo, two GitHub environments, secrets, deploy via Actions | Phase 0 | Changed. Secrets are SOPS with age in git; GitHub runs tests and never holds deploy credentials |
| 3 | Stand up the droplet, join the tailnet, point DNS | Phase 0 | Changed. No droplet and no tunnel. DNS survives as its own step |
| 4 | Decide where member PII and signed waivers live | Answered | Waivers stay where the lab already keeps them and this system stores a reference. The remaining PII question is a migration blocker with an owner |
| 5 | Zitadel and its Postgres behind Caddy | Phase 2 | Kept. One Postgres server, two databases |
| 6 | Register three PKCE clients, the machine account, audiences | Phase 2 | Kept |
| 7 | Token lifetimes: ten minute access, rotating refresh | Phase 2 | Kept |
| 8 | Resolve duplicate emails on staging, export | Phase 0 and the migration blockers | Kept |
| 9 | Import users into Zitadel, subjects back onto member rows | Phase 2 | Kept |
| 10 | A cohort of real members signs in on staging | Phase 2 exit | Improved. Split into synthetic accounts for the mechanism and volunteers for reality, because the original criterion needed plaintext nobody has |
| 11 | Apply the migrations: identity, approvals, policies | **Built** | The schema, its rules and its policies exist and run |
| 12 | Add PostgREST | Rejected | It has no authentication, emits a schema derived contract, and makes the layering rule structurally false. RLS, the good half, is kept |
| 13 | Prove isolation across member, admin, anonymous | **Built** | 31 policy assertions, including the anonymous case |
| 14 | Self hosted runner at the space, reviewer gated | Removed | Followed from dropping GitHub deploys. The door service runs on the VLAN and accepts nothing inbound |
| 15 | Deploy the door service, verify a sync round trip | Phase 5 | Kept, plus a read only week first |
| 16 | Serve `/status`, prove `space_api` parity byte for byte | Phase 5 | Kept, plus a 900 byte ceiling the original did not know about |
| 17 | Members portal: profile, membership, cards, payment method | Phase 3 | Payment method out of scope. Gained certifications, waiver status, card eligibility, and self service profile editing |
| 18 | Admin portal: member list, roles, approvals queue | Phase 4 | Kept. The queue covers admin access changes only |
| 19 | Door app: status and controls | Phase 5 | Kept. Actions are asynchronous, so controls resolve from a pending state |
| 20 | Flip Caddy, route `space_api.json` | Phase 6 | Kept |
| 21 | Rails read only for a week, then decommission | Phase 6 | Two weeks, and card management is frozen earlier, at the moment writes are enabled |
| 22 | Drop dead credential columns, confirm the door ran | Phase 6 | Kept |

### Steps this plan adds

- **Post the two approver proposal at the start of phase 1**, three phases before
  the code that depends on it, so the vote arrives before the work.
- **Build the door controller port, its fake, and its conformance suite in phase
  1.** The door ships last and gets de-risked first, because that is where three
  rewrites stalled.
- **Freeze card management in the legacy app before enabling reconcile writes.**
  The original left both systems writing, which silently un-revokes cards.
- **A driver's seat drill per phase.** Somebody who did not build it runs the
  core operation from the runbook while the author watches and says nothing.
- **Named people as a gate.** A phase does not start while the roles it needs are
  empty.
- **Fix the two measured token defects** before any component is built on them.

## 5. What the original did not have at all

- A named owner for anything. `people-and-custody.md` exists because the previous
  three rewrites each had a plan and one volunteer.
- A definition of done that somebody else could check. Every phase now has an exit
  criterion with named evidence.
- A driver's seat drill. Once per phase, somebody who did not build it performs
  the core operation from the runbook while the author watches and says nothing.
- A stopping condition. Written now, while it is cheap.
- Working code. The schema, its rules, and 50 database assertions exist and run.
