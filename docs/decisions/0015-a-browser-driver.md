# ADR 0015: a browser driver for the portal checks

- **Status:** accepted
- **Date:** 2026-08-30
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in it yet, and this record is not complete until a build lead signs it.

## Context

Nothing in this repository has ever driven a browser. `tools/members-portal/tests/`
says so in its own header: it runs the portal through Caddy with curl and
python3, so it reads what the served document says and cannot see what a person
sees. That has been the right trade, and it has a hard edge. Every view in
`apps/members/index.html` arrives carrying the `hidden` attribute,
`apps/members/main.js` chooses one and unhides it, and `apps/members/render.js`
fills it in after a request answers, so the document that suite reads has six
hidden sections and no member data in it.

The build lead asked for end to end checks through a real browser, which makes
the driver a decision rather than a detail.

The constraint that decides it is in `README.md` and holds for every other
suite here: a person runs the checks with Docker and python3, and installs
nothing on their own machine. Two shapes already satisfy it.
`tools/ceilings/run.sh` pins a published image by digest. `tools/import-boundaries/`
builds one, because nobody publishes an import-linter image.

## Options considered

Every version, date, licence, issue count and digest below was read on
2026-08-30 from `https://registry.npmjs.org/<name>`, from
`https://pypi.org/pypi/<name>/json`, from the GitHub API, or from the registry
with `docker buildx imagetools inspect`. Every size and timing was measured on
this laptop, an arm64 macOS 12 machine running Docker 28.0.4.

One number needs a caveat wherever it appears. The contributor counts come from
paging the GitHub contributors listing with `per_page=1` and reading the last
page number out of the `Link` header, and that listing stops at 500. All four
projects here are well inside the hundreds, so what the count says is that no
one of them is a single maintainer.

### Option A: Playwright

- **Last release:** `playwright` 1.62.1 on npm, 2026-07-30. `playwright` 1.62.0
  on PyPI, uploaded 2026-07-31.
- **Licence:** Apache-2.0, from both registries.
- **Maintainers:** Microsoft. `microsoft/playwright` has 148 open issues and the
  contributors listing pages to 472. Five publishing accounts on npm.
- **How it arrives:** `mcr.microsoft.com/playwright/python:v1.62.0-noble`, index
  digest `sha256:aa81288e...`, carrying linux/amd64 and linux/arm64. Ubuntu
  24.04 with the chromium, firefox and webkit builds that release pins, plus
  every shared library they need.
- **Fit:** one container holds the browser and the thing that drives it. The
  Python API is synchronous, which is the same shape the rest of the checks here
  are written in. `wait_until="networkidle"` is a first class wait, and the
  portal is a page that fetches after load, so that wait is the whole difference
  between a check and a race.
- **Cost:** the image is large. 4 minutes 18 seconds to pull on this laptop,
  3.77 GB on disk after it lands and 3.97 GB once the driver is installed into
  it. And the base image ships no Python package at all, which is not what its
  name suggests: measured by running `pip list` in it, which names six packages
  and none of them playwright. The build step that installed one ends
  `rm -rf /ms-playwright-agent`, throwing away the virtual environment it used.
  So a Dockerfile and a lock are needed here anyway.

### Option B: Selenium

- **Last release:** `selenium` 4.48.0 on PyPI, 2026-08-27. `selenium-webdriver`
  4.48.0 on npm the same day.
- **Licence:** Apache-2.0, from both registries.
- **Maintainers:** the Selenium project. `SeleniumHQ/selenium` has 99 open
  issues, the fewest of the four, and the contributors listing pages to 406.
  Six publishing accounts on npm, the most of the four.
- **How it arrives:** `selenium/standalone-chromium:143.0`, index digest
  `sha256:8745c650...`, linux/amd64 and linux/arm64, 0.92 GB of compressed
  layers on arm64.
- **Fit:** the only one of the four whose wire protocol is a specification
  somebody else owns. `https://www.w3.org/TR/webdriver2/` is a W3C Working
  Draft dated 2026-07-02, read on 2026-08-30, so a check written against it
  outlives any one project. Multi architecture, and the client library is
  Python.
