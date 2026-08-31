#!/usr/bin/env python3
"""Prove what the members portal lets a member change, with no browser.

The portal reads six things and writes two, and both writes are the member's
own record: the button a first sign in gets, which check_sign_in.py holds, and
the profile form, which is this file. No browser runs here, so nothing below
saves anything. What a check with no browser can do is read the form the server
sends and hold every field in it against the contract, which is the failure
worth catching: a field name the API does not take is refused on the first save
a member tries, and the member reads that as the lab losing what they typed.

Run it against a stack that is already up:

    ORO_PORTAL_URL=http://localhost:8080 python3 tools/members-portal/tests/check_profile.py

tools/members-portal/tests/run.sh brings up its own stack and runs this.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402
import page  # noqa: E402
from harness import ROOT, fetch, signed_in  # noqa: E402

HTML = fetch("/").body
CONTRACT = (ROOT / "docs" / "api" / "members-v1.yaml").read_text()

FORMS = page.named(HTML, "form")
OFFERED = page.carrying(HTML, "data-edit")


def schema_properties(name: str) -> list[str]:
    """The property names one schema in the contract declares.

    Read by indentation rather than with a YAML parser, because a parser is a
    dependency this tree does not have and this needs two blocks of one file.
    A property is a line at eight spaces ending in a colon, and the block ends
    at the first line indented less than that.
    """
    block = CONTRACT[CONTRACT.index(f"    {name}:"):]
    block = block[block.index("      properties:"):]
    out = []
    for line in block.splitlines()[1:]:
        if line.strip() and not line.startswith("        "):
            break
        found = re.match(r"        (\w+):", line)
        if found:
            out.append(found.group(1))
    return out


def boolean_properties(name: str) -> list[str]:
    """The properties of one schema that are a plain yes or no."""
    block = CONTRACT[CONTRACT.index(f"    {name}:"):]
    block = block[:block.index("      additionalProperties")]
    return re.findall(r"        (\w+): \{ type: boolean \}", block)


def fields_under(source: str) -> set:
    """Every field name bound anywhere inside the view that reads one path."""
    out = set()
    for field in page.carrying(HTML, "data-field"):
        holder = field.enclosing("data-source")
        if holder is not None and holder.get("data-source") == source:
            out.add(field.get("data-field"))
    return out


def label_for(field):
    """The label element pointing at one control, or None."""
    for label in page.named(HTML, "label"):
        if label.get("for") == field.get("id"):
            return label
    return None


# ------------------------------------------------------- the form itself

def test_a_member_can_change_their_own_record():
    """The portal the lab runs today lets a member edit their profile, so a
    replacement that only reads is a replacement that takes something away."""
    assert len(FORMS) == 1, \
        f"{len(FORMS)} forms on this page, and the profile is the only one"
    assert "data-profile-form" in FORMS[0].attrs, \
        "the one form on the page is not the profile form"
    assert OFFERED, "the form offers no field, so nothing can be changed"
    saves = [button for button in page.named(HTML, "button")
             if button.get("type") == "submit"]
    assert saves, "the form has no submit control, so a keyboard cannot save it"
    assert saves[0].enclosing("data-profile-form") is not None, \
        "the submit control is not inside the form it saves"


def test_the_form_sits_in_the_view_that_reads_the_record_it_changes():
    """The record and the boxes that change it are one view, so a member does
    not read one page and edit another that might disagree with it."""
    holder = FORMS[0].enclosing("data-source")
    assert holder is not None and holder.get("data-source") == "/me", \
        "the profile form is not inside the view that reads /me"


# ------------------------------------------ every field, against the contract

def test_every_field_the_form_offers_is_one_a_member_may_change():
    """The check this form exists to pass. MemberSelfUpdate in
    docs/api/members-v1.yaml is what PATCH /me accepts, and it declares
    additionalProperties: false, so a field invented in the page is refused and
    the whole save fails with it."""
    allowed = schema_properties("MemberSelfUpdate")
    assert allowed, "MemberSelfUpdate declares no properties, so this read nothing"
    for field in OFFERED:
        assert field.get("data-edit") in allowed, (
            f"the form offers {field.get('data-edit')!r}, which MemberSelfUpdate "
            "does not declare, so PATCH /me refuses the whole request")


def test_the_form_offers_nothing_an_admin_owns():
    """Standing, the dues date, when somebody joined and who walked them round
    the lab are an admin's to set. The database refuses them by trigger, in
    enforce_profile_self_edit, and a box on this page offering one would be a
    control that cannot work. The list is the difference between the two update
    schemas rather than a list written here."""
    admin_only = set(schema_properties("MemberAdminUpdate")) \
        - set(schema_properties("MemberSelfUpdate"))
    assert admin_only, "the two schemas differ by nothing, so this read nothing"
    offered = {field.get("data-edit") for field in OFFERED}
    assert not (offered & admin_only), \
        f"the form offers {sorted(offered & admin_only)}, which an admin sets"


def test_the_visibility_switches_are_the_ones_the_contract_types_as_a_yes_or_no():
    """What the directory shows about a member is three yes or no answers, and
    a checkbox is what sends a boolean. A text box would send the word."""
    switches = boolean_properties("MemberSelfUpdate")
    assert len(switches) == 3, f"expected three, the contract types {switches}"
    for name in switches:
        offered = [field for field in OFFERED if field.get("data-edit") == name]
        assert offered, f"the form never offers {name}"
        assert offered[0].get("type") == "checkbox", (
            f"{name} is a yes or a no in the contract and the form offers it as "
            f"a {offered[0].get('type')}, which sends a string")


# ------------------------------------------------- what a screen reader gets

def test_every_field_carries_a_label_a_screen_reader_can_use():
    """A placeholder is not a label: it disappears on the first keystroke and
    several screen readers never announce it at all."""
    for field in OFFERED:
        assert field.get("id"), \
            f"{field.get('data-edit')} has no id, so no label can point at it"
        assert label_for(field) is not None, \
            f"{field.get('data-edit')} has no label pointing at its id"
        assert "placeholder" not in field.attrs, \
            f"{field.get('data-edit')} leans on a placeholder instead of a label"


def test_the_three_kinds_of_field_are_grouped_and_each_group_says_what_it_is():
    """Plain contact details, what the directory shows, and who the lab calls in
    an emergency are three different questions. A fieldset draws the boundary
    and its legend is what a screen reader announces with every control inside
    it, which is the same grouping a sighted member reads."""
    groups = page.named(HTML, "fieldset")
    assert len(groups) == 3, f"{len(groups)} fieldsets, expected three"
    assert len(page.named(HTML, "legend")) == 3, \
        "a fieldset has no legend, so its group is drawn and never named"
    for field in OFFERED:
        assert field.enclosing("data-fields") is not None, \
            f"{field.get('data-edit')} sits in no group"
    emergency = {field.enclosing("data-fields").get("data-fields")
                 for field in OFFERED
                 if field.get("data-edit").startswith("emergency_")}
    assert len(emergency) == 1, \
        f"the emergency contact is spread across {sorted(emergency)}"


# ----------------------------------------------------- what saving reports

def test_the_page_says_what_happened_when_a_member_saves():
    """A save that reports nothing reads as a save that did not happen. Both
    sentences are attributes on the form rather than strings in a script, for
    the same reason every view carries data-loading and data-loaded: it is what
    lets this check read the copy without running the page."""
    form = FORMS[0]
    for said in ("data-saving", "data-saved"):
        assert form.get(said), f"the form carries no {said} sentence"
    live = [element for element in page.carrying(HTML, "data-save-status")
            if element.get("role") == "status"]
    assert live, \
        "nothing in the form is a live region, so a screen reader is never " \
        "told the save finished"
    assert page.carrying(HTML, "data-save-error"), \
        "the form has nowhere to show a refusal, so it would take the form off " \
        "the screen along with what the member had typed"


def test_a_refusal_that_names_a_field_is_shown_against_that_field():
    """A ProblemDetail carries an errors list of a field and a sentence about
    it, per docs/api/members-v1.yaml. Pointing the input at that sentence is
    what makes a screen reader read the two together, and it is the difference
    between "that request could not be applied" and knowing which box."""
    assert "errors" in CONTRACT[CONTRACT.index("    ProblemDetail:"):][:2000], \
        "the contract no longer carries per field problems"
    source = fetch("/profile.js").body
    for wanted in ("aria-invalid", "aria-describedby", "problem.errors"):
        assert wanted in source, \
            f"profile.js never sets {wanted}, so a refusal is not tied to a field"


def test_the_form_saves_by_the_operation_the_contract_declares():
    """PATCH /me, read out of the contract rather than assumed, and sent by
    api.js. A page that saved by some other path would be a second opinion
    about where a member's record lives."""
    assert "operationId: updateMe" in CONTRACT, \
        "the contract declares no PATCH /me, so this form offers an operation " \
        "that does not exist. Rule 10"
    sent = fetch("/api.js").body
    assert re.search(r'send\("/me", "PATCH"', sent), \
        "api.js never sends PATCH /me, so the form has nothing to save through"


