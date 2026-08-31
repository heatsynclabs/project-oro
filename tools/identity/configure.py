#!/usr/bin/env python3
"""Register what the identity service has to hold, from configuration.

Phase 2 of docs/plan/order-of-operations.md asks for a deployment reproducible
from the compose file plus a database dump, with no console click that is not
also in configuration. The compose file creates the instance, its admin and a
machine account. This creates everything above that: the project, the four
clients docs/plan/api-design.md section 2 specifies, and the GANTRY branding on
the hosted screens.

    tools/identity/configure.py --members-origin http://localhost:8080 \\
      --admin-origin http://localhost:8081 --door-origin http://localhost:8082

Every origin is required and none is derived from another. The three portals do
not share a hostname on a deployment, and guessing one from another is the
mistake ADR 0002 records.

Idempotent. Run it twice and the second run reports every client as already
correct rather than failing, because a configuration step somebody is afraid to
re-run stops being run. Everything it registers is held under an identifier
chosen here rather than one the service generates, so the second run reads back
exactly what the first one made.

Needs a token that can administer the instance. The compose stack writes one to
/bootstrap/pat inside the identity container and `make identity-configure`
copies it out.

Writes one file: apps/members/identity.json, carrying the client id Zitadel
generated for the members portal, which is the only way that portal can know it.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import api              # noqa: E402, after the path insert above
import portal_config    # noqa: E402
import registrations    # noqa: E402

PROJECT = "Project ORO"

# The checkout, so the client id lands beside the portal whatever the cwd is.
ROOT = pathlib.Path(__file__).resolve().parents[2]

# The identifiers this step gives the things it registers. They are ours rather
# than the service's, so a second run addresses what the first one made instead
# of searching by name and hoping one thing came back.
PROJECT_ID = "oro-project"

# What an instance configured before this step chose its own identifiers looks
# like. Adopting what is there beats registering a second one beside it: the
# portals carry the client ids the first run gave them.
_GENERATED_INSTEAD = ("held under an identifier the service generated, which is "
                      "what the older version of this step left behind. Using")

# The project and the clients are registered through the v2 services and the
# branding through the v1 management API, which is not an inconsistency anybody
# gets to fix. Every management method this step used to call is marked
# deprecated in the 4.17.1 image's own embedded descriptors, read on 2026-08-29.
# The three label policy methods are not, and settings v2 can read branding back
# but has nothing that sets it, so the branding stays until Zitadel gives it
# somewhere to go.
#
# The door app is supposed to carry the door API in its audience, per
# docs/plan/api-design.md section 2. Nothing here does that, and nothing can
# yet: an audience is another project's id, the door API has no project, and
# inventing one would be a client pointing at nothing. It arrives in phase 5.

# The three portals, each a public client using authorization code with PKCE,
# per docs/plan/api-design.md section 2. A public client holds no secret: PKCE
# stands in for one, and a secret shipped inside a page a browser downloads is
# not a secret. The redirect is the origin rather than a path under it, because
# the portals are static files with fragment routing and a path would need a
# rewrite in Caddy to survive a reload. The last field is where the client id
# gets written, for a portal that exists and reads it. Only the members portal
# does: the other two are not built, and rule 10 forbids configuration for code
# that is not there.
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


def ensure_project(organisation: str, token: str) -> str:
    held = registrations.get_project(PROJECT_ID, token)
    if held.status == 200:
        print(f"project {PROJECT}: already there")
        return PROJECT_ID
    if held.status != 404:
        raise api.Refused(f"reading the project back was refused: "
                          f"{held.status} {held.message()}. Nothing was created "
                          "or changed. A 401 here is the token rather than the "
                          "project: a revoked or expired one looks like this.")

    older = registrations.project_named(PROJECT, token)
    if older is not None:
        print(f"project {PROJECT}: {_GENERATED_INSTEAD} {older['projectId']}")
        return older["projectId"]

    answer = registrations.project_call("CreateProject", {
        "organizationId": organisation,
        "projectId": PROJECT_ID,
        "name": PROJECT,
    }, token)
    if answer.status != 200:
        raise SystemExit(f"could not create the project: {answer.status} {answer.message()}")
    print(f"project {PROJECT}: created")
    return PROJECT_ID


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for portal in PORTALS:
        parser.add_argument("--" + portal.flag + "-origin", required=True,
                            help=f"the origin {portal.name} is served from, "
                                 "with no trailing slash")
    parser.add_argument("--token", default=api.token_from_environment(),
                        help="a token that can administer the instance")
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("No token. Pass --token, or set ORO_IDENTITY_TOKEN. "
                         "make identity-configure reads one out of the container.")

    try:
        organisation = registrations.organisation(args.token)
        project = ensure_project(organisation, args.token)
        for portal in PORTALS:
            origin = getattr(args, portal.flag + "_origin").rstrip("/")
            application = ensure_app(project, portal, origin, args.token)
            if portal.configuration:
                portal_config.write_configuration(portal, application, origin)
        ensure_door_service(organisation, args.token)
        api.apply_branding(args.token)
    except api.Refused as refused:
        # Nothing here is partially applied by a refused search: each step reads
        # before it writes. So the whole message is what happened, and it names
        # the token rather than the step that was about to run.
        raise SystemExit(str(refused))
    print(f"\nconfigured against {api.BASE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
