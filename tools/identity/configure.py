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
re-run is a configuration step that stops being run.

Needs a token that can administer the instance. The compose stack writes one to
/bootstrap/pat inside the identity container and `make identity-configure`
copies it out.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import api      # noqa: E402, after the path insert above

PROJECT = "Project ORO"

# These call the v1 management API, whose proto marks these methods deprecated
# in 4.17.1 while still routing them. The v2 replacement can be handed an
# application id of our choosing, which would make a re-run exact rather than a
# lookup by name. That is the better shape and it is not what is written here,
# because this version has been run against a live instance and the other has
# not. HANDOFF.md section 6 carries it.

# The door app is supposed to carry the door API in its audience, per
# docs/plan/api-design.md section 2. Nothing here does that, and nothing can
# yet: an audience is another project's id, the door API has no project, and
# inventing one would be a client pointing at something that does not exist.
# It arrives with the door service in phase 5.

# The three portals, each a public client using authorization code with PKCE,
# per docs/plan/api-design.md section 2. A public client holds no secret: PKCE
# is what stands in for one, and a secret shipped inside a page a browser
# downloads is not a secret.
#
# The redirect is the origin itself rather than a path under it. The portals are
# static files with fragment routing, so a path would need a rewrite in Caddy
# and a reload of that path would answer 404 without one.
PORTALS = (
    ("Members portal", "members"),
    ("Admin portal", "admin"),
    ("Door app", "door"),
)

# The door service is not an application. It is a machine account using client
# credentials, because nothing about it involves a person at a browser.
DOOR_SERVICE = "door-service"


def public_client(origin: str) -> dict:
    return {
        "redirectUris": [origin + "/"],
        "postLogoutRedirectUris": [origin + "/"],
        "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
        "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE",
                       "OIDC_GRANT_TYPE_REFRESH_TOKEN"],
        "appType": "OIDC_APP_TYPE_USER_AGENT",
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
        "devMode": origin.startswith("http://"),
    }


def ensure_project(token: str) -> str:
    existing = api.named(api.search("/management/v1/projects/_search", token), PROJECT)
    if existing:
        print(f"project {PROJECT}: already there")
        return existing["id"]
    answer = api.call("/management/v1/projects", {"name": PROJECT}, token)
    if answer.status != 200:
        raise SystemExit(f"could not create the project: {answer.status} {answer.message()}")
    print(f"project {PROJECT}: created")
    return answer.body["id"]


def ensure_app(project: str, name: str, origin: str, token: str) -> None:
    apps = api.search(f"/management/v1/projects/{project}/apps/_search", token)
    existing = api.named(apps, name)
    wanted = public_client(origin)
    if existing is None:
        answer = api.call(f"/management/v1/projects/{project}/apps/oidc",
                          dict(wanted, name=name), token)
        if answer.status != 200:
            raise SystemExit(f"{name}: {answer.status} {answer.message()}")
        print(f"{name}: created")
        return

    answer = api.call(
        f"/management/v1/projects/{project}/apps/{existing['id']}/oidc_config",
        wanted, token, method="PUT")
    if answer.status == 200:
        print(f"{name}: updated")
        return

    # An update that would change nothing is refused, and the wording differs by
    # endpoint: "No changes" here, "has not been changed" on the label policy.
    # So the state is read back and compared rather than the message parsed. A
    # refusal for any other reason then still fails, and it fails naming the
    # field that disagrees.
    wrong = api.differences(existing.get("oidcConfig", {}), wanted)
    if wrong:
        raise SystemExit(f"{name}: {answer.status} {answer.message()}. "
                         f"What differs: {'; '.join(wrong)}")
    print(f"{name}: already correct")


def ensure_door_service(token: str) -> None:
    answer = api.call("/management/v1/users/machine", {
        "userName": DOOR_SERVICE, "name": "Door service",
        "description": "Reads the card table. docs/plan/api-design.md section 2",
        "accessTokenType": "ACCESS_TOKEN_TYPE_JWT",
    }, token)
    if answer.status == 200:
        print(f"{DOOR_SERVICE}: created")
        return
    if "AlreadyExists" in answer.message() or answer.status == 409:
        print(f"{DOOR_SERVICE}: already there")
        return
    raise SystemExit(f"{DOOR_SERVICE}: {answer.status} {answer.message()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name, _ in PORTALS:
        flag = "--" + name.split()[0].lower() + "-origin"
        parser.add_argument(flag, required=True,
                            help=f"the origin {name} is served from, with no trailing slash")
    parser.add_argument("--token", default=api.token_from_environment(),
                        help="a token that can administer the instance")
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("No token. Pass --token, or set ORO_IDENTITY_TOKEN. "
                         "make identity-configure reads one out of the container.")

    try:
        project = ensure_project(args.token)
        for name, key in PORTALS:
            ensure_app(project, name, getattr(args, key + "_origin").rstrip("/"), args.token)
        ensure_door_service(args.token)
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
