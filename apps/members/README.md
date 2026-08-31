# Members portal

## What it is

The six self service views a member has of their own record: the record itself,
their cards, their certifications, their waiver, whether they can be nominated
for card access, and the member directory.

A member signs in to it, and what it shows is their own record. The sign in is
an authorization code flow with PKCE against the identity service, and every
call it makes carries an access token that service issued.

It says at the top where the records came from, and it works that out rather
than being told: it calls the members API once with a token nothing issued, and
anything that answers 200 to that is checking no tokens, which makes it the
contract mock. So the sentence about invented data disappears on the day a real
service takes that prefix, without anybody remembering to edit it.

It reads. The one thing it writes is `POST /me` on a first sign in, for a
person the identity service knows and the members database does not. There is
no form and no field anywhere on the page: the name and address that operation
needs come from the identity service, which the person has just proved
themselves to. A PATCH belongs to a later step.

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

## The mark

The masthead carries `hsl-mark-current.svg` and `hsl-wordmark-current.svg` from
`heatsync-brand/assets/logos` in the hsl-forge brand skill package, which is
internal HeatSync Labs work product and the same package
`packages/gantry-tokens/tokens.css` is taken from. sha256
`e8bb9cc8edf7ebd31ebdfd28488602a94a1d339308251271a5dcf35079111152` and
`0a531347ca539e35afd9289037a131a91810202000948db078dd34b2efe662fa`.

Three things from that package's `references/logos.md` decided how they are used
here, and each one has a check behind it in
`tools/members-portal/tests/check_appearance.py`.

**The mark is two pieces in two colours.** The sun disc keeps the logo orange,
`#F99A1C`, and the flames and the sync arrow take `currentColor`. Filling the
disc with the flame colour makes a shape that is no longer the HeatSync mark,
and `hsl-mark-current.svg` exists so that cannot happen whatever colour a page
sets. That document also says do not redraw or simplify the flames, which is
what an earlier version of this portal did with a sun drawn from scratch.

**The wordmark is Charis SIL 700, outlined.** It depends on no font being
installed, which matters because this portal ships no font files. Setting it in
any other face is named as misuse.

**Both keep their packaged width and height.** Stripping them to size with CSS
alone leaves the element with no intrinsic aspect ratio, and an SVG with no
ratio in a flex row falls back to the full width of that row. That is what the
wordmark did until the attributes went back. Only the accessible name was
changed: the mark is `aria-hidden`, the wordmark keeps the packaged label, so a
screen reader announces the lab once rather than twice.

The sizes are the lockup proportion that document measures off the live site,
34px of mark against a 23px cap height.

## How to run it

```sh
make development
```

That starts Caddy, the members API, Postgres, the contract mock and the identity
service, and serves this directory at the root of the hostname in your `.env`.
Plain HTTP, on the port in `ORO_HTTP_PORT`, with no redirect and no certificate
to accept. Caddy proxies `/v1` on that same origin and strips the prefix, so the
portal calls one set of paths and no page names a host.

Signing in needs one more step, once per stack:

```sh
ORO_IDENTITY_URL=http://localhost:8180 \
ORO_IDENTITY_TOKEN="$(docker compose cp identity:/bootstrap/pat - | tar -xO)" \
python3 tools/identity/configure.py \
  --members-origin http://localhost:8080 \
  --admin-origin http://localhost:8081 \
  --door-origin http://localhost:8082
```

That registers the clients and writes `identity.json` beside this file, carrying
the client id the identity service generated. Until it has been run, the band
under the masthead says signing in is not set up here and names that command.
`make identity-configure` is the same step with a deployment's addresses in it,
which is not what a laptop serves.

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
neither read nor disturbed, and runs three suites against it. To check a stack
you already have running instead:

```sh
ORO_PORTAL_URL=http://localhost:8080 ORO_MOCK_URL=http://localhost:4010 \
  python3 tools/members-portal/tests/check_portal.py
```

The same two variables run `check_appearance.py` and `check_sign_in.py`. None of
the three runs a browser, so none of them sees the rendered document. They assert
what is either side of that.

