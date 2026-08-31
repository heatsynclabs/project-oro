#!/usr/bin/env python3
"""One check, through a real browser: the members portal loads and a person
arriving signed out gets the landing.

    ORO_PORTAL_URL=http://localhost:8080 python3 check_first_view.py

Run it through tools/browser-checks/run.sh, which supplies the browser.

Why one check and not a suite. Everything past this point needs a sign in, and
signing in means a real identity service, a client registered against it, and a
password. That is a suite worth having and it is not this one. What this proves
is the harness: a real browser, on the real page, running the real script, with
a picture of what it saw.

What the no browser suite next door cannot do, and this can. The portal renders
its views in the browser. Every section in apps/members/index.html arrives
carrying the hidden attribute, apps/members/main.js chooses one and unhides it,
and apps/members/render.js fills it in once the request behind it answers.
tools/members-portal/tests/ reads the document as Caddy serves it, where all
six sections are hidden, so it can say what the page promises and not what a
person gets. The last assertion below is that difference, read twice off the
same address: the document Caddy served, and then the page in front of a
person.

What this deliberately does not assert is anything behind a sign in. A signed
out visitor gets the landing, which is one page with a way in, because every
view is about the reader's own things and somebody who has never been here has
none. Whether the API on this origin answers is what make api-test is for.

It went red on 2026-08-31 and nothing noticed, because the landing arrived the
day after this file did and make browser-checks is in no CI workflow. HANDOFF.md
section 2 carries that gap.
"""
from __future__ import annotations

import re
import sys

from harness import PORTAL_URL, portal_page, run, screenshot

# What a person who has never signed in is shown. Not a view: the views are all
# about the reader's own things, so apps/members/render.js hides every one of
# them and unhides this instead.
LANDING_HEADING = "Your membership at HeatSync Labs"

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
    """The data-route of every view section a person can currently see.

    The landing is a section.view as well, so that it inherits the same
    spacing, and it carries no data-route because it is not a route. Selecting
    on the attribute is what keeps it out of this list.
    """
    sections = page.locator("section.view[data-route]")
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


def test_the_landing_renders_for_a_person_who_is_signed_out() -> None:
    with portal_page() as page:
        # Before the assertions, so a red run still leaves the picture that
        # says why. Half the value of a browser check is the screenshot.
        path = screenshot(page, "landing")
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

        landing = page.locator("section.view.landing")
        assert landing.is_visible(), (
            f"A person arriving signed out at {PORTAL_URL} was shown no "
            "landing. Either the script did not run, or it decided this "
            "browser is signed in, and the screenshot above shows which.")

        heading = landing.locator("h2").first.inner_text()
        assert reads(heading) == reads(LANDING_HEADING), (
            f"The landing is headed {heading!r} rather than {LANDING_HEADING!r}.")

        showing = visible_views(page)
        assert showing == [], (
            f"The portal opened showing {showing} beside the landing. Every "
            "view is about the reader's own things and a person who has never "
            "signed in has none, so a signed out arrival shows none of them.")

        for control, what in ((landing.locator("[data-join]"), "a way to join"),
                              (landing.locator("[data-sign-in]"),
                               "a way in for somebody who already has an account")):
            assert control.is_visible(), (
                f"The landing offers no {what}. A page with nothing to read and "
                "no way forward is why the landing exists.")

        served = views_the_document_shows(page, PORTAL_URL)
        assert served == [], (
            f"Caddy serves {PORTAL_URL} with {served} already unhidden. Every "
            "view is meant to arrive hidden and be chosen in the browser, so "
            "with one of them unhidden in the document this check would pass "
            "on a page whose script never ran. Something in "
            "apps/members/index.html lost its hidden attribute.")


if __name__ == "__main__":
    sys.exit(run(dict(globals()), "browser"))
