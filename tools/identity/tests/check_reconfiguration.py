#!/usr/bin/env python3
"""Prove that running tools/identity/configure.py again is exact.

The other configuration suite proves what one run registered. This one proves
what a second run does to it, which is the property that decides whether anybody
dares run the step against a deployment that is already carrying members.

Everything it registers is held under an identifier the step chose itself. That
is what makes a second run exact: it reads back the thing it made rather than
searching for something with the right name and hoping one came back. A portal
is built with its client id compiled into it, so a re-run that mints a second
client is a re-run that signs everybody out.

    ORO_IDENTITY_URL=... ORO_IDENTITY_TOKEN=... \\
      python3 tools/identity/tests/check_reconfiguration.py

tools/identity/tests/run.sh starts a stack, configures it twice, and runs this.
"""
from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import api                       # noqa: E402, after the path insert above
import flow                      # noqa: E402
import login_policy              # noqa: E402
import registrations             # noqa: E402
import clients                   # noqa: E402
import configure                 # noqa: E402

TOKEN = os.environ.get("ORO_IDENTITY_TOKEN", "")

# The origin a member's browser would be on. Nothing has to be listening there:
# what the screens are asked for is a login form and a code, not a page to land
# on afterwards.
MEMBERS_ORIGIN = os.environ.get("ORO_MEMBERS_ORIGIN", "http://localhost:8080")

# The one portal nothing else drives. check_configuration.py signs a member in
# through the members portal, so moving that portal's origin underneath it would
# fail a check about something else entirely and send the reader to the wrong
# place.
MOVEABLE = clients.PORTALS[2]

# Nothing is listening there. What is under test is what the identity service
# holds, not whether a browser could reach it.
SOMEWHERE_ELSE = "http://localhost:8099"


def _project() -> str:
    found = registrations.project_named(configure.PROJECT, TOKEN)
    assert found, f"there is no project named {configure.PROJECT!r}"
    return found["projectId"]


def _portal(portal) -> dict:
    found = registrations.application_named(_project(), portal.name, TOKEN)
    assert found, f"there is no application named {portal.name!r}"
    return found


def _configure_again(portal, origin: str) -> None:
    """One step of a re-run, with its progress report swallowed.

    configure.py prints a line per client, and those lines interleaved with FAIL
    lines read as though the suite itself had said them.

    It also ends the process when a call is refused, which is what a person
    running the command wants and not what this wants. SystemExit is a
    BaseException, so it goes straight past the harness below and ends the run
    with no FAIL line and no count.
    """
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            clients.ensure_app(_project(), portal, origin, TOKEN)
    except SystemExit as refused:
        raise AssertionError(
            f"configuring {portal.name} again was refused: {refused}") from None


def test_the_project_is_held_under_the_identifier_the_step_chose():
    answer = registrations.get_project(configure.PROJECT_ID, TOKEN)
    assert answer.status == 200, (
        f"nothing is held under the project identifier {configure.PROJECT_ID!r}: "
        f"{answer.status} {answer.message()}. A step that has to find its own "
        "project by name cannot tell it apart from another of the same name")
    assert answer.body["project"]["name"] == configure.PROJECT, answer.body


def test_every_portal_is_held_under_the_identifier_the_step_chose():
    for portal in clients.PORTALS:
        answer = registrations.get_application(portal.identifier, TOKEN)
        assert answer.status == 200, (
            f"nothing is held under the application identifier "
            f"{portal.identifier!r}: {answer.status} {answer.message()}")
        assert answer.body["application"]["name"] == portal.name, answer.body


def test_the_door_service_is_held_under_the_identifier_the_step_chose():
    answer = registrations.get_user(clients.DOOR_SERVICE_ID, TOKEN)
    assert answer.status == 200, (
        f"nothing is held under the account identifier "
        f"{clients.DOOR_SERVICE_ID!r}: {answer.status} {answer.message()}")
    assert answer.body["user"]["username"] == clients.DOOR_SERVICE, answer.body


def test_configuring_again_leaves_one_application_per_portal():
    """Two runs, three clients. A fourth is a portal nobody is signing in to."""
    listed = registrations.application_call(
        "ListApplications",
        {"filters": [{"projectIdFilter": {"projectId": _project()}}]}, TOKEN)
    assert listed.status == 200, listed.message()
    names = [app["name"] for app in listed.body.get("applications") or []]
    for portal in clients.PORTALS:
        assert names.count(portal.name) == 1, (
            f"the project holds {names.count(portal.name)} applications named "
            f"{portal.name!r}. All of them: {names}")


def test_configuring_again_does_not_change_a_portal_client_id():
    """The client id is compiled into the portal, so a new one signs everybody out."""
    portal = clients.PORTALS[0]
    before = _portal(portal)["oidcConfiguration"]
    origin = before["redirectUris"][0].rstrip("/")
    _configure_again(portal, origin)
    after = _portal(portal)["oidcConfiguration"]
    assert after["clientId"] == before["clientId"], (
        f"{portal.name} was given a new client id, {before['clientId']} became "
        f"{after['clientId']}, so every browser holding the old one is refused")


def test_a_changed_origin_is_applied_and_can_be_put_back():
    """A redirect somebody edited by hand is put back by the next run.

    The update refuses a request whose name matches the name it already holds,
    and it refuses it before looking at the OIDC configuration, so a real change
    sent alongside an unchanged name is dropped and answered "No changes".
    Measured against 4.17.1 on 2026-08-29. Nothing else in either suite would
    notice, because everything else reads a configuration that was right on the
    first run.
    """
    original = _portal(MOVEABLE)["oidcConfiguration"]["redirectUris"][0].rstrip("/")
    try:
        _configure_again(MOVEABLE, SOMEWHERE_ELSE)
        moved = _portal(MOVEABLE)["oidcConfiguration"]["redirectUris"]
        assert moved == [SOMEWHERE_ELSE + "/"], (
            f"{MOVEABLE.name} still redirects to {moved}, so a configuration "
            "change was reported as applied and was not")
    finally:
        _configure_again(MOVEABLE, original)
    back = _portal(MOVEABLE)["oidcConfiguration"]["redirectUris"]
    assert back == [original + "/"], f"{MOVEABLE.name} redirects to {back}"