def test_whatever_is_behind_the_api_answers_a_save_in_a_shape_a_page_shows():
    """The block a member is shown on a refusal is bound to the fields of a
    problem detail, so an answer that is not JSON leaves an empty box on the
    screen. No browser here signs in, so this asserts the shape of the answer
    and never that a save succeeded.
    """
    answer = signed_in("/v1/me", method="PATCH", body={"pronouns": "they/them"})
    try:
        json.loads(answer.body)
    except ValueError:
        raise AssertionError(
            f"PATCH /v1/me answered {answer.status} and the body was not JSON, "
            "so a member saving their profile is shown an empty refusal"
        ) from None


# ------------------------------------------------- what the markup carries

def test_no_token_reaches_the_markup():
    """Two senses of the word, and the form is a new surface for both.

    A GANTRY token typed into an element escapes the contrast validator in
    packages/gantry-tokens, which measures the stylesheets and cannot see an
    attribute. And a credential in a static file is readable by anybody who
    loads the page: check_sign_in.py holds that over every script, and this
    holds it over the document they sit in.
    """
    for element in page.elements(HTML):
        assert "style" not in element.attrs, \
            f"<{element.name}> carries an inline style, which no token measures"
    assert "--g-" not in HTML, \
        "the document names a theme token, so a colour on this page is set " \
        "where the contrast validator cannot read it"
    assert "eyJ" not in HTML, "the page carries something shaped like a token"


def test_the_entries_view_hands_a_member_nothing_about_the_hardware():
    """A door event is an access record for a building, and what a member wants
    from it is when they came in and which door. The card row it names, the raw
    value the controller sent and the free form detail object are all in the
    contract and none of them is that. check_appearance.py refuses the slot
    number itself, which is the one that would be a real disclosure."""
    entries = [view for view in page.carrying(HTML, "data-source")
               if view.get("data-source") == "/me/door-events"]
    assert entries, "no view reads the member's own door events"
    bound = fields_under("/me/door-events")
    assert bound, "the entries view shows nothing at all"
    for hardware in ("card_id", "raw_data", "detail", "dedupe_key"):
        assert hardware not in bound, \
            f"the entries view shows {hardware}, which tells a member nothing " \
            "they can act on"


if __name__ == "__main__":
    sys.exit(harness.run(globals(), "profile"))
