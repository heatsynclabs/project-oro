#!/usr/bin/env python3
"""What the members portal claims about the API behind it, and the one write.

Split out of check_sign_in.py under the 300 line ceiling in rule 6. That file is
what the page ships and where it reads its client id from. This one is the band
under the masthead, which says what answered /v1, and the first sign in, which
is the only operation this portal calls that writes anything.

Run it against a stack that is already up:

    ORO_PORTAL_URL=http://localhost:8080 python3 tools/members-portal/tests/check_the_band.py

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


def portal_source(name):
    """One of the portal's own files, off disk, with a readable failure."""
    where = PORTAL / name
    assert where.exists(), f"apps/members/{name} is not there"
    return where.read_text()


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


# ---------------------------------------------- what the banner is allowed to say

def test_the_banner_claims_nothing_the_page_has_not_measured():
    """The band used to say everything came from the contract mock and nobody
    was signed in. Both stop being true, and at different times. So the page
    carries a sentence per answer, hidden, and shows the one that matches what
    it found when it asked.

    There is no sentence for the real service, and that is deliberate. A member
    does not need to be told there is an API behind their own record, and a
    caution band on a page where nothing is wrong trains people to ignore the
    band on the day it says something real. The band is a caution band: it has
    a warning mark in it and it stands on the hazard ground.
    """
    claims = {element.get("data-behind"): element
              for element in page.carrying(HTML, "data-behind")}
    for wanted in ("unknown", "mock"):
        assert wanted in claims, f"the band has no sentence for {wanted}"
    assert "service" not in claims, (
        "the band has a sentence for the real service, which is the ordinary "
        "state of this page. A caution shown when nothing is wrong is a "
        "caution nobody reads.")
    assert "hidden" in claims["mock"].attrs, \
        "the page claims the contract mock before it has asked anything"
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
    sys.exit(harness.run(globals(), "band and first sign in"))
