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

What a person meets on the screens moved to check_the_way_in.py when this file
reached the 300 line ceiling in rule 6. This one is what the second run of the
step does to what the first one registered, and nothing else.

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
