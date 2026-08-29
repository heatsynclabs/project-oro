# Members portal

## What it is

The six self service views a member has of their own record: the record itself,
their cards, their certifications, their waiver, whether they can be nominated
for card access, and the member directory.

It reads the members API contract through a mock. There is no API service and no
database behind it. Every name, card, date and skill it shows is an example out
of `docs/api/members-v1.yaml`, and the page says so at the top where a reader
cannot miss it.

It is read only. There is no sign in, because the identity service is not built,
and the mock takes any bearer token. There is no form and no PATCH, because a
form that appears to save and does not is worse than no form. Both belong to
phase 3, against a real service.

Why it exists before the service does: `docs/plan/api-design.md` section 7 step 2
asks for the portal to be finished against the mock, because a portal that can be
finished is what proves the contract is usable. Note that
`docs/plan/order-of-operations.md` puts the members portal in phase 3, after
identity. The two documents disagree about when this is built. This is the
contract proof, and it is not phase 3 complete.

Plain HTML, CSS and JavaScript. No build step, no bundler, no package manager and
no framework, so there is nothing to install and no dependency to review. Open a
file and read it.

It looks like the ORO mockups because the components came out of them: the card
with its small label and display heading, the label and value grid, the inline
chip, the sheet, and the caution stripe under the masthead. What did not come
out of them is the section "Where this and the mockups differ" below.

## How to run it

```sh
make development
```

That starts Caddy, the contract mock, Postgres and the identity service, and
serves this directory at the root of the hostname in your `.env`. Plain HTTP, on the port in
`ORO_HTTP_PORT`, with no redirect and no certificate to accept. It proxies `/v1`
to the mock on the same origin, and Caddy strips the `/v1` prefix, so the portal
calls the same paths it will call against the real service and no page needs a
second base URL.

The deployment is unchanged and still serves TLS.
`docs/decisions/0003-plain-http-for-development.md` says why the two differ and
what developing over plain HTTP can hide.

Views are addressed by fragment: `#/me`, `#/cards`, `#/certifications`,
`#/waiver`, `#/card-eligibility`, `#/directory`. A fragment rather than a path
because this is a file server: a path route would need a rewrite in Caddy, and
without one a reload of a deep link answers 404.

`make down` stops it.

## How to test it

```sh
make portal-test
```

That brings up its own stack on its own ports, so a stack you already have up is
neither read nor disturbed, and runs two suites against it. To check a stack you
already have running instead:

```sh
ORO_PORTAL_URL=http://localhost:8080 python3 tools/members-portal/tests/check_portal.py
ORO_PORTAL_URL=http://localhost:8080 python3 tools/members-portal/tests/check_appearance.py
```

Neither runs a browser, so neither sees the rendered document. They assert what
is either side of that.

`check_portal.py` is the page against the contract underneath it. The copy and
the structure a reader is served: the sentence saying this is a mock, the skip
link, the error copy, and that no element on the page could be mistaken for
something that saves. Then that every field the page binds is a field the
contract actually serves at the endpoint that view reads. That last one is the
check this portal exists to make. A field name the API does not carry renders as
nothing, and nothing is what a member reads as having no cards.

`check_appearance.py` is the page itself. That the masthead mark is drawn in the
document rather than fetched or typed as an emoji, that the components are still
there, that the view switcher keeps the 44px floor, that no colour is picked by
hand, and that none of the readable text uses the ink measuring below the
contrast minimum. Then one check for each correction in the table below. Split
from the other file because one file holding both runs past the 300 line ceiling
in rule 6.

Run the prose gate over any file you change here:

```sh
python3 tools/voice-check/voice_check.py apps/members/
```

## What it depends on

| Thing | Why |
|---|---|
| `docs/api/members-v1.yaml` | The contract. Every field name on every view comes from it |
| `packages/gantry-tokens` | The theme. Caddy binds the package and the development routes serve it at `/theme`, so there is one copy of it |
| `caddy/routes/development.caddyfile` | Puts the portal and the mock on one origin |

