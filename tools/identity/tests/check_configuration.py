#!/usr/bin/env python3
"""Prove what tools/identity/configure.py registered, by using it.

The other file in this directory proves the identity service can hold the
passwords the lab already has. This one proves a member can sign in with one:
the clients exist and have the shape docs/plan/api-design.md section 2 asks
for, the screens a member is sent to are really served, and one whole
authorization code flow ends in tokens that behave the way phase 2 promises.

Nothing here reads a configuration file to see what was asked for. Every check
asks the service what it holds, because a create call that returned 200 and a
service that holds the right thing are different claims.

    ORO_IDENTITY_URL=... ORO_IDENTITY_TOKEN=... \\
      python3 tools/identity/tests/check_configuration.py

tools/identity/tests/run.sh starts a stack, configures it, and runs this.
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import api                       # noqa: E402, after the path insert above
import registrations             # noqa: E402
import flow                      # noqa: E402
import clients                   # noqa: E402
import branding                  # noqa: E402
import configure                 # noqa: E402

TOKEN = os.environ.get("ORO_IDENTITY_TOKEN", "")
MEMBERS_ORIGIN = os.environ.get("ORO_MEMBERS_ORIGIN", "http://localhost:8080")

MEMBER = {"login": "", "password": "Configuration-Probe-Passw0rd!"}
STATE: dict = {}


def _project() -> str:
    found = registrations.project_named(configure.PROJECT, TOKEN)
    assert found, f"there is no project named {configure.PROJECT!r}"
    return found["projectId"]


def _app(name: str) -> dict:
    found = registrations.application_named(_project(), name, TOKEN)
    assert found, f"there is no application named {name!r}"
    return found["oidcConfiguration"]


# --------------------------------------------------------------------------
# The clients, read back from the service rather than from what was sent.

def test_the_three_portals_are_registered():
    for portal in clients.PORTALS:
        _app(portal.name)


def test_every_portal_is_a_public_client_holding_no_secret():
    """PKCE stands in for the secret, because these are pages a browser downloads.

    A secret shipped inside a downloadable page is not a secret, and a client
    that has one is a client somebody can impersonate. There is no field in the
    read back for a secret, so the second half asks the service instead. Client
    credentials is the grant a secret alone completes, and a portal completing
    it would mean it holds one.
    """
    for portal in clients.PORTALS:
        config = _app(portal.name)
        assert config["authMethodType"] == "OIDC_AUTH_METHOD_TYPE_NONE", \
            f"{portal.name} uses {config['authMethodType']}"
        alone = api.post_form("/oauth/v2/token", {
            "grant_type": "client_credentials", "scope": "openid",
            "client_id": config["clientId"]})
        assert alone.status >= 400, (
            f"{portal.name} was given a token for its client id on its own, so "
            "it is not the public client it is registered as")


def test_every_portal_uses_authorization_code_and_can_refresh():
    for portal in clients.PORTALS:
        config = _app(portal.name)
        assert config["responseTypes"] == ["OIDC_RESPONSE_TYPE_CODE"], portal.name
        assert "OIDC_GRANT_TYPE_AUTHORIZATION_CODE" in config["grantTypes"], portal.name
        assert "OIDC_GRANT_TYPE_REFRESH_TOKEN" in config["grantTypes"], (
            f"{portal.name} cannot refresh, so a member is signed out every ten "
            "minutes")


def test_the_door_service_is_a_machine_account_and_not_an_application():
    """It talks to no browser, so it has no redirect and no login screen."""
    users = api.call("/v2/users", {"queries": [
        {"userNameQuery": {"userName": clients.DOOR_SERVICE}}]}, TOKEN)
    assert users.status == 200, users.message()
    assert users.body.get("result"), f"there is no {clients.DOOR_SERVICE} account"
    assert registrations.application_named(_project(), "Door service", TOKEN) is None, \
        "the door service was registered as an application as well"


# --------------------------------------------------------------------------
# The screens. This is the check that catches a service nobody can sign in to.

def test_a_member_is_sent_to_a_page_that_serves_a_login_form():
    """The whole point of the identity service, and the easiest thing to break.

    Zitadel 4.17.1 defaults its hosted screens to a version this image does not
    serve, and the redirect then lands on a 404. Everything else in this suite
    passed while that was true, because everything else speaks to the API.
    """
    status, page = flow.sign_in_page(_app("Members portal")["clientId"],
                                     MEMBERS_ORIGIN)
    assert status == 200, f"the sign in page answered {status}"
    assert 'name="loginName"' in page, (
        "the page a member is sent to has no field to type a login name into. "
        "If it says an internal error occurred, read HANDOFF.md section 7")


def test_the_branding_reaches_the_login_screen():
    """Set is not the same as activated, and activated is not the same as served.

    So this reads the stylesheet the screens actually load and looks for the
    accent colour out of packages/gantry-tokens/tokens.css in it.
    """
    organisation = api.call("/v2/organizations/_search", {}, TOKEN).body["result"][0]["id"]
    status, css = flow.fetch_page(
        f"/ui/login/resources/dynamic?orgId={organisation}"
        "&default-policy=false&filename=policy/label/css/variables.css")
    assert status == 200, f"the branding stylesheet answered {status}"
    red, green, blue = (int(branding.POLICY["primaryColor"][i:i + 2], 16)
                        for i in (1, 3, 5))
    assert f"rgb({red}, {green}, {blue})" in css, (
        f"the login screens do not carry {branding.POLICY['primaryColor']}. A label "
        "policy that was set and never activated reads as applied and changes "
        "nothing")


# --------------------------------------------------------------------------
# One whole sign in, and what the tokens do afterwards.

def test_a_member_can_sign_in_and_gets_a_refresh_token():
    assert not STATE.get("error"), STATE["error"]
    tokens = STATE["tokens"]
    assert "access_token" in tokens, tokens
    assert "refresh_token" in tokens, (
        "signing in returned no refresh token, so a member is signed out every "
        "ten minutes")


def test_the_access_token_can_be_validated_without_calling_back():
    """A JWT, not an opaque token.

    docs/plan/api-design.md section 2 has both APIs validating tokens offline
    against the published JWKS. Zitadel's default is an opaque token, which is
    five segments of encrypted nothing to anybody who cannot ask it, and asking
    it is what offline validation exists to avoid. The door service in
    particular has to verify a token during an internet outage.
    """
    assert not STATE.get("error"), STATE["error"]
    token = STATE["tokens"]["access_token"]
    assert token.count(".") == 2, (
        f"the access token has {token.count('.') + 1} segments, so it is not a "
        "JWT and no service can check it without calling the identity service")


def test_the_access_token_from_a_sign_in_lasts_ten_minutes():
    assert not STATE.get("error"), STATE["error"]
    assert STATE["tokens"]["expires_in"] in (599, 600), \
        f"it lasts {STATE['tokens']['expires_in']} seconds"


def test_using_a_refresh_token_rotates_it():
    assert not STATE.get("error"), STATE["error"]
    assert STATE["refreshed"]["refresh_token"] != STATE["tokens"]["refresh_token"], \
        "the same refresh token came back, so nothing rotated"


def test_the_previous_refresh_token_stops_working():
    """Rotation without invalidation is not rotation.

    A stolen refresh token that keeps working alongside its replacement is the
    whole thing rotation exists to stop.
    """
    assert not STATE.get("error"), STATE["error"]
    again = api.post_form("/oauth/v2/token", {
        "grant_type": "refresh_token",
        "refresh_token": STATE["tokens"]["refresh_token"],
        "client_id": STATE["client_id"]})
    assert again.status == 400, \
        f"the old refresh token still works, and answered {again.status}"


def _sign_in_once() -> None:
    """Everything the flow checks above read, done once before any of them run.

    A real sign in, through the pages a member is served, with a password that
    was never anything but this fixture's.
    """
    run = os.environ.get("ORO_IDENTITY_RUN", str(os.getpid()))
    MEMBER["login"] = f"configuration-probe-{run}@fixture.invalid"
    api.call("/v2/users/human", {
        "username": MEMBER["login"],
        "profile": {"givenName": "Configuration", "familyName": "Probe"},
        "email": {"email": MEMBER["login"], "isVerified": True},
        "password": {"password": MEMBER["password"], "changeRequired": False},
    }, TOKEN)
    client_id = _app("Members portal")["clientId"]
    STATE["client_id"] = client_id
    tokens = flow.sign_in_through_the_screens(
        client_id, MEMBERS_ORIGIN, MEMBER["login"], MEMBER["password"])
    assert tokens.status == 200, f"the sign in failed: {tokens.body}"
    STATE["tokens"] = tokens.body
    refreshed = api.post_form("/oauth/v2/token", {
        "grant_type": "refresh_token",
        "refresh_token": tokens.body["refresh_token"], "client_id": client_id})
    assert refreshed.status == 200, f"the refresh failed: {refreshed.body}"
    STATE["refreshed"] = refreshed.body


def _run() -> int:
    checks = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    failed = []
    for name, fn in checks:
        try:
            fn()
        except AssertionError as exc:
            failed.append(name)
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    if not TOKEN:
        print("No ORO_IDENTITY_TOKEN, so nothing was checked.", file=sys.stderr)
        sys.exit(1)
    try:
        _sign_in_once()
    except Exception as stopped:      # noqa: BLE001
        # Recorded rather than raised, so the checks that do not depend on a
        # completed sign in still run and the reader sees which ones those are.
        # A traceback here would hide, for instance, that the login screen is
        # a 404, which is the most likely reason a sign in did not finish.
        STATE["error"] = f"{type(stopped).__name__}: {stopped}"
    sys.exit(_run())