`check_portal.py` is the page against the contract underneath it. The copy and
the structure a reader is served: the skip link, the error copy, and the heading
order. Then that every field the page binds is a field the contract actually
serves at the endpoint that view reads. That last one is the check this portal
exists to make. A field name the API does not carry renders as nothing, and
nothing is what a member reads as having no cards. It asks the contract mock
that question, on the mock's own port: the mock is the contract, and the members
API refuses every call a suite with no browser could make.

`check_appearance.py` is the page itself. That the masthead mark is drawn in the
document rather than fetched or typed as an emoji, that the components are still
there, that every control keeps the 44px floor, that no colour is picked by
hand, and that none of the readable text uses the ink measuring below the
contrast minimum. Then one check for each correction in the table below.

`check_sign_in.py` is what the page does about signing in. That the controls are
there and a keyboard reaches them, that nothing the server sends carries a token
or a client id, that the band claims nothing the page has not measured, and that
the block a first sign in gets offers the operation the contract declares. It
makes the same measurement of what is behind `/v1` that the page makes, reading
the probe token out of `api.js` so the two cannot disagree.

Three files rather than one because one file holding them runs past the 300 line
ceiling in rule 6.

Run the prose gate over any file you change here:

```sh
python3 tools/voice-check/voice_check.py apps/members/
```

## Signing in

Authorization code with PKCE, against the client `tools/identity/configure.py`
registers as "Members portal". That client is public and holds no secret: a
secret shipped inside a page a browser downloads is not a secret, and PKCE
stands in for one.

**The client id cannot live in this repository.** The identity service generates
one per instance, so a portal carrying one would work on exactly the deployment
it was written for. `configure.py` writes `identity.json` into this directory
when it registers the client, because that step is the only thing that knows the
value at the moment it exists, and Caddy already serves this directory. The file
is gitignored. The portal reads it, then reads the identity service's own
discovery document for every endpoint, so no path is written down here either.

Three ways that can be wrong, and each is a sentence in the band rather than a
button that does nothing: the document is not there, it registers an address
other than the one the page is being read on, or the browser does not treat this
origin as secure and there is no `crypto.subtle` to build the challenge with.
The last one is real on a laptop: plain HTTP is a secure context on `localhost`
and on nothing else.

**Running the identity test suite repoints this file.**
`tools/identity/tests/run.sh` calls `configure.py` against a throwaway identity
service on port 8184, which dies with the suite. The portal then finds nothing
at the address in `identity.json` and says so. Run `configure.py` again.

### Where the tokens are, and what that exposes

In `sessionStorage`, and the trade is written out in the header of
`session.js`. What it buys: the tokens belong to one browser tab and are gone
when the tab closes, which is what matters on a machine several members use.
What it costs: anything that can run JavaScript on this origin can read them,
and could use them from somewhere else until the refresh token is next rotated.
This page loads no third party script and fetches nothing from another origin,
which is what keeps that narrow.

An access token lasts ten minutes. Every call asks for one, and asking is what
renews it, so a member reading down a long page is not thrown out between one
view and the next. The refresh token rotates, so two views renewing at the same
moment would spend one token twice and the second would be refused: every caller
waits on the one renewal already running.

Signing out drops the tokens here and then sends the browser to the identity
service to end the session there too. Without the second half, the next person
at that machine signs in with one click and no password.

### A first sign in

A person the identity service knows and the members database does not is refused
by every view, with `no-member-record`. The portal shows that refusal with the
one control that fixes it, which sends `POST /me`. The name and the address in
that request come from the identity service, which the person has just proved
themselves to, so there is no field to type into and nothing to get wrong.

`members.email` is unique, so a member whose record the lab already holds is
refused by the database and told an admin joins them to it. Sending no address
would have written them a second, empty record instead.

## Two things measured by driving it in a browser

