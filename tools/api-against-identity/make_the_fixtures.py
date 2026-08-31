#!/usr/bin/env python3
"""Everything this suite needs registered on the identity service before it asks.

Two invented people and one extra project. tools/identity/configure.py has
already run by the time this does, so the lab's own project and its three
portals are there, and what is added here is only what a check needs and
configure.py has no business creating.

    tools/api-against-identity/run.sh

Run inside the compose network, because ORO_IDENTITY_URL names the identity
service by its name on that network. The subject, the address and the name of
the member go to stdout, tab separated, so run.sh can write the members row for
that subject. Everything a person reads goes to stderr.

Nothing here writes to the database. The identity account has to exist before
the member row can be written, because link_or_create_member in
db/migrations/008_system_paths.sql takes the subject that account will arrive
with, and tools/bootstrap/README.md says why that order is the only one that
works.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "identity"))

import api                       # noqa: E402, after the path insert above
import configure                 # noqa: E402
import registrations             # noqa: E402

# Rule 13 of CLAUDE.md: invented, and obviously invented. .invalid is reserved
# and cannot be registered, so neither address can reach a person by accident.
# The passwords are this suite's and are read by nothing outside it.
MEMBER = {
    "login": "wren@example.invalid",
    "name": "Wren Kestrel",
    "password": "Real-Token-Passw0rd-1!",
}

# The same lab, the same identity service, and no members row. This is the
# member who has signed in and whom nothing has linked to a record yet, which
# app/problems.py carries a sentence for and which nothing in the contract can
# resolve. services/api/README.md says so under what is deliberately missing.
STRANGER = {
    "login": "solder@example.invalid",
    "name": "Solder",
    "password": "No-Member-Row-Passw0rd-1!",
}

# A second project on the same instance, so that a check can hold a token this
# identity service really issued, signed with the key it really publishes,
# carrying an audience that is not the members API's. Buying that token any
# other way means minting it here, and a token this suite minted proves nothing
# about what the provider does.
OTHER_PROJECT = "Somebody else's project"
OTHER_PROJECT_ID = "another-project"
OTHER_APP = "Somebody else's portal"
OTHER_APP_ID = "another-project-portal"

# Nothing listens here. What the checks read is the redirect the identity
# service sends a browser back to, and tools/identity/flow.py catches it rather
# than following it.
ORIGIN = os.environ.get("ORO_MEMBERS_ORIGIN", "http://portal.invalid:9999")


def make_person(person: dict, token: str) -> str:
    """One human account, holding a password the checks sign in with.

    Verified, because this stack configures no mail provider, so an address
    left unverified has no way to become verified and the sign in would stop on
    a screen asking for a code nobody can read.
    """
    given, _, family = person["name"].partition(" ")
    made = api.call("/v2/users/human", {
        "username": person["login"],
        "profile": {"givenName": given, "familyName": family or given,
                    "displayName": person["name"]},
        "email": {"email": person["login"], "isVerified": True},
        "password": {"password": person["password"], "changeRequired": False},
    }, token)
    if made.status != 200:
        raise SystemExit(f"the identity service would not create an account "
                         f"for {person['login']}: {made.status} {made.message()}")
    return made.body["userId"]


def make_the_other_project(organisation: str, token: str) -> None:
    """A project this repository does not own, with one client of its own."""
    made = registrations.project_call("CreateProject", {
        "organizationId": organisation,
        "projectId": OTHER_PROJECT_ID,
        "name": OTHER_PROJECT,
    }, token)
    if made.status != 200:
        raise SystemExit(f"could not create {OTHER_PROJECT}: "
                         f"{made.status} {made.message()}")
    added = registrations.application_call("CreateApplication", {
        "projectId": OTHER_PROJECT_ID,
        "applicationId": OTHER_APP_ID,
        "name": OTHER_APP,
        "oidcConfiguration": configure.public_client(ORIGIN),
    }, token)
    if added.status != 200:
        raise SystemExit(f"could not create {OTHER_APP}: "
                         f"{added.status} {added.message()}")


def main() -> int:
    token = api.token_from_environment()
    if not token:
        raise SystemExit("No ORO_IDENTITY_TOKEN, so nothing was created.")
    subject = make_person(MEMBER, token)
    make_person(STRANGER, token)
    make_the_other_project(registrations.organisation(token), token)
    print(f"{MEMBER['name']} and {STRANGER['name']} have identity accounts, "
          f"and {OTHER_PROJECT} exists", file=sys.stderr)
    print(f"{subject}\t{MEMBER['login']}\t{MEMBER['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
