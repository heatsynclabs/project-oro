#!/usr/bin/env python3
"""The way in: the screens a person actually meets, and the policy behind them.

Split out of check_reconfiguration.py, which reached the 300 line ceiling in
rule 6. That file is what a second run of configure.py does to what the first
one registered. This one is what a person gets when they arrive: the wall the
administrator account is behind, the sign up the screens offer, and the login
policy that decides whether they do.

Nothing here sends mail. A screen asking for an emailed code is a screen nobody
gets past without a mail server, which is what compose.development.yaml runs a
catcher for and what check_mail.py covers.

    ORO_IDENTITY_URL=... ORO_IDENTITY_TOKEN=... \\
      python3 tools/identity/tests/check_the_way_in.py

tools/identity/tests/run.sh starts a stack, configures it, and runs this.
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
MEMBERS_ORIGIN = os.environ.get("ORO_MEMBERS_ORIGIN", "http://localhost:8080")


def _project() -> str:
    found = registrations.project_named(configure.PROJECT, TOKEN)
    assert found, f"there is no project named {configure.PROJECT!r}"
    return found["projectId"]


def _portal(portal) -> dict:
    found = registrations.application_named(_project(), portal.name, TOKEN)
    assert found, f"there is no application named {portal.name!r}"
    return found



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


def _turn_registration_off() -> None:
    """Put the instance in the state open_self_registration exists to leave.

    allowRegister is true on a fresh 4.17.1 instance, so every check below
    passed against an instance the step had never touched, and deleting the
    call in configure.py turned none of them red. This is what makes them
    checks. The write is the whole policy, per login_policy.FIELDS, because a
    field left out of it comes back false.
    """
    policy = login_policy.held(TOKEN)
    wanted = {field: policy[field] for field in login_policy.FIELDS
              if field in policy}
    wanted["allowRegister"] = False
    answer = api.call(login_policy.POLICY, wanted, TOKEN, method="PUT")
    assert answer.status == 200, (
        f"registration could not be turned off, so what follows would be "
        f"asserting a default: {answer.status} {answer.message()}")
    assert not login_policy.self_registration_is_on(login_policy.held(TOKEN)), (
        "the write was accepted and registration is still on")


def test_the_step_turns_registration_on_and_a_second_run_reports_it_correct():
    """Both halves, from the state the step is for.

    The second half is the property that decides whether anybody dares re-run
    the step: a configuration step people are afraid to run twice stops being
    run.
    """
    _turn_registration_off()

    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        login_policy.open_self_registration(TOKEN)
    assert "turned on" in said.getvalue(), (
        f"the step said {said.getvalue().strip()!r} against an instance with "
        "registration off, so it is not what turns it on")
    assert login_policy.self_registration_is_on(login_policy.held(TOKEN)), (
        "the step reported turning it on and it is still off")

    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        login_policy.open_self_registration(TOKEN)
    assert "already on" in said.getvalue(), (
        f"running the step again said {said.getvalue().strip()!r} rather than "
        "finding self registration already on, so it writes on every run")


def test_turning_registration_on_left_the_rest_of_the_policy_alone():
    """The update replaces the whole policy, so a partial send blanks it: a
    field left out of that request reads as false, and sending allowRegister
    alone would turn password sign in off and lock every member out.

    Off and on again first, so this reads a policy the step wrote rather than
    the one the instance shipped with.
    """
    _turn_registration_off()
    login_policy.open_self_registration(TOKEN)
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