**Every sign in asks who is signing in.** `identity.js` sends
`prompt=select_account` on the authorize request. Without it the identity service
reuses whatever user agent session the browser already has. Measured on
2026-08-31 against Zitadel 4.17.1: with no prompt, every sign in from this page
landed on the initial administrator's Activate User screen, the back arrow
restarted the same screen, and signing out at `/ui/login/logout` did not clear
it. With `select_account` the same request answers Select Account, listing the
signed in people and an Other User row that reaches the login name screen. A lab
has shared machines in it, so this is the ordinary case rather than the edge.

**Nothing here declares a top level name twice.** These are classic scripts
sharing one global scope, which is what keeps a lockfile and a hundred packages
out of this tree, and the cost is that two files declaring the same top level
name silently pick a winner by load order. It happened: `render.js` had a value
formatter called `present` and `main.js` has the function that decides what to
draw, also called `present`. `main.js` loads later, so `render.js` called the
wrong one and threw on the refusal path, which is the path every new member
takes. The formatter is `formatted` now. Before adding a top level function
here, grep the other files for its name.

## What it depends on

| Thing | Why |
|---|---|
| `docs/api/members-v1.yaml` | The contract. Every field name on every view comes from it |
| The identity service | Every access token. `identity.json` beside this file says which one and as which client |
| `packages/gantry-tokens` | The theme. Caddy binds the package and the development routes serve it at `/theme`, so there is one copy of it |
| `caddy/routes/development.caddyfile` | Puts the portal, the members API and the theme on one origin |

Nothing else. No runtime dependency, no lockfile, no `node_modules`.

Nothing here is a copy of anything. This portal used to ship its own byte
identical `tokens.css` next to a check that failed when the two drifted, which
is a defect and a detector for it where one file does. `make portal-test` fails
if that copy comes back.

### How a view is wired

Each view is a `<section>` in `index.html` carrying `data-source`, the path it
reads. Inside it, an element with `data-field` names a path into the record, and
a `<template data-item-for="...">` names a list inside that record. `api.js`
fetches and never touches the DOM. `identity.js` talks to the identity service
and never touches the DOM either, and `session.js` under it holds what comes
back and calls nothing. `render.js` writes to the DOM and never fetches.
`main.js` is the only file that does both, which is what a composition root is
for.

Five files rather than three because each ran past the 300 line ceiling in rule
6 as one. There is no `import` statement anywhere in this tree, deliberately:
ADR 0006 makes the first one the condition that brings `eslint-plugin-boundaries`
in, and with it a lockfile and a hundred packages. These are classic scripts and
the load order in `index.html` is what puts each global in place before the
next file uses it.

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
| App bar carries an avatar, a member's name and a sign out link | A chip carrying whoever is signed in, a sign in control, and a sign out control | Two of the three arrived with the sign in. The avatar did not: nothing in this system holds a picture of anybody |
| Small text on `--g-ink-3`, and `--g-plate` on the app bar and the sheet | `--g-ink-2`, and the plate ground | `--g-ink-3` measures below the contrast minimum on three of the four grounds, per HANDOFF.md section 7. No token file defines `--g-plate` |

### Things that are true of the mock and are not true of the service

The mock no longer has `/v1`. It still runs, still answers on `ORO_MOCK_PORT`,
and is still what `check_portal.py` asks about the contract, so these still
matter to anybody reading that suite.

- It fills every nullable field, so a card comes back active and revoked at the
  same time, and text fields read `string`. The real service sends nulls, and
  the empty and missing paths in `render.js` are what a member actually meets.
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
- Nothing here has been driven through a browser by a check. The flow was run
  end to end without one on 2026-08-30, through the real hosted screens with
  `tools/identity/flow.py` and against the real members API: a fixture member
  signed in, `GET /me` refused with `no-member-record`, `POST /me` answered 201,
  the other five views answered, and a refresh rotated the token and left the
  old one refused. What that run cannot cover is the part only a browser does:
  the redirect back carrying the code, `crypto.subtle` building the challenge,
  and `sessionStorage`. `tools/browser-checks/` is where that belongs.
- No silent renewal across a closed tab. `sessionStorage` goes with the tab, so
  a member who closes it signs in again. The identity service still holds the
  session, so that is one click rather than a password.