- **Cost:** it is two pieces rather than one. The image's config exposes ports
  4444, 5900 and 9000 and runs `entry_point.sh` as uid 1200, which is to say it
  is a server. The client is a separate package that still has to be installed
  somewhere, so this repository ends up building an image regardless, and then
  operating a second container beside it and waiting for it to be ready. That is
  more moving parts at 2am for a check whose whole job is to open one page.

### Option C: Cypress

- **Last release:** 15.21.1 on npm, 2026-08-25.
- **Licence:** MIT.
- **Maintainers:** Cypress.io. `cypress-io/cypress` has 1,021 open issues, by
  far the most of the four, and the contributors listing pages to 411. Two
  publishing accounts on npm.
- **How it arrives:** `cypress/included:15.21.1`, index digest
  `sha256:8d874a8e...`, linux/amd64 and linux/arm64, 0.94 GB compressed on
  arm64.
- **Fit:** the only one of the four that is a whole test runner rather than a
  library, so the assertions, the retries and the reporting all arrive with it
  instead of being written here.
- **Cost:** it is JavaScript, and it owns the whole run rather than being called
  from one. Tests are written in its own runner against its own chained API, so
  the check would not read like anything else in `tools/`.

### Option D: Puppeteer

- **Last release:** 25.9.0 on npm, 2026-08-25.
- **Licence:** Apache-2.0.
- **Maintainers:** Google. `puppeteer/puppeteer` has 245 open issues and the
  contributors listing pages to 445. Two publishing accounts on npm, one of
  them a release bot.
- **How it arrives:** `ghcr.io/puppeteer/puppeteer:25.9.0`, 0.79 GB compressed,
  the smallest of the four.
- **Fit:** the closest thing to driving Chrome with nothing in the way.
- **Cost:** JavaScript, the same as Option C. And that tag is not an index: it
  is a single manifest whose config reads `amd64`, so on the machine this was
  written on every run would be emulated. The mock already costs this repository
  that, and `Makefile` says so where it allows 300 seconds for the development
  stack to come up.

## Decision

**Option A, Playwright, driven from Python, in an image this repository builds
over `mcr.microsoft.com/playwright/python:v1.62.0-noble` pinned by digest, with
the driver installed from a `requirements.txt` carrying a hash per wheel.**

The language decided it before anything else did. There is no JavaScript
toolchain here to join. `git ls-files` finds no `package.json` and no lockfile
of any kind, the only JavaScript in the repository is the three files under
`apps/members/` that Caddy serves as static files with no build step, and the
one Node line in `HANDOFF.md` section 3 is `npx @redocly/cli` for the contract
lint, which CI runs as its own job for that reason. Options C and D would put a
second runtime in front of a volunteer who currently needs Docker and python3.
That eliminated both, and Puppeteer's amd64 only image would have made it a poor
trade on this hardware even in a repository that already had Node.

Between the two Python options, Playwright is one container where Selenium is
two. That is the argument, and it is a small one. Playwright's automatic waiting
is the second: the portal fetches after load, so a check that does not wait for
the network to go quiet is a flake waiting for a slow morning.

The image is built here rather than pulled, for the reason
[ADR 0011](./0011-import-linter-arrives.md) gives at length: the base reaches
the network once per machine, and after that the check runs with nothing
resolving. The base and the lock are pinned the same way that gate pins its own.

## The condition that would flip this

If the lab ever needs a portal check in a browser Playwright does not ship, most
likely a real Safari on real macOS hardware or a phone, Selenium is the thing
that drives it and this decision flips to Option B. Nothing else here would have
to move: the checks are plain Python and the harness is one file.

A second, narrower one. If Microsoft starts publishing a
`mcr.microsoft.com/playwright/python` image with the Python package already in
it, delete the Dockerfile and the lock and pin that image by digest in `run.sh`,
the way `tools/ceilings/run.sh` pins ruff.

## Consequences

