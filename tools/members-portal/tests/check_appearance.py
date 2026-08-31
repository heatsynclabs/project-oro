#!/usr/bin/env python3
"""Prove what the members portal looks like, as far as a check with no browser can.

check_portal.py holds the checks about the contract underneath the page. These
are the ones about the page itself: the chrome it wears, the components the ORO
mockups use, and the four corrections
`docs/plan/changes-from-the-original.md` section 4 makes to those mockups.

No browser runs here either, so nothing below can see a layout. Each check
therefore asserts on what is in the document or in the stylesheet a reader is
served, which is where every one of those corrections is either kept or lost.

Run it against a stack that is already up:

    ORO_PORTAL_URL=http://localhost:8080 python3 tools/members-portal/tests/check_appearance.py

tools/members-portal/tests/run.sh brings up its own stack and runs this.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402
import page  # noqa: E402
from harness import fetch  # noqa: E402

HTML = fetch("/").body

# The portal's own stylesheets, which is every one it links except the token
# layer. Read from the page rather than listed here, so a third file added
# tomorrow is measured the day it is added.
OWN_STYLESHEETS = [element.get("href") for element in page.named(HTML, "link")
                   if element.get("rel") == "stylesheet"
                   and not element.get("href", "").startswith("/theme/")]


def stylesheet_rules():
    """Every rule the portal serves, with the comments taken out.

    A comment that names a token in order to say why the file does not use it
    would otherwise read as a use of it, which is how the contrast check below
    first went red on the sentence explaining the contrast check.
    """
    served = "\n".join(fetch(href).body for href in OWN_STYLESHEETS)
    return re.sub(r"/\*.*?\*/", "", served, flags=re.S)


# ------------------------------------- what the mockups drew and this keeps

def test_the_masthead_mark_is_the_packaged_one_in_two_colours():
    """The brand package's own rule, from heatsync-brand/references/logos.md:
    the mark is two pieces in two colours, and filling the sun disc with the
    flame colour makes a shape that is no longer the HeatSync mark. So the disc
    carries the logo orange and the flames carry currentColor, and an earlier
    version of this portal that drew its own simplified sun broke the rule the
    same document states as "do not redraw or simplify the flames"."""
    marks = [svg for svg in page.named(HTML, "svg")
             if "sunmark" in svg.get("class", "")]
    assert marks, "no element with class sunmark, so the masthead has no mark"
    holder = marks[0].enclosing("class")
    assert holder is not None and "topbar" in holder.get("class"), \
        "the mark is not in the masthead"

    at = HTML.index('class="sunmark"')
    start = HTML.rindex("<svg", 0, at)
    mark = HTML[start:HTML.index("</svg>", at)]
    assert "#F99A1C" in mark, (
        "the sun disc does not carry the logo orange #F99A1C. logos.md samples "
        "it from the canonical raster and says --hazard is the UI accent, not "
        "the logo orange")
    assert "currentColor" in mark, \
        "the flames do not take currentColor, so the mark cannot follow the theme"
    fills = re.findall(r'fill="([^"]+)"', mark)
    assert fills == ["#F99A1C", "currentColor"], (
        f"the mark is filled {fills}, and logos.md says it is two pieces in two "
        "colours: the disc, then the flames and the arrow as one piece")
    assert len(mark) > 8000, (
        f"the mark is {len(mark)} characters, which is too little path data to "
        "be the traced original. logos.md forbids redrawing or simplifying the "
        "flames, and a hand drawn approximation is what this catches")



def test_an_unconfirmed_email_is_a_signal_and_not_a_gate():
    """The lab asked for confirmation to read as a more verified account rather
    than as a blocker. So the portal carries a chip that reports it and a line
    saying it takes nothing away, and it must not tell a member that anything
    is withheld until they confirm. The account works either way: both paths
    that create one, tools/identity/api.py and tools/bootstrap/, and the
    nullable email_verified_at column, all treat unconfirmed as a valid state."""
    chips = [e for e in page.named(HTML, "span")
             if e.get("data-field") == "email_verified_at"]
    assert chips, "nothing reports whether the email address is confirmed"
    assert chips[0].get("data-chip") == "present", (
        "the confirmation is not a chip, so it reads as a row of state rather "
        "than as a signal")

    lowered = HTML.lower()
    for gate in ["must confirm", "confirm your email to",
                 "until you confirm", "unverified accounts",
                 "verify your email to", "confirm to continue"]:
        assert gate not in lowered, (
            f"the portal says {gate!r}, which makes confirmation a gate. It is "
            "a signal: an account that is never confirmed still works")
def test_the_page_wears_the_components_the_mockups_use():
    """The cards, the chips and the sheet, taken from the mockups rather than
    invented. A view that went back to a bare definition list is the drift this
    catches."""
    classes = set()
    for element in page.elements(HTML):
        classes.update(element.get("class", "").split())
    for wanted in ("card", "card-label", "card-title", "kv", "chip",
                   "sheet", "note", "grid2", "tape", "action"):
        assert wanted in classes, f"nothing on the page carries class {wanted}"


def test_every_control_keeps_the_tap_target_floor():
    """A card table read on a phone in a workshop. --tap is 44px, and the
    controls are the view switcher and the buttons that sign a member in, sign
    them out, and write their record on a first sign in."""
    styles = stylesheet_rules()
    for selector in (r"\.views a", r"\.action"):
        assert re.search(selector + r"\s*\{[^}]*min-height: var\(--tap\)", styles), \
            f"{selector} sets no minimum height, so it can go under 44px"


# ----------------------------------------- what the mockups drew and this drops

def test_no_door_controller_slot_reaches_a_member():
    """A slot is an EEPROM address on the door controller. The mockups put
    "Slot 041" in front of a member, and the adapter in db/migrations exists
    precisely so that hardware detail stops at the door service."""
    assert "controller_slot" not in HTML, \
        "the page binds controller_slot, which is a door controller address"
    found = re.search(r"\bslots?\b", HTML, re.I)
    assert found is None, \
        f"the page says {found.group(0)!r}, which is door controller vocabulary"


def test_nothing_says_two_admins_decide_card_access():
    """The mockups say "Grants and revokes need two admins by lab rule". No
    such rule exists. Card access is voted on by card members at Hack Your
    Hackerspace, per docs/glossary.md."""
    assert "two admins" not in HTML.lower(), \
        "the page still says two admins decide card access"
    assert "Hack Your Hackerspace" in HTML, \
        "the page never names the meeting where card access is actually decided"


def test_the_page_holds_no_payment_record():
    """Payments are out of scope, by direction. The mockups show a status of
    Paid, a last payment date, a stored payment method and a button to change
    it. A control that cannot work is worse than no control."""
    for leftover in ("paypal", "last payment", "update payment method"):
        assert leftover not in HTML.lower(), \
            f"the page carries {leftover!r}, and payments are out of scope"
    assert "Standing" in HTML, "the page shows no standing, which is what replaced it"


def test_the_card_eligibility_view_is_reachable():
    """The question members actually ask, and the one the mockups have no
    answer for. db/migrations/012_close_remaining.sql answers it."""
    routes = [element.get("data-source") for element in page.carrying(HTML, "data-source")]
    assert "/me/card-eligibility" in routes, "no view reads the eligibility endpoint"
    links = [element.get("href") for element in page.named(HTML, "a")]
    assert "#/card-eligibility" in links, "nothing in the navigation reaches it"


# ------------------------------------------- honesty about who is reading it

def test_the_chrome_names_whoever_is_signed_in_and_offers_the_way_out():
    """The mockups put an avatar, a member's name and a sign out link in the app
    bar. Two of the three are right now that there is a sign in behind them: the
    chip carries whoever the identity service says is reading, and the control
    beside it ends the session there as well as here. The avatar is still not
    here, because nothing in this system holds one.

    This check used to assert the opposite, that the page said nobody was signed
    in and offered no way out. That was true while the identity service was not
    reachable from the portal and it is a lie now.
    """
    chips = {element.get("data-who")
             for element in page.carrying(HTML, "data-who")}
    assert chips == {"signed-out", "signed-in"}, \
        f"the app bar carries chips for {sorted(chips)}, expected both states"
    assert "Not signed in" in HTML, \
        "the chrome no longer says so when nobody is signed in"
    assert page.carrying(HTML, "data-name"), \
        "nothing in the chrome carries the name of whoever is signed in"
    assert any("data-sign-out" in element.attrs
               for element in page.named(HTML, "button")), \
        "the page offers no way out of a session it can start"
    assert "avatar" not in HTML.lower(), \
        "the page carries an avatar, and nothing here holds a picture of anybody"


# ------------------------------------------------------ colour and contrast

def test_the_stylesheets_name_no_colour_of_their_own():
    """Every colour resolves through a token, because the contrast validator in
    packages/gantry-tokens measures tokens and cannot measure a literal."""
    assert OWN_STYLESHEETS, "the page links no stylesheet of its own"
    styles = stylesheet_rules()
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b", styles)
    literals += re.findall(r"\b(?:rgba?|hsla?|color-mix|oklch)\(", styles)
    assert not literals, f"the portal picks colours by hand: {sorted(set(literals))}"


def test_nothing_a_reader_must_read_uses_the_tertiary_ink():
    """HANDOFF.md section 7: --g-ink-3, which --color-text-tertiary aliases,
    measures below the contrast minimum on three of the four grounds. The
    mockups reach for it on the value labels, the sheet headings and the
    footnote, which is most of the small text on the screen."""
    styles = stylesheet_rules()
    for banned in ("--g-ink-3", "--color-text-tertiary", "--ink-ghost"):
        assert banned not in styles, \
            f"{banned} is below the contrast minimum and carries readable text"


if __name__ == "__main__":
    sys.exit(harness.run(globals(), "appearance"))
