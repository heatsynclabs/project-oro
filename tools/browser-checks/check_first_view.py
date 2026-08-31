#!/usr/bin/env python3
"""One check, through a real browser: the members portal loads and its first
view renders.

    ORO_PORTAL_URL=http://localhost:8080 python3 check_first_view.py

Run it through tools/browser-checks/run.sh, which supplies the browser.

Why one check and not a suite. Everything the portal shows past this point
comes from the contract mock, and the service that will replace the mock is
being wired now, so a suite written today would be written against something
about to move. What this proves is the harness: a real browser, on the real
page, running the real script, with a picture of what it saw.

What the no browser suite next door cannot do, and this can. The portal renders
its views in the browser. Every section in apps/members/index.html arrives
carrying the hidden attribute, apps/members/main.js chooses one and unhides it,
and apps/members/render.js fills it in once the request behind it answers.
tools/members-portal/tests/ reads the document as Caddy serves it, where all
six sections are hidden, so it can say what the page promises and not what a
person gets. The last assertion below is that difference, read twice off the
same address: the document Caddy served, and then the page in front of a
person.

What this deliberately does not assert is whether the first view's request
answered. A signed out visitor gets a panel saying so, that panel is the
portal's own design, and whether the API on this origin answers is what
make mock-test and make api-test are for.
"""
from __future__ import annotations

import re
import sys

from harness import PORTAL_URL, portal_page, run, screenshot

# The route the portal opens on when nobody has asked for anything else. An
# empty fragment finds no section in apps/members/main.js, so show() falls back
# to the first one in the document, and that one is /me.
FIRST_VIEW = "/me"

# What a browser tab has to say for a person to know which page they are on.
TITLE_STARTS = "Members portal"

A_VIEW_SECTION = re.compile(r"<section\b[^>]*\bdata-route=\"([^\"]+)\"[^>]*>")


def reads(text: str) -> str:
    """One rendered string, ready to compare against the document's own copy.

    Case folded, and that fold is the first thing this check found. Both `h2`
    and `.status` in apps/members/members.css carry text-transform: uppercase,
    so the document says "Your record" and a browser reads back "YOUR RECORD".
    A check that reads the served document sees no difference there at all.
    Folding rather than pinning the uppercase, because the uppercase is a theme
    decision and this check is about the portal working.
    """
    return text.strip().casefold()


def visible_views(page) -> list[str]:
    """The data-route of every view section a person can currently see."""
    sections = page.locator("section.view")
    return [sections.nth(index).get_attribute("data-route")
            for index in range(sections.count())
            if sections.nth(index).is_visible()]


def views_the_document_shows(page, url: str) -> list[str]:
    """The data-route of every view section Caddy serves without the hidden
    attribute on it.

    Fetched by the page itself, so it takes the same route to the same address
    the page took and nothing runs over what comes back. Playwright's own
    request context is not used here: it fetches from the driver rather than
    from the browser, so the resolver rule harness.py sets does not apply to it
    and it stops on ECONNREFUSED. That was measured rather than reasoned about.
    """
    document = page.evaluate(
        "address => fetch(address).then(answer => answer.text())", url)
    return [route for tag, route in
            ((match.group(0), match.group(1))
             for match in A_VIEW_SECTION.finditer(document))
            if "hidden" not in tag]


def test_the_first_view_renders_for_a_person() -> None:
    with portal_page() as page:
        # Before the assertions, so a red run still leaves the picture that
        # says why. Half the value of a browser check is the screenshot.
        path = screenshot(page, "first-view")
        print(f"Screenshot: {path}")

        # The start of the title rather than the whole of it. What follows it
        # says which back end the page is reading, and that sentence is meant
        # to change on the day the portal comes off the contract mock. What a
        # person needs from a browser tab is the first two words.
        assert page.title().startswith(TITLE_STARTS), (
            f"The page in the browser is titled {page.title()!r}. The portal "
            f"at {PORTAL_URL} titles itself {TITLE_STARTS!r} and then says "
            "which back end it is reading. Something else is answering that "
            "address, or apps/members/index.html changed and this check did "
            "not.")

        showing = visible_views(page)
        assert showing == [FIRST_VIEW], (
            f"The portal opened showing {showing}, and a person arriving at "
            f"{PORTAL_URL} should see exactly {[FIRST_VIEW]}. If the list is "
            "empty, the script did not run or it stopped before it chose a "
            "route, and the screenshot above shows which.")

        view = page.locator(f"section.view[data-route='{FIRST_VIEW}']")
        heading = view.locator("h2").first.inner_text()
        assert reads(heading) == reads("Your record"), (
            f"The first view is headed {heading!r} rather than 'Your record'.")

        served = views_the_document_shows(page, PORTAL_URL)
        assert served == [], (
            f"Caddy serves {PORTAL_URL} with {served} already unhidden. Every "
            "view is meant to arrive hidden and be chosen in the browser, so "
            "with one of them unhidden in the document this check would pass "
            "on a page whose script never ran. Something in "
            "apps/members/index.html lost its hidden attribute.")


if __name__ == "__main__":
    sys.exit(run(dict(globals()), "browser"))
