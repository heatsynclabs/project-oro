#!/usr/bin/env python3
"""Prove what the members portal does about signing in, with no browser.

No browser runs here, so nothing below completes a sign in or reads a rendered
page. What a check with no browser can do is read what the server sends and call
what the page calls, and every claim this portal makes about signing in is in
one of those two places: the controls and the sentences are in the document, the
client id is in a document beside it, and what is behind /v1 is a question this
suite asks the same way the page asks it. Driving the whole flow through real
screens is a browser's job and is somebody else's task.

Run it against a stack that is already up:

    ORO_PORTAL_URL=http://localhost:8080 python3 tools/members-portal/tests/check_sign_in.py

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
from harness import PORTAL, ROOT, fetch, signed_in  # noqa: E402

HTML = fetch("/").body

# Every script the page loads, as the reader is served it, read off the page so
# a file added tomorrow is checked the day it is added.
SCRIPTS = [element.get("src") for element in page.named(HTML, "script")
           if element.get("src")]

def portal_source(name):
    """One of the portal's own files, off disk, with a readable failure."""
    where = PORTAL / name
    assert where.exists(), f"apps/members/{name} is not there"
    return where.read_text()


def configuration_path():
    """Where the portal reads its client id from, taken out of identity.js
    rather than written twice. A copy here would pass while the page asked for
    another path and found nothing."""
    found = re.search(r'CONFIGURATION_PATH = "([^"]+)"', portal_source("identity.js"))
    assert found, "identity.js names no configuration document to read"
    return found.group(1)


def served_scripts():
    return {src: fetch(src).body for src in SCRIPTS}


def behind_the_api():
    """What answers /v1 on this stack, sorted the way api.js sorts it.

    200 to a token nothing issued means nothing checks tokens, which is the
    contract mock. A refusal carrying a problem detail is a real service. An
    answer that is not JSON means nothing is routed there, which is what Caddy's
    own 502 looks like.
    """
    source = fetch("/api.js").body
    probe = re.search(r'A_TOKEN_NOTHING_ISSUED = "([^"]+)"', source)
    assert probe, "api.js no longer measures what is behind /v1, so the band guesses"
    answer = fetch("/v1/me", {"Authorization": "Bearer " + probe.group(1),
                              "Accept": harness.ACCEPTED})
    if answer.status == 200:
        return "mock"
    try:
        json.loads(answer.body)
    except ValueError:
        return "unknown"
    return "service"


# ------------------------------------------------------ the controls a person gets

def test_the_page_offers_a_sign_in_and_a_sign_out_a_keyboard_can_reach():
    """A signed out member needs somewhere to go, and it has to be a control
    rather than a line of text. A button is reachable by tab and pressable by
    space, and it is not a link because the address it goes to carries a
    challenge that does not exist until it is pressed."""
    buttons = page.named(HTML, "button")
    assert buttons, "the page carries no button, so nothing offers a sign in"
    for wanted in ("data-sign-in", "data-sign-out"):
        found = [button for button in buttons if wanted in button.attrs]
        assert found, f"no button carries {wanted}"
        assert found[0].get("type") == "button", (
            f"the {wanted} button has no type, so it defaults to submit")
        assert found[0].enclosing("data-profile-form") is None, (
            f"the {wanted} button sits inside the profile form, so pressing it "
            "would save the form on the way past")


def test_a_signed_out_reader_is_told_what_to_do_about_it():
    """Every view is the reader's own record, so signed out it has nothing to
    show. Showing an empty record instead of saying so is what a member reads as
    the lab having lost their cards."""
    assert 'id="not-signed-in"' in HTML, \
        "no template for a view a signed out reader is looking at"
    assert "Sign in to read this" in HTML, \
        "the signed out block never says what to do"
    assert "showSignedOut" in fetch("/render.js").body, \
        "the renderer has no path that shows that block"


# ------------------------------------------------------------ nothing shipped

