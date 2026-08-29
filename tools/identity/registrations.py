"""What the identity service is holding, read back by the identifier we gave it.

tools/identity/configure.py registers a project, three OIDC clients and a machine
account, and everything here is how it finds out what is already there before it
writes. Split out of api.py, which is how to talk to the service at all, because
that file was over the 300 line ceiling in rule 6 of CLAUDE.md and this is the
half with its own subject.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import api      # noqa: E402, after the path insert above

from api import Answer, Refused      # noqa: E402, the two types used below


# The two services that replaced the deprecated halves of the v1 management API.
# They answer on a path built from the proto package and the service name rather
# than under /v2/, because zitadel/project/v2/project_service.proto and
# zitadel/application/v2/application_service.proto carry no google.api.http
# option for the gateway to route. Read out of the 4.17.1 image's own embedded
# descriptors on 2026-08-29, and then proven by calling them.
PROJECT_SERVICE = "zitadel.project.v2.ProjectService"
APPLICATION_SERVICE = "zitadel.application.v2.ApplicationService"


def project_call(method: str, body: dict, token: str) -> Answer:
    return api.call(f"/{PROJECT_SERVICE}/{method}", body, token)


def application_call(method: str, body: dict, token: str) -> Answer:
    return api.call(f"/{APPLICATION_SERVICE}/{method}", body, token)


def get_project(project_id: str, token: str) -> Answer:
    """The project under an identifier we chose. 404 when there is none."""
    return project_call("GetProject", {"projectId": project_id}, token)


def get_application(application_id: str, token: str) -> Answer:
    """The application under an identifier we chose. 404 when there is none."""
    return application_call("GetApplication",
                            {"applicationId": application_id}, token)


def get_user(user_id: str, token: str) -> Answer:
    """The account under an identifier we chose. 404 when there is none."""
    return api.get(f"/v2/users/{user_id}", token)


def project_named(name: str, token: str) -> dict | None:
    """A project carrying this name, whatever identifier it holds.

    Only the fallback. An instance configured by the version of this tool that
    let the service generate the identifier has one of these, and creating a
    second project of the same name beside it would leave every portal pointing
    at clients in the one nothing writes to any more.
    """
    answer = project_call("ListProjects", {"filters": [
        {"projectNameFilter": {"projectName": name,
                               "method": "TEXT_FILTER_METHOD_EQUALS"}}]}, token)
    _refuse_if_not_ok(answer, f"the search for a project named {name!r}")
    return (answer.body.get("projects") or [None])[0]


def application_named(project: str, name: str, token: str) -> dict | None:
    """An application in this project carrying this name. The same fallback."""
    answer = application_call("ListApplications", {"filters": [
        {"projectIdFilter": {"projectId": project}},
        {"nameFilter": {"name": name,
                        "method": "TEXT_FILTER_METHOD_EQUALS"}}]}, token)
    _refuse_if_not_ok(answer, f"the search for an application named {name!r}")
    return (answer.body.get("applications") or [None])[0]


def organisation(token: str) -> str:
    """The organisation everything this tool registers belongs to.

    Creating a project needs one named, and the instance the compose file seeds
    holds exactly one, from ZITADEL_FIRSTINSTANCE_ORG_NAME. More than one means
    somebody added an organisation, and guessing which of them the lab's members
    live in is the kind of guess that puts the portals in the wrong place.
    """
    held = api.search("/v2/organizations/_search", token)
    if len(held) != 1:
        raise Refused(
            f"the instance holds {len(held)} organisations, and this step only "
            "knows how to configure an instance with one. Nothing was created "
            "or changed. Name the organisation to configure, or remove the "
            "ones that do not belong to the lab.")
    return held[0]["id"]


def _refuse_if_not_ok(answer: Answer, what: str) -> None:
    if answer.status >= 400:
        raise Refused(f"{what} was refused: {answer.status} {answer.message()}. "
                      "Nothing was created or changed. A 401 here is the token "
                      "rather than the search: a revoked or expired one looks "
                      "exactly like this.")


def differences(actual: dict, wanted: dict) -> list[str]:
    """Which of the fields we asked for the service does not already hold.

    Lists are compared as sets, because the order Zitadel returns a redirect
    URI list in is not the order it was given.
    """
    wrong = []
    for key, value in wanted.items():
        held = actual.get(key)
        if isinstance(value, list):
            if set(held or []) != set(value):
                wrong.append(f"{key} is {held!r}, wanted {value!r}")
        elif held is None and value is False:
            # A field holding its default is left out of the answer entirely, so
            # developmentMode reads back as absent rather than as false. Absent
            # and false are one state. Measured on 4.17.1 on 2026-08-29 against
            # an application registered with an https origin, whose read back
            # carried no developmentMode at all. Calling those two different
            # would have every https deployment ask for an update on every run
            # and be refused with "No changes".
            continue
        elif held != value:
            wrong.append(f"{key} is {held!r}, wanted {value!r}")
    return wrong
