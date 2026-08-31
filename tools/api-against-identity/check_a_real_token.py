#!/usr/bin/env python3
"""Does the members API accept a token the identity service actually issued.

Everything the members API had been checked against until this suite was a
token this repository minted with a key of its own, which answers a narrower
question than anybody wanted: whether the service can verify its own signature.
The question here is whether a member who signs in on the real hosted screens
can then read their own record, and whether the three tokens that must be
refused are.

    tools/api-against-identity/run.sh

Four sign ins happen before any check runs, each one all the way through the
screens a member is served. Two of them are the same person, differing only in
which client they arrived through, so a check about the audience changes one
thing and nothing else. The fourth is the person POST /me is for: a real
account the members database has never met.

The minting the harness does here is only ever forgery. Both key settings it
reads name the same stranger's key, because nothing this suite signs is meant
to be accepted.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "identity"))
sys.path.insert(0, str(ROOT / "services" / "api" / "tests"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import api                       # noqa: E402, after the path inserts above
import configure                 # noqa: E402
import flow                      # noqa: E402
import harness                   # noqa: E402
import registrations             # noqa: E402
import make_the_fixtures         # noqa: E402

TOKEN = api.token_from_environment()
ORIGIN = make_the_fixtures.ORIGIN

# What run.sh gave the api container, and what the members row it wrote holds.
AUDIENCE = os.environ["ORO_API_TEST_AUDIENCE"]
ISSUER = os.environ["ORO_API_TEST_ISSUER"]
MEMBER_ID = os.environ["ORO_MEMBER_ID"]

ERRORS = "https://oro.heatsynclabs.org/errors/"

STATE: dict = {}


def claims_on(access_token: str) -> dict:
    payload = access_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(
        payload + "=" * (-len(payload) % 4)))


def key_id_on(access_token: str) -> str:
    header = access_token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(
        header + "=" * (-len(header) % 4)))["kid"]


def signed_in() -> dict:
    assert not STATE.get("error"), STATE["error"]
    return STATE


def refusal_on(access_token: str) -> dict:
    """What the API answered, required to be a refusal in the contract's shape.

    A service that has fallen over refuses everything, so the status alone is
    not evidence. app/problems.py promises a problem detail carrying a slug and
    a sentence, and reading the slug is what tells a refusal apart from a
    collapse.
    """
    answer = harness.fetch("/me", access_token)
    assert answer.status == 401, f"it answered {answer.status}: {answer.body}"
    body = answer.json()
    assert body.get("type", "").startswith(ERRORS), body
    return body


# --------------------------------------------------------------------------
# The chain this suite exists to prove.

def test_a_member_who_signed_in_reads_their_own_record():
    """The whole point. A real token, the real API, and the member's own row."""
    answer = harness.fetch("/me", signed_in()["access_token"])
    assert answer.status == 200, f"{answer.status}: {answer.body}"
    me = answer.json()
    assert me["id"] == MEMBER_ID, me
    assert me["email"] == make_the_fixtures.MEMBER["login"], me
    assert me["name"] == make_the_fixtures.MEMBER["name"], me


def test_the_token_was_issued_by_the_provider_and_not_by_this_suite():
    """A guard on every check below, which are worth nothing without it.

    The key id is the provider's own, the issuer is the origin it was
    configured with, and the subject is the one the members row was written
    for. A suite that had quietly fallen back to minting its own token would
    fail here rather than passing everything.
    """
    held = signed_in()
    assert claims_on(held["access_token"])["iss"] == ISSUER, "wrong issuer"
    assert claims_on(held["access_token"])["sub"] == held["subject"]
    assert key_id_on(held["access_token"]) != harness.KEY_ID, (
        "the token carries this suite's own key id, so nothing below is "
        "measuring the identity service")


def test_the_audience_the_api_demands_is_the_one_a_real_token_carries():
    """Which value that is was measured rather than chosen.

    A real access token from this instance carries a list: the client id of
    every application in the project, and the project's own identifier. The
    identifier is the half this repository chooses, in configure.PROJECT_ID,
    and the client ids are generated per instance, so the project id is the
    only one an api container can be configured with ahead of time.
    """
    carried = claims_on(signed_in()["access_token"])["aud"]
    assert isinstance(carried, list), f"aud is {carried!r}"
    assert configure.PROJECT_ID in carried, carried
    assert AUDIENCE == configure.PROJECT_ID, (
        f"the api was configured to demand {AUDIENCE!r}, and the project this "
        f"identity service issues tokens for is {configure.PROJECT_ID!r}")


def test_the_same_token_reads_the_directory():
    """Not one endpoint. The token is what the service accepted, not the path."""
    answer = harness.fetch("/members", signed_in()["access_token"])
    assert answer.status == 200, f"{answer.status}: {answer.body}"


# --------------------------------------------------------------------------
# The three refusals. A suite showing only the happy path proves half of it.

def test_a_token_for_another_project_on_the_same_instance_is_refused():
    """Right issuer, right signing key, wrong audience.

    The same person, signed in a second time through a client belonging to a
    project this repository does not own. Everything about it is real except
    who it was minted for.
    """
    held = signed_in()
    carried = claims_on(held["another_project_token"])
    assert carried["iss"] == ISSUER, carried
    assert carried["sub"] == held["subject"], carried
    assert AUDIENCE not in carried["aud"], (
        f"the other project's token carries {AUDIENCE!r} too, so this check is "
        "not asking about the audience")
    body = refusal_on(held["another_project_token"])
    assert body["type"] == ERRORS + "unauthenticated", body


