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

## How to run it

```sh
make development
```

That starts Caddy, the contract mock and Postgres, and serves this directory at
the root of the hostname in your `.env`. Plain HTTP, on the port in
`ORO_HTTP_PORT`, with no redirect and no certificate to accept. It proxies `/v1`
to the mock on the same origin, and Caddy strips the `/v1` prefix, so the portal
calls the same paths it will call against the real service and no page needs a
second base URL.

The deployment profile is unchanged and still serves TLS.
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
neither read nor disturbed, and runs
`tools/members-portal/tests/check_portal.py` against it. To check a stack you
already have running instead:

```sh
ORO_PORTAL_URL=http://localhost:8080 python3 tools/members-portal/tests/check_portal.py
```

The check runs no browser, so it never sees the rendered document. It asserts
what is either side of that. On one side, the copy and the structure a reader is
served: the sentence saying this is a mock, the skip link, the error copy, and
that no element on the page could be mistaken for something that saves. On the
other, that every field the page binds is a field the contract actually serves at
the endpoint that view reads. That last one is the check this portal exists to
make. A field name the API does not carry renders as nothing, and nothing is what
a member reads as having no cards.

Run the prose gate over any file you change here:

```sh
python3 tools/voice-check/voice_check.py apps/members/
```

## What it depends on

| Thing | Why |
|---|---|
| `docs/api/members-v1.yaml` | The contract. Every field name on every view comes from it |
| `tools/mock/` | Serves that contract. `compose.yaml` runs it in the development profile |
| `packages/gantry-tokens/tokens.css` | The theme. `theme/tokens.css` here is a copy of it, served at `/theme/tokens.css` |
| `caddy/routes/development.caddyfile` | Puts the portal and the mock on one origin |

Nothing else. No runtime dependency, no lockfile, no `node_modules`.

The theme is a copy rather than a mount, which is the one place this portal
holds a second copy of somebody else's file. A compose volume takes no profile,
so a bind from `packages/` into Caddy would belong to every deployment as well
as to the development stack, and Docker creates a directory where the source
should be when the source is not there. That gives a healthy stack serving an
unstyled page, with a directory sitting where a source file belongs. A copy
costs a drift check instead, and `make portal-test` fails when the two files
differ by a byte. To take a new version of the token layer:

```sh
cp packages/gantry-tokens/tokens.css apps/members/theme/tokens.css
```

### How a view is wired

Each view is a `<section>` in `index.html` carrying `data-source`, the path it
reads. Inside it, an element with `data-field` names a path into the record, and
a `<template data-item-for="...">` names a list inside that record. `api.js`
fetches and never touches the DOM. `render.js` writes to the DOM and never
fetches. `main.js` is the only file that does both, which is what a composition
root is for.

Every sentence a reader sees is in `index.html`, including the two error blocks,
which are templates the renderer clones. That is what lets a check with no
browser read the copy.

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

- No light theme. `packages/gantry-tokens` flips on `[data-theme="light"]` and
  nothing here sets it, so the portal is dark.
- No web fonts. That package is the token layer and carries no `@font-face`, so
  the display and mono families fall back to what the machine has.
- A link a member entered is shown as text rather than as a link, because the
  renderer sets text and never an attribute.
