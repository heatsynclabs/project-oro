# ADR 0003: Plain HTTP for the development profile

- **Status:** accepted
- **Date:** 2026-08-28
- **Deciders:** TBD. The same gap ADR 0001 and ADR 0002 record.
  `people-and-custody.md` has no names in it, and by the rule in that file this
  ADR is not decided until one is written here. It is recorded as accepted
  because the change is built and `make development-test` passes against it.

## Context

The development profile was brought up and pointed at a real Chrome, and the
page could not be opened. Caddy served it over HTTPS with `tls internal`, so the
certificate came from `CN=Caddy Local Authority - ECC Intermediate`, read off a
running stack with `curl -skv https://localhost:8443/health`. Chrome answers
that with its certificate interstitial. That interstitial is a privileged page,
so no browser automation can click through it, and a volunteer gets past it only
by running `caddy trust` as an administrator and installing a root certificate
into the machine they own. Asking for that before somebody can read a local page
is a real cost, paid by every person who clones this repository.

A second defect sat next to it. With `ORO_HTTP_PORT=8080`,
`curl -i http://localhost:8080/` answered `308` to `https://localhost/`, with no
port, because Caddy cannot see the host side of a published port. The plain HTTP
route therefore landed on a closed port. `.env.example` warns about that in
prose.

## Options considered

Each was checked against the running stack on this machine rather than reasoned
about.

### Option A: keep TLS, and document `caddy trust`

- **What it costs:** an administrator password and a root certificate installed
  into the trust store of a machine the lab does not own, before a volunteer can
  read a page served from their own loopback interface. It also has to be undone
  later by somebody who remembers it is there.
- **What it buys:** the development stack matches the deployment on scheme.
- **Checked:** the interstitial is what a browser shows for this authority, and
  it cannot be clicked through by automation, which is what started this.

### Option B: plain HTTP for the development profile only

- **What it costs:** the two profiles now differ on scheme, so a defect that
  only appears under TLS is not seen on a laptop. Stated in full below.
- **What it buys:** clone, `make development`, open the page. Nothing installed,
  nothing trusted, no interstitial, and no redirect to a port that is closed.
- **Checked:** `tools/development/tests/run.sh` calls the root, `/health` and
  `/v1/me` over plain HTTP and asserts no redirect anywhere.

### Option C: a certificate for `localhost` from `mkcert`

- **Last release:** not checked, and the option did not survive far enough to
  need it.
- **What it costs:** a new tool every volunteer installs, and it still writes a
  root certificate into the machine's trust store, which is the cost Option A
  was rejected for. Rule 11 of the working rules also has this project taking on
  no new dependency it does not need.
- **What it buys:** a browser that opens the page without an interstitial, with
  the scheme matching the deployment.

## Decision

We chose **Option B, plain HTTP for the development profile only**.

Option A was eliminated by what it asks of a person: an administrator password
and a permanent change to a machine the project does not own, to read a page on
loopback. Option C asks for the same change to the trust store and adds a tool
to install first, so it buys the scheme back at a higher price than Option A.

Loopback development traffic gets nothing from TLS here. There is no network to
eavesdrop on, the mock serves invented records, and there is no sign in and no
session to steal. The deployment is where TLS earns its place, and the
deployment keeps it unchanged.

The runner up is Option A. If the portal ever grows a real sign in against the
identity service on a developer's machine, the balance moves, because then there
is a session cookie on that origin and a reason to want it treated the way the
deployment treats it.

## The condition that would flip this

If anything in `apps/` starts holding a credential or a session on the
development origin, this is wrong and Option A becomes correct. Concretely: the
first time a development page sets a cookie, or the first time a portal talks to
Zitadel rather than to the mock.

## Consequences

**What this trades away, and it is the whole cost.** Developing against plain
HTTP hides any defect that only appears under TLS. A cookie marked `Secure` is
never sent on a plain HTTP origin, so a session that works on a laptop can fail
in production and the other way round. Mixed content, where a page loaded over
HTTPS pulls a subresource over HTTP, cannot happen on a development origin that
is entirely HTTP, so a hardcoded `http://` URL in a page passes every local
check and is blocked by the browser on the deployment. Anything that reads
`window.isSecureContext`, and every browser API gated behind it, behaves
differently on the two. None of that is theoretical, and none of it is caught by
the checks in this repository, because they call the stack with `curl` rather
than with a browser. The guard is to test a change like that against the
deployment profile before it ships, not to trust a green development run.

**What gets easier.** Clone, `.env`, `make development`, open the page. A real
browser opens it and browser automation can drive it, which is what
`apps/members/README.md` says the existing checks cannot do.

**What is unchanged.** The deployment. `make up` serves the hostname over TLS
with the certificate `ORO_TLS` asks for, answers `/health`, and still sends a
request on the HTTP port to HTTPS with a `308`.
`tools/development/tests/run.sh` asserts each of those, including reading the
certificate issuer, so a later edit that quietly moves the deployment onto plain
HTTP fails a check.

**What we now have to operate.** Nothing new. No dependency was added and no
variable was added. `caddy/routes/development.caddyfile` opens an `http://` site
and `caddy/routes/deployment.caddyfile` opens the TLS one, and `ORO_ROUTES`
still chooses between them out of `COMPOSE_PROFILES`.

**The shape of the Caddy configuration had to change with it.** A site address
written `http://` cannot carry a `tls` directive, and a file imported inside a
site block cannot open a site of its own, so the route files now own their whole
site block and `caddy/Caddyfile` imports one of them at the top level. That file
records the two arrangements weighed against it. The health route is written out
in both files, and the development checks call it under both profiles so a drift
between them fails rather than passing quietly.

**Reversing this** costs an hour. Put `https://` back on the site address in
`caddy/routes/development.caddyfile`, give it `tls {$ORO_TLS}`, and move the
checks in `tools/development/tests/run.sh` back onto the HTTPS port. Nothing
outside `caddy/routes/` and the two test runners depends on the scheme.

## What was borrowed

Nothing.

## Open questions

* The port dropping redirect is untouched. On a deployment holding 80 and 443 it
  is correct, and on any other port it names a port nobody is listening on.
  Fixing it means telling Caddy the published port, which it cannot see, so it
  would take a new variable that has to agree with `ORO_HTTPS_PORT`. Left as it
  is, warned about in `.env.example`, and now unnecessary for development because
  that profile does not redirect at all.