def test_a_token_naming_a_key_the_provider_never_published_is_refused():
    """Refused from the key set already in memory, at no outbound cost.

    app/identity.py turns an unknown key id away without reading the provider's
    JWKS, because a caller who can sign nothing could otherwise choose the
    moment the service makes a request.
    """
    forged = harness.mint(signed_in()["subject"])
    assert key_id_on(forged) == harness.KEY_ID
    body = refusal_on(forged)
    assert body["type"] == ERRORS + "unauthenticated", body


def test_a_stranger_signature_under_the_provider_key_id_is_refused():
    """The same key id the real token carries, and somebody else's signature.

    The check above stops at the key id, so on its own it would pass against a
    service that never verified a signature at all.
    """
    held = signed_in()
    header = {"alg": "RS256", "typ": "JWT",
              "kid": key_id_on(held["access_token"])}
    forged = harness.signed_token(header, harness.token_claims(held["subject"]))
    body = refusal_on(forged)
    assert body["type"] == ERRORS + "unauthenticated", body


def test_a_first_sign_in_writes_a_member_record_for_a_real_sign_in():
    """POST /me, with a subject the members database has genuinely never met.

    This suite is the only place that subject exists. The one in
    services/api/tests mints its own tokens, so a check there proves the
    operation and not that the person on the other end of it is real.
    """
    held = signed_in()
    made = harness.fetch("/me", held["newcomer_token"], method="POST",
                         body={"name": make_the_fixtures.NEWCOMER["name"],
                               "email": make_the_fixtures.NEWCOMER["login"]})
    assert made.status == 201, f"{made.status}: {made.body}"
    assert made.json()["name"] == make_the_fixtures.NEWCOMER["name"], made.body
    STATE["newcomer_member_id"] = made.json()["id"]

    read = harness.fetch("/me", held["newcomer_token"])
    assert read.status == 200, f"{read.status}: {read.body}"
    assert read.json()["id"] == STATE["newcomer_member_id"], read.body


def test_a_second_first_sign_in_answers_the_same_record():
    """Idempotent, which is what lets a portal send it on every sign in.

    It runs after the check above, because the names sort that way, and it
    depends on that: the record has to exist for the second call to be a
    second call.
    """
    held = signed_in()
    again = harness.fetch("/me", held["newcomer_token"], method="POST",
                          body={"name": "Somebody Else Entirely"})
    assert again.status == 200, f"{again.status}: {again.body}"
    assert again.json()["id"] == STATE["newcomer_member_id"], again.body
    assert again.json()["name"] == make_the_fixtures.NEWCOMER["name"], (
        f"the second call rewrote the name: {again.body}")


def test_a_sign_in_that_matches_no_member_row_is_told_so():
    """A real token, verified, for somebody the members database has never met.

    Nothing in the contract can join the two, so this is the end of the road
    rather than a step on it, and the sentence says that. services/api/README.md
    carries the gap and contract-review-notes.md finding 5 is the same gap from
    the contract's side.
    """
    body = refusal_on(signed_in()["stranger_token"])
    assert body["type"] == ERRORS + "no-member-record", body


# --------------------------------------------------------------------------

def sign_in(person: dict, application: str) -> str:
    held = registrations.get_application(application, TOKEN)
    assert held.status == 200, f"{application}: {held.status} {held.message()}"
    client_id = held.body["application"]["oidcConfiguration"]["clientId"]
    tokens = flow.sign_in_through_the_screens(
        client_id, ORIGIN, person["login"], person["password"])
    assert tokens.status == 200, f"the sign in failed: {tokens.body}"
    return tokens.body["access_token"]


def sign_everybody_in() -> None:
    """Four whole sign ins, before any check reads anything.

    Done once rather than per check, because each one drives three screens and
    a suite that signed in eight times would spend most of its run there.
    """
    members_portal = configure.PORTALS[0].identifier
    STATE["access_token"] = sign_in(make_the_fixtures.MEMBER, members_portal)
    STATE["subject"] = claims_on(STATE["access_token"])["sub"]
    STATE["another_project_token"] = sign_in(
        make_the_fixtures.MEMBER, make_the_fixtures.OTHER_APP_ID)
    STATE["stranger_token"] = sign_in(make_the_fixtures.STRANGER, members_portal)
    STATE["newcomer_token"] = sign_in(make_the_fixtures.NEWCOMER, members_portal)


if __name__ == "__main__":
    if not TOKEN:
        print("No ORO_IDENTITY_TOKEN, so nothing was checked.", file=sys.stderr)
        sys.exit(1)
    try:
        sign_everybody_in()
    except Exception as stopped:      # noqa: BLE001
        # Recorded rather than raised. A traceback here would hide which checks
        # were never reached, and the most likely reason a sign in stops is a
        # login screen answering something other than a form.
        STATE["error"] = f"{type(stopped).__name__}: {stopped}"
    sys.exit(harness.run(globals(), "members API against the identity service"))
