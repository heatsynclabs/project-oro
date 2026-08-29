#!/usr/bin/env python3
"""One admin's first sign in, all the way through the screens they will use.

The rest of the suite signs in the way tools/identity does, by asking the
identity service to check a password. That proves the password works. It does
not prove the thing this command has to get right, which is that the subject
written onto the member row is the subject a portal will be handed in a token.
Those are two different strings until somebody checks.

Last in the suite, because it changes a password. Every check before it reads
the handover password the command printed.

    ORO_PSQL=... ORO_IDENTITY_URL=... ORO_IDENTITY_TOKEN=... \\
      ORO_BOOTSTRAP_PEOPLE=... ORO_BOOTSTRAP_TRANSCRIPT=... \\
      ORO_MEMBERS_ORIGIN=... check_first_sign_in.py
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "identity"))

import api              # noqa: E402, after the path inserts above
import database         # noqa: E402
import flow             # noqa: E402
import registrations    # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import check_seats      # noqa: E402, the fixtures and the transcript reader

TOKEN = os.environ.get("ORO_IDENTITY_TOKEN", "")
MEMBERS_ORIGIN = os.environ.get("ORO_MEMBERS_ORIGIN", "")

# Long enough for the policy the identity service ships with, which is eight
# characters carrying an upper case letter, a lower case letter, a number and a
# symbol. Invented, used once, and gone with the stack. Rule 13.
CHOSEN_PASSWORD = "Chosen-By-The-Member-9!"


def subject_in_the_token() -> str:
    """Sign in the way a person does, and read the subject out of the token."""
    email = check_seats.emails()[0]
    person = check_seats.account(email)
    changed = api.set_password(person["userId"], CHOSEN_PASSWORD, TOKEN)
    assert changed.status == 200, (
        f"the password could not be changed: {changed.status} {changed.message()}")

    client = registrations.get_application("oro-members-portal", TOKEN)
    assert client.status == 200, "the members portal client is not registered"
    tokens = flow.sign_in_through_the_screens(
        client.body["application"]["oidcConfiguration"]["clientId"],
        MEMBERS_ORIGIN, email, CHOSEN_PASSWORD)
    assert tokens.status == 200, f"the token exchange answered {tokens.status}"
    payload = tokens.body["id_token"].split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]


def test_the_subject_in_the_token_is_the_one_on_the_member_row():
    email = check_seats.emails()[0]
    on_the_row = database.ask(
        "SELECT identity_subject FROM members WHERE email = :'email'",
        {"email": email})
    assert subject_in_the_token() == on_the_row, (
        "a portal will be handed a subject this member row does not carry, so "
        "the admin who just signed in is nobody as far as this database is "
        "concerned")


def _run() -> int:
    failed = []
    for name, function in sorted(globals().items()):
        if not name.startswith("test_") or not callable(function):
            continue
        try:
            function()
            print(f"ok   {name}")
        except AssertionError as unmet:
            failed.append(name)
            print(f"FAIL {name}  {unmet}")
        except Exception as broke:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}  {type(broke).__name__}: {broke}")
    return 1 if failed else 0


if __name__ == "__main__":
    if not TOKEN or not MEMBERS_ORIGIN:
        print("No ORO_IDENTITY_TOKEN or no ORO_MEMBERS_ORIGIN, so nothing was "
              "checked. tools/bootstrap/tests/run.sh sets both.", file=sys.stderr)
        sys.exit(1)
    sys.exit(_run())
