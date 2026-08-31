# Browser checks

## What it is

One check that opens the members portal in a real chromium, lets the page's own
script run, and asserts on what a person would see. It writes a screenshot of
the page every time, red or green.

The last of its four assertions is the one worth reading. It fetches the same
address a second time from inside the page, and every view in what comes back
has to still be carrying the `hidden` attribute. So the check says the document
arrives with nothing on screen while the browser puts one view on screen, which
is the difference between the two suites written as an assertion rather than as
a paragraph.

What it deliberately does not assert is whether the first view's request
answered. A signed out visitor gets a panel saying so, that panel is the
portal's own design, and whether anything answers the members API on this
origin is what `make mock-test` and `make api-test` are for.

Nothing else here drives a browser. `tools/members-portal/tests/` reads the
document Caddy serves, which is the right trade for most of what that suite
asserts and cannot reach the rendered page at all: every view in
`apps/members/index.html` arrives with the `hidden` attribute on it, and
`apps/members/main.js` picks one and `apps/members/render.js` fills it in after
a request answers. The served document has six hidden sections and no member
data in it.

One check rather than a suite, on purpose. The service that will replace the
contract mock is being wired now, so a suite of portal assertions written today
would be written against something about to move. What this proves is that the
harness drives a browser, takes a picture, and goes red when the page is wrong.

`docs/decisions/0015-a-browser-driver.md` records why the driver is Playwright
and what was priced against it.

## How to run it

It checks a stack that is already up, and it starts nothing:

```sh
make development                  # if the portal is not already running
./tools/browser-checks/run.sh
```

```
Driving http://localhost:8080 with chromium. Screenshots land in /Users/you/oro-screenshots

Screenshot: /Users/you/oro-screenshots/first-view.png

1/1 browser checks passed
```

Two settings, both optional:

| Variable | Default | What it is |
|---|---|---|
| `ORO_PORTAL_URL` | `http://localhost:8080` | Where the portal is. A laptop serves plain HTTP on `ORO_HTTP_PORT`, so this carries the port your own `.env` chose |
| `ORO_SHOT_DIR` | `$HOME/oro-screenshots` | Where the screenshots land. A path inside this repository is refused, because every suite here leaves the working tree as it found it |

The first run builds the image, which pulls about a gigabyte. Runs after that
reuse it.

## How to test it

There is no self test suite here yet, and that is worth saying plainly rather
than implying otherwise. `tools/ceilings/` and `tools/import-boundaries/` each
plant a violation in a throwaway tree and require the gate to catch it. This one
is checked by hand. Two ways, both run on 2026-08-30.

Point it at a port nothing serves:

```
$ ORO_PORTAL_URL=http://localhost:8099 ./tools/browser-checks/run.sh
Driving http://localhost:8099 with chromium. Screenshots land in /Users/you/oro-screenshots

ERROR test_the_first_view_renders_for_a_person
        Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:8099/
Call log:
  - navigating to "http://localhost:8099/", waiting until "networkidle"


0/1 browser checks passed
```

Then ask the page for a heading it does not carry. With `reads("Your record")`
in `check_first_view.py` changed to `reads("Your door log")`:

```
$ ./tools/browser-checks/run.sh
Driving http://localhost:8080 with chromium. Screenshots land in /Users/you/oro-screenshots

Screenshot: /Users/you/oro-screenshots/first-view.png
FAIL  test_the_first_view_renders_for_a_person
        The first view is headed 'YOUR RECORD' rather than 'Your door log'.

0/1 browser checks passed
```

Both exit 1. The second one still wrote the screenshot, which is the behaviour
worth keeping: a browser check that goes red with no picture sends the reader
back to reproduce it by hand.

That second failure also shows what a browser buys. The heading in the document
says `Your record`. What comes back through chromium is `YOUR RECORD`, because
`h2` in `apps/members/members.css` carries `text-transform: uppercase`. The
check folds case and says why it has to.

## What it depends on

Docker, and nothing installed on your machine.

`mcr.microsoft.com/playwright/python:v1.62.0-noble`, pinned by digest, brings
Ubuntu 24.04, the chromium, firefox and webkit builds that playwright release
was pinned to, and the shared libraries they need. It deliberately ships no
Python package: the build step that installs one ends by deleting the virtual
environment it used. So `Dockerfile` here installs `playwright` 1.62.0 from
`requirements.txt`, which is a lock with a hash per wheel, the same mechanism
`services/api` and `tools/import-boundaries` use.

`requirements.in` names the one package. Regenerate the lock the way ADR 0012
does, with the command written at the top of `requirements.txt`.

The version in `requirements.in` has to be the version in the image tag. The
base image holds one browser build per browser, named for the playwright release
that pinned it, and a driver of another version goes looking for a build that is
not in the image.

## The one thing that is not obvious

The browser runs in a container and the portal runs on the machine that started
it, so the check has to get out of the container and arrive at Caddy with the
right `Host` header on it. Two obvious routes were run on 2026-08-30 and neither
works.

`--add-host localhost:host-gateway` does nothing: chromium resolves the name
`localhost` to its own loopback and never reads `/etc/hosts` for it, so the page
fails on `ERR_CONNECTION_REFUSED`. Docker's own `host.docker.internal` resolves
fine, but the development route file addresses its site block
`http://{$ORO_HOSTNAME}`, so a request under any other name gets an empty 200
from Caddy rather than the portal.

What works is a chromium resolver rule, `--host-resolver-rules=MAP localhost
<gateway>`, which sends the connection to the host while the request still
carries `Host: localhost`. `harness.py` builds it, and it applies only when the
address is `localhost`. A URL written `http://127.0.0.1:8080` is refused with a
sentence saying to use the name instead, because an address never reaches the
resolver and no rule can redirect it.
