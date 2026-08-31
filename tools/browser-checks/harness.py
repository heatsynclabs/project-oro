#!/usr/bin/env python3
"""The parts of the browser checks that are not themselves checks.

One browser pointed at the running portal, one screenshot written where a
person can open it, and the runner that prints the result. check_first_view.py
holds the check and nothing else.

The shape of this file, and run() almost line for line, is
tools/members-portal/tests/harness.py in this repository. That suite reads what
the portal's document says. This one runs the document.
"""
from __future__ import annotations

import contextlib
import os
import socket
import urllib.parse

from playwright.sync_api import sync_playwright

# Where the portal is, as a person would type it into a browser. run.sh passes
# this through from the caller.
PORTAL_URL = os.environ.get("ORO_PORTAL_URL", "http://localhost:8080")

# Mounted by run.sh from a directory on the host, so a screenshot outlives the
# container that took it.
SHOTS = "/shots"

# The same directory as the person running this would type it. A path inside
# the container is no use to somebody being told where to look.
SHOTS_ON_HOST = os.environ.get("ORO_SHOT_DIR", SHOTS)

# A page with a fetch behind it is not finished when load fires. Ten seconds is
# the mock answering from a cold container on a laptop, measured at well under
# one.
SETTLE_MILLISECONDS = 10_000


def loopback_rule(url: str) -> list[str]:
    """The chromium arguments that let a browser in a container reach a portal
    on the machine running it.

    Measured on 2026-08-30: chromium resolves the name `localhost` to its own
    loopback and never reads /etc/hosts for it, so `--add-host` cannot redirect
    it and the page fails with ERR_CONNECTION_REFUSED. Docker's own
    `host.docker.internal` does resolve, but the portal is a Caddy site block
    addressed http://localhost, so a request carrying any other Host header
    gets an empty 200 from Caddy rather than the portal. Both were run.

    The resolver rule is the one mechanism that satisfies both: the browser
    connects to the host and still sends `Host: localhost`.
    """
    host = urllib.parse.urlsplit(url).hostname
    if host != "localhost":
        return []
    return ["--host-resolver-rules=MAP localhost "
            + socket.gethostbyname("host.docker.internal")]


def refuse_an_address_no_rule_can_reach(url: str) -> None:
    """Stop on a URL this cannot drive, rather than on a timeout that reads as
    a broken portal."""
    host = urllib.parse.urlsplit(url).hostname
    if host in ("127.0.0.1", "::1"):
        raise SystemExit(
            f"ORO_PORTAL_URL is {url}, and nothing was checked.\n"
            "The browser runs in a container, where that address is the\n"
            "container itself. An address is not a name, so no resolver rule\n"
            "reaches past it. Set ORO_PORTAL_URL to the same port on\n"
            "localhost and run this again.")


@contextlib.contextmanager
def portal_page(url: str = PORTAL_URL):
    """A real chromium on the portal's first view, with the fetch settled."""
    refuse_an_address_no_rule_can_reach(url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=loopback_rule(url))
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(url, wait_until="networkidle",
                      timeout=SETTLE_MILLISECONDS)
            yield page
        finally:
            browser.close()


def screenshot(page, name: str) -> str:
    """Write the whole page out and return the path a person can open."""
    page.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)
    return os.path.join(SHOTS_ON_HOST, name + ".png")


def run(checks, what: str = "browser") -> int:
    """Run every test_ function in a namespace and report what failed."""
    found = [(name, function) for name, function in sorted(checks.items())
             if name.startswith("test_") and callable(function)]
    failed = []
    for name, function in found:
        try:
            function()
        except AssertionError as problem:
            failed.append(name)
            print(f"FAIL  {name}\n        {problem}")
        except Exception as problem:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}\n        {type(problem).__name__}: {problem}")
    print(f"\n{len(found) - len(failed)}/{len(found)} {what} checks passed")
    return 1 if failed else 0
