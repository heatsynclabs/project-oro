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
| Card grants through the two admin queue | Card access through `card_proposals`: the real bylaws process | Majority of at least five card members at HYH, posted two weeks ahead, nominator is mentor for six months |
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
  replacing. Card access needs a nomination by a cardholder and a vote of at least
  five card members at Hack Your Hackerspace.
- **Certifications card.** Stands, and gains expiry and revocation, which the
  mockup does not show and which matter for a laser and a welder.
- Worth adding: **card eligibility**. The system knows the date and what is still
  missing, and it answers the question members actually ask.

### Admin portal

- **The approvals queue is doing two different jobs and needs to be two queues.**
  The mockup shows `grant_card` and `revoke_card` in the two admin queue. Card
  access is not a two admin decision, it is a community vote. So: one queue for
  admin role changes, needing a second admin, and one for card proposals, showing
  the posting date, the two week clock, the meeting, the quorum, and the outcome.
  Each labelled with its authority, because they look alike and are not alike.
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

## 5. What the original did not have at all

- A named owner for anything. `people-and-custody.md` exists because the previous
  three rewrites each had a plan and one volunteer.
- A definition of done that somebody else could check. Every phase now has an exit
  criterion with named evidence.
- A driver's seat drill. Once per phase, somebody who did not build it performs
  the core operation from the runbook while the author watches and says nothing.
- A stopping condition. Written now, while it is cheap.
- Working code. The schema, its rules, and 50 database assertions exist and run.