def test_nothing_the_server_sends_carries_a_token():
    """The portal shipped a bearer token as a constant in api.js until this
    change, which was honest while the mock took any string and is a credential
    in a static file the moment one is real. Every token this page uses now
    arrives from the identity service at run time and is held by the browser."""
    sent = dict(served_scripts())
    sent["/"] = HTML
    for where, body in sent.items():
        assert "CONTRACT_MOCK_TOKEN" not in body, \
            f"{where} still declares the constant the portal used to ship"
        assert "eyJ" not in body, \
            f"{where} carries something shaped like a JSON web token"
        found = re.search(
            r'(?i)(?:access|refresh|bearer|api)[_ ]?(?:token|key)"?\s*[:=]\s*'
            r'"([A-Za-z0-9._-]{16,})"', body)
        assert found is None, \
            f"{where} assigns a credential shaped value: {found.group(1)[:12]}..."


def test_no_script_names_an_identity_service_or_a_client_id():
    """Zitadel generates a client id per instance, so a portal carrying one
    works on exactly one deployment and fails silently everywhere else. The same
    goes for the address of the identity service: on a laptop it is a port on
    localhost and on a deployment it is a name under the hostname."""
    for where, body in served_scripts().items():
        assert "://" not in body, \
            f"{where} names an absolute address, and every origin here differs"
        assert not re.search(r'client_?id"?\s*[:=]\s*"[0-9]{6,}"', body, re.I), \
            f"{where} carries a client id, which belongs to one instance only"


# ------------------------------------------------- the configuration document

def test_the_client_id_is_read_from_a_document_on_this_origin():
    """The one mechanism, and every way it can be wrong is a state the page
    names rather than a button that does nothing.

    tools/identity/configure.py writes it when it registers the client, because
    that step alone knows the client id at the moment it exists. This suite
    meets two of the three states: a stack that step never ran against serves no
    document, and a throwaway stack on another port serves the one written for a
    laptop's own stack, because the file sits in the directory Caddy binds.
    """
    path = configuration_path()
    served = fetch(path)
    if served.status != 200:
        assert "tools/identity/configure.py" in HTML, (
            f"{path} is not served, and the page never names the command that "
            "writes it, so a reader is left with a sign in that does nothing")
        return
    document = json.loads(served.body)
    for key in ("issuer", "client_id", "redirect_uri"):
        assert document.get(key), f"{path} carries no {key}"
    if document["redirect_uri"] != harness.BASE + "/":
        assert "reading it on" in HTML, (
            f"{path} registers {document['redirect_uri']!r} and this portal is "
            f"served from {harness.BASE!r}, so a sign in would send the code "
            "somewhere this page never sees it, and the page says nothing "
            "about that")


def test_the_page_has_a_sentence_for_every_way_signing_in_can_be_unavailable():
    """Four states, and none of them is the sign in button doing nothing.
    identity.js answers with one of these names and the band under the masthead
    carries the sentence for each, so the reason is on screen rather than in a
    console."""
    said = {element.get("data-signing-in")
            for element in page.carrying(HTML, "data-signing-in")}
    source = portal_source("identity.js")
    for state in ("unconfigured", "wrong-origin", "insecure-origin",
                  "sign-in-failed"):
        assert state in said, f"the page has no sentence for {state}"
        assert f'"{state}"' in source, \
            f"identity.js never answers {state}, so that sentence is unreachable"


# ---------------------------------------------- what the banner is allowed to say

def test_the_banner_claims_nothing_the_page_has_not_measured():
    """The band used to say everything came from the contract mock and nobody
    was signed in. Both stop being true, and at different times. So the page
    carries a sentence per answer, hidden, and shows the one that matches what
    it found when it asked."""
    claims = {element.get("data-behind"): element
              for element in page.carrying(HTML, "data-behind")}
    for wanted in ("unknown", "mock", "service"):
        assert wanted in claims, f"the band has no sentence for {wanted}"
    assert "hidden" in claims["mock"].attrs, \
        "the page claims the contract mock before it has asked anything"
    assert "hidden" in claims["service"].attrs, \
        "the page claims the real service before it has asked anything"
    assert "hidden" not in claims["unknown"].attrs, \
        "the band starts with nothing shown, so a reader with a slow API is " \
        "told nothing about where the record came from"