Nothing else. No runtime dependency, no lockfile, no `node_modules`.

Nothing here is a copy of anything. This portal used to ship its own byte
identical `tokens.css` next to a check that failed when the two drifted, which
is a defect and a detector for it where one file does. `make portal-test` fails
if that copy comes back.

### How a view is wired

Each view is a `<section>` in `index.html` carrying `data-source`, the path it
reads. Inside it, an element with `data-field` names a path into the record, and
a `<template data-item-for="...">` names a list inside that record. `api.js`
fetches and never touches the DOM. `render.js` writes to the DOM and never
fetches. `main.js` is the only file that does both, which is what a composition
root is for.

The styling is in two files for the same reason the checks are: one file runs
past the ceiling. `members.css` is the page frame, the masthead down to the foot.
`components.css` is what sits inside a view, and it is the GANTRY component layer
as far as one app needs one. HANDOFF.md section 2 has `packages/gantry-css` as a
later step, and the second app that wants a card is what should move it.

Every sentence a reader sees is in `index.html`, including the two error blocks,
which are templates the renderer clones. That is what lets a check with no
browser read the copy.

### Where this and the mockups differ

The mockups predate decisions this project has already made.
`docs/plan/changes-from-the-original.md` section 4 lists them. Each row below is
a check in `check_appearance.py`, so putting one back turns the suite red.

| The mockup | Here | Why |
|---|---|---|
| Membership card shows a paid status, a last payment date, a stored PayPal method and a button to change it | Standing, and a dues paid through date | Payments are out of scope by direction. Both are set by an admin, and the card says so |
| Door access card shows "Slot 041" | The card, its label, its masked tag and its state | A slot is an EEPROM address on the door controller. The adapter in `db/migrations` exists so that detail stops at the door service, and the word appears nowhere on this page |
| "Grants and revokes need two admins by lab rule" | A cardholder nominates you, the proposal is posted at least two weeks ahead, and card members vote at Hack Your Hackerspace | No two admin rule for cards exists. The wording is from `docs/glossary.md` |
| Certifications show the tool, the date and the instructor | Those, plus expiry, revocation and the reason | A laser and a welder are why |
| No card eligibility anywhere | Its own view | It is the question members actually ask, and `card_eligibility` in `db/migrations/012_close_remaining.sql` answers it |
| App bar carries an avatar, a member's name and a sign out link | A chip reading "Not signed in" | There is no identity service and no sign in. Chrome that names a person nobody authenticated is a lie the page tells before a reader has read a word of it |
| Small text on `--g-ink-3`, and `--g-plate` on the app bar and the sheet | `--g-ink-2`, and the plate ground | `--g-ink-3` measures below the contrast minimum on three of the four grounds, per HANDOFF.md section 7. No token file defines `--g-plate` |

### Things that are true of the mock and will not be true of the service

- It fills every nullable field, so a card comes back active and revoked at the
  same time, and text fields read `string`. The empty and missing paths in
  `render.js` are therefore exercised by nothing here.
- A response holding a member inside a member comes back with the inner one cut
  to `{"$ref": null}`. No view binds a field under one of those.
  `docs/decisions/0002-mock-server.md` says which fields it reaches.
- It reads the contract at startup, so a change to that document needs the mock
  restarted.

### What this does not do yet

- No theme switch. Bare `:root` in `packages/gantry-tokens` carries the paper
  set, so a page naming no theme is light and this one names none. Setting
  `data-theme="dark"` on the `html` element flips it, and every rule in both
  stylesheets is written through the ground tokens so the flip needs nothing
  here. Both were looked at in a browser. Nothing on the page offers the switch.
- No web fonts. That package is the token layer and carries no `@font-face`, so
  the display and mono families fall back to what the machine has.
- A link a member entered is shown as text rather than as a link, because the
  renderer sets text and never an attribute.
