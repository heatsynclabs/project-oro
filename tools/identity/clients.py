#!/usr/bin/env python3
"""Registering the three portal clients, and correcting one that has drifted.

Split out of configure.py, which reached the 300 line ceiling in rule 6. That
file is now the order the steps run in; this one is what a client is.
"""
from __future__ import annotations

import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import api              # noqa: E402, after the path insert above
import registrations    # noqa: E402


Portal = collections.namedtuple("Portal", "name flag identifier configuration")

PORTALS = (
    Portal("Members portal", "members", "oro-members-portal",
           "apps/members/identity.json"),
    Portal("Admin portal", "admin", "oro-admin-portal", None),
    Portal("Door app", "door", "oro-door-app", None),
)

# The door service is not an application. It is a machine account on client
# credentials, because nothing about it involves a person at a browser.
DOOR_SERVICE = "door-service"
DOOR_SERVICE_ID = "oro-door-service"


def public_client(origin: str) -> dict:
    return {
        "redirectUris": [origin + "/"],
        "postLogoutRedirectUris": [origin + "/"],
        "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
        "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE",
                       "OIDC_GRANT_TYPE_REFRESH_TOKEN"],
        "applicationType": "OIDC_APP_TYPE_USER_AGENT",
        "authMethodType": "OIDC_AUTH_METHOD_TYPE_NONE",
        # A JWT, because docs/plan/api-design.md section 2 says both APIs
        # validate tokens offline against the published JWKS. The default is an
        # opaque token, which is five segments of encrypted nothing to anybody
        # without a call back to the identity service, and that call is the
        # thing offline validation exists to avoid.
        "accessTokenType": "OIDC_TOKEN_TYPE_JWT",
        # Plain HTTP origins are refused without this, and a laptop has no
        # other kind. On a deployment every origin is https and this changes
        # nothing, so it is set from the origin rather than from a flag nobody
        # would remember to turn off.
        "developmentMode": origin.startswith("http://"),
    }


def held_application(project: str, portal: Portal, token: str) -> dict | None:
    answer = registrations.get_application(portal.identifier, token)
    if answer.status == 200:
        return answer.body["application"]
    if answer.status != 404:
        raise api.Refused(f"{portal.name}: reading the application back was "
                          f"refused: {answer.status} {answer.message()}. "
                          "Nothing was created or changed.")
    older = registrations.application_named(project, portal.name, token)
    if older is not None:
        print(f"{portal.name}: {_GENERATED_INSTEAD} {older['applicationId']}")
    return older


def ensure_app(project: str, portal: Portal, origin: str, token: str) -> dict:
    """Register or correct one client, and give back what the service now holds."""
    held = held_application(project, portal, token)
    wanted = public_client(origin)
    if held is None:
        answer = registrations.application_call("CreateApplication", {
            "projectId": project,
            "applicationId": portal.identifier,
            "name": portal.name,
            "oidcConfiguration": wanted,
        }, token)
        if answer.status != 200:
            raise SystemExit(f"{portal.name}: {answer.status} {answer.message()}")
        print(f"{portal.name}: created")
        # Read back rather than trust the create answer, as every step here does,
        # and refuse rather than reach into a body that has no application in it.
        # Measured on 2026-08-31: against a freshly created instance this read
        # came back without that key and the whole step died on a KeyError, which
        # names nothing a reader can act on.
        written = registrations.get_application(portal.identifier, token)
        if written.status == 200 and "application" in written.body:
            return written.body["application"]
        # The identifier this file chose is not always the one that comes back.
        # Measured on 2026-08-31 against a freshly created instance: the create
        # succeeded and this read did not find it under that identifier, so the
        # step died on a KeyError. Look it up the way an older instance is looked
        # up instead, which is by name, and refuse readably if that fails too.
        older = registrations.application_named(project, portal.name, token)
        if older is not None:
            return older
        raise api.Refused(
            f"{portal.name} was created and could not be read back, under the "
            f"identifier {portal.identifier} or by name. Reading by identifier "
            f"answered {written.status} {written.message()}. The client may well "
            "be registered: run this again, because it is idempotent and the "
            "second run reads what the first one made.")
    update_app(portal, held, wanted, token)
    return held


def update_app(portal: Portal, held: dict, wanted: dict, token: str) -> None:
    """Put back whatever differs, and say so when nothing does."""
    wrong = registrations.differences(held.get("oidcConfiguration", {}), wanted)
    misnamed = held.get("name") != portal.name
    if not wrong and not misnamed:
        print(f"{portal.name}: already correct")
        return

    request = {"applicationId": held["applicationId"],
               "projectId": held["projectId"],
               "oidcConfiguration": wanted}
    # The name is sent only when it is the thing that changed. An update whose
    # name matches the name already held is refused with "No changes" before the
    # OIDC configuration is looked at, so a real redirect change sent alongside
    # an unchanged name is dropped and reported as nothing to do. Measured
    # against 4.17.1 on 2026-08-29: the same request without the name applied.
    if misnamed:
        request["name"] = portal.name

    answer = registrations.application_call("UpdateApplication", request, token)
    if answer.status != 200:
        raise SystemExit(f"{portal.name}: {answer.status} {answer.message()}. "
                         f"What differs: {'; '.join(wrong) or 'the name'}")
    print(f"{portal.name}: updated")


def ensure_door_service(organisation: str, token: str) -> None:
    held = registrations.get_user(DOOR_SERVICE_ID, token)
    if held.status == 200:
        print(f"{DOOR_SERVICE}: already there")
        return
    if held.status != 404:
        raise api.Refused(f"{DOOR_SERVICE}: reading the account back was "
                          f"refused: {held.status} {held.message()}. Nothing "
                          "was created or changed.")

    answer = api.call("/v2/users/new", {
        "organizationId": organisation,
        "userId": DOOR_SERVICE_ID,
        "username": DOOR_SERVICE,
        "machine": {
            "name": "Door service",
            "description": "Reads the card table. docs/plan/api-design.md section 2",
            "accessTokenType": "ACCESS_TOKEN_TYPE_JWT",
        },
    }, token)
    if answer.status == 200:
        print(f"{DOOR_SERVICE}: created")
        return
    # Nothing is held under our identifier, so an account that already exists is
    # one holding the login name, which is the older version of this step under
    # an identifier the service generated. Two answers say that and they say it
    # differently, both measured against 4.17.1 on 2026-08-29: a login name
    # already taken is 409 "User already exists", an identifier already taken is
    # 400 "Errors.User.AlreadyExisting".
    if answer.status == 409 or "AlreadyExisting" in answer.message():
        print(f"{DOOR_SERVICE}: already there, under an identifier the service "
              "generated")
        return
    raise SystemExit(f"{DOOR_SERVICE}: {answer.status} {answer.message()}")