def test_the_page_finds_out_what_is_behind_the_api_the_way_this_suite_does():
    """A call carrying a token nothing issued, which is what api.js sends once
    on every load. The token is read out of that file rather than written again
    here, and the three answers are sorted the same way it sorts them, so this
    suite and the page cannot measure different things about one stack.
    """
    found = behind_the_api()
    if found == "mock":
        assert "contract mock" in HTML, \
            "nothing behind /v1 checked a token nobody issued, which makes it " \
            "the contract mock, and the page has no sentence saying so"
    elif found == "service":
        assert "members API" in HTML, \
            "/v1 refused a token nobody issued, which makes it a real service, " \
            "and the page has no sentence saying so"
    else:
        assert "Nothing has answered the members API" in HTML, \
            "nothing is behind /v1 on this stack and the page has no sentence " \
            "for not knowing, so it would claim one of the two"


# ---------------------------------------------------------- the one write path

def test_the_first_sign_in_offers_the_operation_the_contract_declares():
    """A person who has never been here has no member record and the API refuses
    every view with the same refusal. The block for it carries the one control
    that fixes it, and what that control sends is what the contract asks for."""
    assert 'id="api-no-member-record"' in HTML, \
        "no block for the refusal a first sign in gets"
    claims = [element for element in page.carrying(HTML, "data-claim-member")]
    assert claims, "that block offers no control, so it is a dead end"
    assert claims[0].name == "button", \
        f"the control is a {claims[0].name}, and only a button writes anything"

    contract = (ROOT / "docs" / "api" / "members-v1.yaml").read_text()
    assert "operationId: createMe" in contract, \
        "the contract declares no POST /me, so this page offers an operation " \
        "that does not exist. Rule 10"
    schema = contract[contract.index("    FirstSignIn:"):]
    required = re.search(r"required: \[([^\]]+)\]", schema).group(1)
    sent = fetch("/api.js").body
    for field in [name.strip() for name in required.split(",")]:
        assert f"{field}:" in sent, \
            f"FirstSignIn requires {field} and api.js never sends it"


def test_the_refusal_the_page_acts_on_is_the_one_the_service_raises():
    """The portal picks its block by the slug at the end of the problem type.
    Read out of the service rather than copied, because a slug renamed on one
    side and not the other turns the one actionable refusal into a dead end."""
    problems = (ROOT / "services" / "api" / "app" / "problems.py").read_text()
    slug = re.search(r'NO_MEMBER_RECORD = Problem\(\s*slug="([^"]+)"',
                     problems).group(1)
    renderer = fetch("/render.js").body
    assert f'"/{slug}"' in renderer, \
        f"the service raises {slug} and the renderer looks for something else"


def test_the_stack_under_test_answers_the_first_sign_in_in_a_shape_a_page_shows():
    """Whatever answers POST /me has to answer in JSON, because the block the
    page shows is bound to fields in a problem detail. Caddy's own 404 is plain
    text, and a page handed that shows an empty box. Nothing to ask when nothing
    is routed at /v1, so that case returns rather than failing.
    """
    if behind_the_api() == "unknown":
        return
    answer = signed_in("/v1/me", method="POST", body={"name": "Fixture Member"})
    try:
        json.loads(answer.body)
    except ValueError:
        raise AssertionError(
            f"POST /v1/me answered {answer.status} and the body was not JSON, "
            "so the page has nothing to show a member on a first sign in"
        ) from None


if __name__ == "__main__":
    sys.exit(harness.run(globals(), "sign in"))