# --------------------------------------------------------------------------
# The way in. Nothing here configures SMTP, so a screen asking for an emailed
# code is a screen nobody gets past.

# Invented, used by nothing outside this run. Both satisfy the default policy of
# eight characters with an uppercase, a lowercase, a number and a symbol.
HANDOVER_PASSWORD = "Handover-Probe-1!"
CHOSEN_PASSWORD = "Chosen-By-The-Member-2!"


def _members_client_id() -> str:
    return _portal(clients.PORTALS[0])["oidcConfiguration"]["clientId"]


def _login_name_of(username: str) -> str:
    """What the service signs a configured username in as: a username with no
    domain gets the organisation domain appended, so `fixture-admin` signs in
    as `fixture-admin@heatsync-labs.localhost`.
    """
    listed = api.call("/v2/users", {}, TOKEN)
    assert listed.status == 200, listed.message()
    for user in listed.body.get("result") or []:
        for name in user.get("loginNames") or []:
            if name == username or name.startswith(username + "@"):
                return name
    raise AssertionError(f"nothing on this instance signs in as {username!r}")


def _account_asked_to_change_its_password() -> str:
    """The wall compose.yaml puts the administrator behind, on our own account."""
    run = os.environ.get("ORO_IDENTITY_RUN", str(os.getpid()))
    login = f"first-password-change-{run}@fixture.invalid"
    made = api.call("/v2/users/human", {
        "username": login,
        "profile": {"givenName": "First", "familyName": "Change"},
        "email": {"email": login, "isVerified": True},
        "password": {"password": HANDOVER_PASSWORD, "changeRequired": True},
    }, TOKEN)
    assert made.status == 200, f"the fixture account was refused: {made.body}"
    return login


def test_a_first_password_change_can_be_finished_through_the_screens():
    """compose.yaml hands a password over and asks for it to be replaced.

    That is the point of the value in .env: it stops being the credential the
    moment somebody uses it. A person finishes that screen. Until 2026-08-31
    flow.py could not, because it answered three password fields with one.
    """
    tokens = flow.sign_in_and_change_the_password(
        _members_client_id(), MEMBERS_ORIGIN,
        _account_asked_to_change_its_password(),
        flow.Passwords(HANDOVER_PASSWORD, CHOSEN_PASSWORD))
    assert tokens.status == 200, (
        f"the change password screen was not finished: {tokens.body}")
    assert "access_token" in tokens.body, tokens.body


def test_the_administrator_compose_creates_can_sign_in_from_cold():
    """make up ends with this account, and it is the only way to administer.

    Signing in spends its forced password change, so it wants a stack nobody
    is using. tools/identity/tests/run.sh names a throwaway one.
    """
    username = os.environ.get("ORO_IDENTITY_ADMIN_USERNAME", "")
    password = os.environ.get("ORO_IDENTITY_ADMIN_PASSWORD", "")
    if not username or not password:
        print("NOT CHECKED that the administrator can sign in: nothing named "
              "one. ORO_IDENTITY_ADMIN_USERNAME and ORO_IDENTITY_ADMIN_PASSWORD "
              "name the pair compose.yaml got, and spend its password change.")
        return
    tokens = flow.sign_in_and_change_the_password(
        _members_client_id(), MEMBERS_ORIGIN, _login_name_of(username),
        flow.Passwords(password, CHOSEN_PASSWORD))
    assert tokens.status == 200, (
        f"the administrator {username!r} could not sign in: {tokens.body}")


def test_the_login_screens_offer_a_sign_up():
    """This site replaces one with a sign up on it, so it needs one.

    It was turned off for a day, on the reasoning that a Register button with no
    mail server behind it is a dead end. The dead end was real: registering ends
    at a screen asking for a code, and that screen carries a required code field,
    Next and Resend Code, and nothing else. Measured on 2026-08-31. The answer is
    a mail server, which compose.development.yaml runs as a catcher, rather than
    taking the door away.
    """
    status, page = flow.sign_in_page(_members_client_id(), MEMBERS_ORIGIN)
    assert status == 200, f"the sign in page answered {status}"
    assert 'name="register"' in page, (
        "the screen a member is sent to offers no way to join, so somebody who "
        "has never been here has to ask an admin for an account")


def test_self_registration_is_on_and_a_second_run_reports_it_correct():
    """The property that decides whether anybody dares re-run the step."""
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        login_policy.open_self_registration(TOKEN)
    assert "already on" in said.getvalue(), (
        f"running the step again said {said.getvalue().strip()!r} rather than "
        "finding self registration already on, so it writes on every run")
    assert login_policy.self_registration_is_on(login_policy.held(TOKEN)), (
        "the screens offer no way to join")


def test_turning_registration_on_left_the_rest_of_the_policy_alone():
    """The update replaces the whole policy, so a partial send blanks it: a
    field left out of that request reads as false, and sending allowRegister
    alone would turn password sign in off and lock every member out.
    """
    policy = login_policy.held(TOKEN)
    assert policy.get("allowUsernamePassword") is True, (
        f"password sign in is off: {policy}")
    assert policy.get("hidePasswordReset") is not True, (
        "the forgotten password link was hidden too, and nothing here was "
        f"asked to hide it: {policy}")


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
    sys.exit(_run())