- One more image to build, and about a gigabyte to pull the first time on any
  machine. That is the largest single download this repository asks for.
- The check reaches out of its container to a portal on the host, and that turns
  out to have exactly one route. Measured on 2026-08-30:
  `--add-host localhost:host-gateway` does nothing, because chromium resolves
  the name `localhost` to its own loopback and never reads `/etc/hosts` for it,
  so the page fails on `ERR_CONNECTION_REFUSED`. Docker's `host.docker.internal`
  resolves, and `caddy/routes/development.caddyfile` addresses its site block
  `http://{$ORO_HOSTNAME}`, so a request under any other name gets an empty 200
  from Caddy rather than the portal. Both were run. What works is
  `--host-resolver-rules=MAP localhost <gateway>`, which sends the connection to
  the host with `Host: localhost` still on it.
- A URL written `http://127.0.0.1:8080` cannot be driven, because an address
  never reaches a resolver and no rule can redirect it.
  `tools/browser-checks/harness.py` refuses one and says to use the name.
- The resolver rule reaches the browser and not Playwright's own HTTP client.
  `page.request.get(url)` fetches from the driver process rather than from
  chromium, so it stops on `connect ECONNREFUSED ::1:8080` where the page
  itself loads fine. Measured on 2026-08-30. Anything in a check that has to
  fetch by hand goes through the page, which is what
  `views_the_document_shows` does.
- Screenshots land outside the working tree, defaulting to
  `$HOME/oro-screenshots`, and a path inside the repository is refused. Every
  other suite here leaves the tree as it found it, and the prose and ceiling
  gates read `git ls-files`.
- A third Python lock to keep current, after `services/api` and
  `tools/import-boundaries`. Nothing checks that any of the three still matches
  its `requirements.in`, which is ADR 0012's open question, now one wider.
- Two versions have to agree: the tag on the base image and the pin in
  `requirements.in`. The base holds one browser build per browser, named for the
  playwright release that pinned it, so a driver of another version looks for a
  build that is not in the image. Both files say so.
- Reversing this is one directory. Nothing else imports it and no other suite
  calls it.

## What was borrowed

`playwright`, Apache-2.0, installed unmodified from PyPI into an image built
here. `mcr.microsoft.com/playwright/python`, published by Microsoft, run
unmodified as a base. Nothing is vendored and no code is copied.

`ATTRIBUTIONS.md` does not carry either of them yet, and that is owed rather
than argued. The dependency half of that file is generated from a fixed list,
`SOURCES` in `tools/attributions/generate.py`, which names `services/api` and
`tools/import-boundaries` and nothing else. Adding a third line for
`tools/browser-checks` and running `make attributions` is the whole change. It
was left out of this one because that target rewrites a tracked file and builds
every image in the list to read each package's own metadata, which is a
different review from choosing a driver.

`tools/browser-checks/harness.py` takes its shape, and its `run()` almost line
for line, from `tools/members-portal/tests/harness.py`, which is this
repository's own. The Dockerfile takes its hashed install and its non root user
from `services/api/Dockerfile` by way of `tools/import-boundaries/Dockerfile`.

## Open questions

- This gate has no suite of its own. `tools/ceilings/` and
  `tools/import-boundaries/` each plant a violation in a throwaway tree and
  require the gate to catch it, and the argument for that is written into both:
  a gate that has only ever been green proves nothing. Here the equivalent is
  two hand runs, recorded in `tools/browser-checks/README.md` with their output.
  A throwaway page served by a throwaway file server, one that renders and one
  that does not, would close it.
- The check is not in `make check` and not in CI. It is the only thing here that
  needs a portal somebody else started, which is the shape every other suite in
  this repository deliberately avoids. Closing that means the suite bringing up
  its own stack on its own ports, the way `tools/members-portal/tests/run.sh`
  does, and that belongs with the suite rather than with the one check.
- Only chromium is driven. The base image carries firefox and webkit and nothing
  here asks them anything. Whether the portal is checked in more than one engine
  is a question for whoever writes the suite.
