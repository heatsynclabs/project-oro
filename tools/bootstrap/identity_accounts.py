"""The account a bootstrap admin signs in with, on the identity service.

The calls themselves come from tools/identity/api.py, which is where this
repository keeps what it knows about talking to that service and why each path
looks the way it does. Copying them here would put two files in the position of
being right about the same thing.

An account is found by its login name before one is created, so a run that
already made somebody's account adopts it rather than being refused for a name
already taken. The password is not touched on that path: by then the person may
have chosen their own, and resetting it would take their account away from them
in the name of tidiness.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "identity"))

import api      # noqa: E402, after the path insert above


def find(email: str, token: str) -> str:
    """The account holding this login name, or an empty string when there is none."""
    found = api.call("/v2/users", {"queries": [
        {"loginNameQuery": {"loginName": email}}]}, token)
    if found.status != 200:
        raise api.Refused(
            f"looking {email} up on the identity service was refused: "
            f"{found.status} {found.message()}. Nothing was created or changed. "
            "A 401 here is the token rather than the search: a revoked or "
            "expired one looks exactly like this.")
    held = found.body.get("result") or []
    if len(held) > 1:
        raise api.Refused(
            f"the identity service holds {len(held)} accounts for {email}, and "
            "this command will not guess which of them is the person in front "
            "of you. Nothing was created or changed.")
    return held[0]["userId"] if held else ""


def create(email: str, name: str, password: str, token: str) -> str:
    """A human account carrying a password they have to change at first sign in.

    The address is recorded as verified because the operator running this is
    standing next to the person, and because this stack configures no mail
    provider, so an address left unverified has no way to become verified.

    The identity service wants a given name and a family name where this system
    holds one name. Everything before the first space is the given name and
    everything after it is the family name, which is wrong for plenty of people,
    so the name as it was typed is sent as the display name and that is what the
    screens show. members.name carries it unsplit.
    """
    given, _, family = name.partition(" ")
    made = api.call("/v2/users/human", {
        "username": email,
        "profile": {"givenName": given, "familyName": family or given,
                    "displayName": name},
        "email": {"email": email, "isVerified": True},
        "password": {"password": password, "changeRequired": True},
    }, token)
    if made.status != 200:
        raise api.Refused(
            f"the identity service would not create an account for {email}: "
            f"{made.status} {made.message()}. Nothing was written to the "
            "database for this person.")
    return made.body["userId"]
