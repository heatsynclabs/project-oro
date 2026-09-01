#!/usr/bin/env python3
"""Register what the identity service has to hold, from configuration.

Phase 2 of docs/plan/order-of-operations.md asks for a deployment reproducible
from the compose file plus a database dump, with no console click that is not
also in configuration. The compose file creates the instance, its admin and a
machine account. This creates everything above that: the project, the four
clients docs/plan/api-design.md section 2 specifies, the GANTRY branding on the
hosted screens, the words on the message a new member gets, the sign up, and the
mail server the codes those screens ask for are sent through.

The sign up is on unless --self-registration off says otherwise. Off is for a
deployment with no mail server, where pressing Register strands a person in a
state no admin can repair.

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
--no-portal-config leaves it alone, which is what a throwaway stack wants: an
instance about to be removed should not be what a working portal points at.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import api              # noqa: E402, after the path insert above
import branding         # noqa: E402
import clients          # noqa: E402
import login_policy     # noqa: E402
import mail             # noqa: E402
import messages         # noqa: E402
import portal_config    # noqa: E402
import registrations    # noqa: E402

PROJECT = "Project ORO"

# The checkout, so the client id lands beside the portal whatever the cwd is.
ROOT = pathlib.Path(__file__).resolve().parents[2]

# The identifiers this step gives the things it registers. They are ours rather
# than the service's, so a second run addresses what the first one made instead
# of searching by name and hoping one thing came back.
PROJECT_ID = "oro-project"

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
        print(f"project {PROJECT}: {clients.GENERATED_INSTEAD} {older['projectId']}")
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


def build_parser() -> argparse.ArgumentParser:
    """What this step takes, which is longer than what it does.

    Its own function because main reached the 50 line ceiling in rule 6, and the
    seam was already here: the flags are a description of the step and the body
    below is the step.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for portal in clients.PORTALS:
        parser.add_argument("--" + portal.flag + "-origin", required=True,
                            help=f"the origin {portal.name} is served from, "
                                 "with no trailing slash")
    parser.add_argument("--mail-host",
                        help="host:port the identity service sends through. "
                             "mail:1025 on a laptop, which is the catcher "
                             "compose.development.yaml runs. Without it, "
                             "registering and a forgotten password both "
                             "stop at a code nothing can send.")
    parser.add_argument("--self-registration", choices=("on", "off"),
                        default="on",
                        help="whether the sign in screens carry a Register "
                             "button. On, because this site replaces one with "
                             "a sign up. Off is for a deployment with no mail "
                             "server, where a person who presses it lands in "
                             "USER_STATE_INITIAL waiting for a code nothing "
                             "can send, and no admin can repair that account.")
    parser.add_argument("--no-portal-config", action="store_true",
                        help="do not write apps/members/identity.json. For a "
                             "throwaway stack, which would otherwise leave that "
                             "file pointing a portal somebody is using at an "
                             "instance that is about to be removed.")
    parser.add_argument("--token", default=api.token_from_environment(),
                        help="a token that can administer the instance")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.token:
        raise SystemExit("No token. Pass --token, or set ORO_IDENTITY_TOKEN. "
                         "make identity-configure reads one out of the container.")

    try:
        organisation = registrations.organisation(args.token)
        project = ensure_project(organisation, args.token)
        for portal in clients.PORTALS:
            origin = getattr(args, portal.flag + "_origin").rstrip("/")
            application = clients.ensure_app(project, portal, origin, args.token)
            if portal.configuration and not args.no_portal_config:
                portal_config.write_configuration(portal, application, origin)
        clients.ensure_door_service(organisation, args.token)
        branding.apply_branding(args.token)
        messages.apply_message_text(args.token)
        if args.mail_host:
            mail.point_at(args.mail_host, args.token)
        else:
            mail.say_there_is_none()
        # Read from the flag rather than from whether --mail-host was given.
        # Tying the two together would leave one variable doing two jobs, which
        # is the trap ADR 0002 records, and it would take the sign up away from
        # a deployment whose mail server somebody configured by hand at step 8
        # of the deploy runbook rather than through this step.
        if args.self_registration == "on":
            login_policy.open_self_registration(args.token)
        else:
            login_policy.close_self_registration(args.token)
    except api.Refused as refused:
        # Nothing here is partially applied by a refused search: each step reads
        # before it writes. So the whole message is what happened, and it names
        # the token rather than the step that was about to run.
        raise SystemExit(str(refused))
    print(f"\nconfigured against {api.BASE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
