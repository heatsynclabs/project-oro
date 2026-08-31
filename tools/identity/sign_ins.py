"""What a sign in is on the identity service, and the writes that make one.

Read by tools/identity/make_a_sign_in.py, which is the command a person runs,
and by the checks beside it. Its own file rather than a section of that one,
because together they were over the 300 line ceiling in rule 6 of CLAUDE.md.

Two states matter here and nothing else does.

USER_STATE_ACTIVE is the one the hosted screens let somebody past, and only
when the account also holds a password and an address the service has recorded
as verified. Missing either, the screens stop: no password lands on Set
Password, an unverified address lands on E-Mail Verification, and both ask for
a code sent by mail.

USER_STATE_INITIAL is where an account made by self registration or by the v1
management create path lands, and it is a dead end. Every write is refused with
"User is not yet initialized", including setting a password and verifying the
address. Measured against Zitadel 4.17.1 on 2026-08-31, path by path, and
written up in tools/identity/README.md.
"""
from __future__ import annotations

import email.utils
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bootstrap"))

import api         # noqa: E402, after the path inserts above
import handover    # noqa: E402, tools/bootstrap/handover.py

ACTIVE = "USER_STATE_ACTIVE"
STUCK = "USER_STATE_INITIAL"

# Verifying an address that is not changing goes through the v1 management API.
# The v2 path refuses it with "Email not changed" whatever isVerified says,
# which reads as a fault and is the service declining the only thing being
# asked of it. Measured against 4.17.1 on 2026-08-31, both ways.
VERIFY_ADDRESS = "/management/v1/users/{user_id}/email"


class Person:
    def __init__(self, name: str, address: str):
        self.name = name
        self.address = address

    def __str__(self) -> str:
        return f"{self.name} <{self.address}>"


def person_from(written: str) -> Person:
    """One argument, written the way an address is written in a mail app."""
    name, address = email.utils.parseaddr(written)
    if "@" not in address:
        raise SystemExit(
            f"{written!r} is not an address, so no sign in was made. Write the "
            'person as "Ada Byron <ada@example.org>".')
    if not name.strip():
        raise SystemExit(
            f"{written!r} needs a name as well as an address, so no sign in "
            "was made. The name is what the screens greet them by. Write it "
            'as "Ada Byron <ada@example.org>".')
    return Person(name.strip(), address)


def account_named(login: str, token: str) -> dict:
    """The account holding this login name, or an empty dict when there is none."""
    found = api.call("/v2/users", {"queries": [
        {"loginNameQuery": {"loginName": login}}]}, token)
    if found.status != 200:
        raise api.Refused(
            f"looking {login} up on the identity service was refused: "
            f"{found.status} {found.message()}. Nothing was created or "
            "changed. A 401 here is the token rather than the search: a "
            "revoked or expired one looks exactly like this.")
    held = found.body.get("result") or []
    if len(held) > 1:
        raise api.Refused(
            f"the identity service holds {len(held)} accounts for {login}, and "
            "this command will not guess which of them is the person in front "
            "of you. Nothing was created or changed.")
    return held[0] if held else {}


def holds_a_password(account: dict) -> bool:
    """Whether a password has ever been set on this account.

    The account carries passwordChanged only once one has been, so its absence
    is the answer. No field states it outright. Read off two accounts made a
    second apart on 2026-08-31, one with a password and one without.
    """
    return "passwordChanged" in account.get("human", {})


def address_is_verified(account: dict) -> bool:
    return bool(account.get("human", {}).get("email", {}).get("isVerified"))


def describe(account: dict) -> str:
    """What this account is, in the words a reader needs to decide what to do."""
    if account.get("state") == STUCK:
        return "stuck in " + STUCK + ", which no write can move it out of"
    if account.get("state") != ACTIVE:
        return f"in {account.get('state')}, which this command does not handle"
    missing = []
    if not address_is_verified(account):
        missing.append("its address was never verified")
    if not holds_a_password(account):
        missing.append("it holds no password")
    if not missing:
        return "active, verified, and able to sign in"
    return "active, but " + " and ".join(missing)


def display_name(account: dict) -> str:
    """The name an account carries, so a replacement greets them the same."""
    profile = account.get("human", {}).get("profile", {})
    return (profile.get("displayName")
            or " ".join(filter(None, [profile.get("givenName"),
                                      profile.get("familyName")]))
            or account["preferredLoginName"])


def create(person: Person, token: str, terminal) -> str:
    """A human account the person can sign in with the moment they are handed it.

    The address is recorded as verified because the operator running this is
    standing next to the person. Nothing here configures a mail server, so an
    address left unverified has no way to become verified and the member is
    stopped at a screen asking for a code that will not arrive.

    The identity service wants a given name and a family name where this system
    holds one name. Everything before the first space is the given name and
    everything after it is the family name, which is wrong for plenty of
    people, so the name as it was typed goes in as the display name and that is
    what the screens show.
    """
    given, _, family = person.name.partition(" ")
    password = handover.new_password()
    made = api.call("/v2/users/human", {
        "username": person.address,
        "profile": {"givenName": given, "familyName": family or given,
                    "displayName": person.name},
        "email": {"email": person.address, "isVerified": True},
        "password": {"password": password, "changeRequired": True},
    }, token)
    if made.status != 200:
        raise api.Refused(
            f"the identity service would not make a sign in for "
            f"{person.address}: {made.status} {made.message()}. Nothing was "
            "created.")
    terminal.hand_over(person.address, password)
    return made.body["userId"]


def verify_the_address(account: dict, token: str) -> None:
    answer = api.call(VERIFY_ADDRESS.format(user_id=account["userId"]),
                      {"email": account["human"]["email"]["email"],
                       "isEmailVerified": True}, token, method="PUT")
    if answer.status != 200:
        raise api.Refused(
            f"the address on {account['preferredLoginName']} could not be "
            f"marked verified: {answer.status} {answer.message()}. Nothing "
            "else was changed.")


def set_a_password(account: dict, token: str, terminal) -> None:
    login = account["preferredLoginName"]
    password = handover.new_password()
    answer = api.set_password(account["userId"], password, token)
    if answer.status != 200:
        raise api.Refused(f"a password could not be set on {login}: "
                          f"{answer.status} {answer.message()}. Nothing else "
                          "was changed.")
    terminal.hand_over(login, password)


def remove(account: dict, token: str) -> None:
    login = account["preferredLoginName"]
    gone = api.call(f"/v2/users/{account['userId']}", {}, token,
                    method="DELETE")
    if gone.status != 200:
        raise api.Refused(f"{login} could not be removed: {gone.status} "
                          f"{gone.message()}. Nothing else was changed.")
