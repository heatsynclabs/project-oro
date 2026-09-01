"""Calling the identity service from a script, with no browser.

Shared by tools/identity/configure.py, which is operational, and by the suite
under tools/identity/tests/, which proves what it did.

This file is how to reach the service at all. What the service is holding for us,
the project and the clients and the door service account, is read back through
tools/identity/registrations.py.

The identity service resolves which instance a request is for by comparing the
Host header against the domain it was configured with, so a call to 127.0.0.1
is refused with "Instance not found" even when the port is right. Everything
here goes through the URL in ORO_IDENTITY_URL, which carries that name.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("ORO_IDENTITY_URL", "http://localhost:8180")

# Seconds, one try a second. Thirty because the read model has always caught up
# inside two, and a bound that never fires is cheaper than a suite that fails
# once a fortnight on a slow machine.
SECRET_VISIBLE_TRIES = 30


class Answer:
    def __init__(self, status: int, body: dict):
        self.status = status
        self.body = body

    def message(self) -> str:
        return str(self.body.get("message", ""))[:200]


class Refused(Exception):
    """The service answered, and the answer was a refusal.

    An ordinary Exception rather than SystemExit. A check suite wraps each check
    in `except Exception` so that one failure is one FAIL line and the rest still
    run. SystemExit is a BaseException, slips past that, and ends the whole run
    with no summary, which turns a readable failure into a silent one.
    """


def call(path: str, body: dict, token: str, method: str = "POST") -> Answer:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"},
        method=method,
    )
    return _send(request)


def _send(request: urllib.request.Request) -> Answer:
    try:
        with urllib.request.urlopen(request) as answer:
            return Answer(answer.status, json.load(answer))
    except urllib.error.HTTPError as refused:
        return Answer(refused.code, json.loads(refused.read().decode()))
    except urllib.error.URLError as unreachable:
        # Rule 7: an error says what happened and what the reader does next.
        # Without this the two commands that seat admins and configure the
        # instance end in a urllib traceback.
        raise Refused(
            f"{BASE} could not be reached: {unreachable.reason}. Nothing was "
            "read or changed. " + _what_to_do_about(unreachable.reason)
        ) from unreachable


def _what_to_do_about(reason: object) -> str:
    """The sentence after the failure, chosen by which failure it was.

    Two shapes reach here and they want opposite answers, and saying both every
    time sends the reader to check a hostname that is already right.

    Nothing listening is the shape a laptop is nearly always in. The default
    ORO_IDENTITY_URL is built from ORO_HOSTNAME as https://id.<host>, which on a
    laptop is https://id.localhost and resolves nowhere. Measured on 2026-08-31
    by running make bootstrap-admins on a laptop with the shipped .env.

    A certificate nothing trusts is the shape a deployment is in. ORO_TLS is
    internal there, which means Caddy issued it from its own authority, and the
    curl in the runbook passes -k while nothing here does. Measured on
    2026-08-31 against a deployment shaped stack on a non standard port:
    configure.py stopped on CERTIFICATE_VERIFY_FAILED, and the advice it printed
    was about the hostname and the stack being up, neither of which was wrong.
    """
    if "CERTIFICATE_VERIFY_FAILED" in str(reason):
        return ("The service answered and its certificate comes from an "
                "authority this machine does not trust, which is what "
                "ORO_TLS=internal means. Copy Caddy's own root out of the "
                "container and name it in SSL_CERT_FILE. Step 6 of "
                "docs/runbooks/deploy-beside-the-legacy-system.md has the two "
                "commands.")
    return ("On a laptop the identity service is published on a port rather "
            "than at a name, so set ORO_IDENTITY_URL to http://localhost: and "
            "the port in ORO_IDENTITY_PORT. On a deployment, check that "
            "ORO_HOSTNAME in .env is the name the certificate is for, that the "
            "name resolves on this machine, and that the stack is up.")


def import_member(login: str, hashed_password: str, token: str) -> Answer:
    """Create a member carrying a password hash the lab already holds.

    This is the migration path. Nobody has the plaintext, so the hash is handed
    over as it was read out of the legacy database and the identity service
    verifies against it from then on.
    """
    return call("/v2/users/human", {
        "username": login,
        "profile": {"givenName": "Fixture", "familyName": "Member"},
        "email": {"email": login, "isVerified": True},
        "hashedPassword": {"hash": hashed_password},
    }, token)


def sign_in(login: str, password: str, token: str) -> Answer:
    """Check a password the way a sign in does, without the hosted screens.

    A session is what the login screens create once a password has been
    checked, so creating one directly asks the same question the screens ask
    and answers it with the same code.
    """
    return call("/v2/sessions", {"checks": {
        "user": {"loginName": login},
        "password": {"password": password},
    }}, token)


def machine_token(name: str, token: str) -> Answer:
    """A real access token, through a real grant, so its lifetime can be read.

    A machine account with a client secret is the only grant a script can
    complete on its own. Every other one ends at a login screen.

    What this measures is therefore a client credentials token, not a member's.
    The lifetime is configured on the instance rather than on the grant, so the
    two should agree, and that has not been measured here because measuring it
    needs a browser.
    """
    made = call("/management/v1/users/machine", {
        "userName": name, "name": name,
        "description": "created by the identity suite, removed with the stack",
        "accessTokenType": "ACCESS_TOKEN_TYPE_JWT",
    }, token)
    if made.status != 200:
        return made
    secret = call(f"/management/v1/users/{made.body['userId']}/secret", {},
                  token, method="PUT")
    if secret.status != 200:
        return secret
    return _client_credentials(secret.body["clientId"],
                               secret.body["clientSecret"])


def _client_credentials(client_id: str, client_secret: str) -> Answer:
    """Ask for a token, waiting for the secret to become visible.

    The identity service answers this from a read model that it updates after
    the write, so a secret created a moment ago is refused with
    Errors.User.Machine.Secret.NotExisting until that catches up. Measured on a
    busy instance, where it failed every time, against a fresh one where it
    never did. A suite that only passes on an idle machine is a flake.
    """
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": "openid",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    request = urllib.request.Request(
        BASE + "/oauth/v2/token", data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    for _ in range(SECRET_VISIBLE_TRIES):
        answer = _send(request)
        if answer.status == 200:
            return answer
        if "Secret.NotExisting" not in str(answer.body):
            return answer
        time.sleep(1)
    return answer


def lifetime_of(access_token: str) -> int:
    """Seconds between the token's own issued at and expiry claims.

    Read from the token rather than from the `expires_in` beside it, because
    that field is what the server says and these are what every verifier will
    act on.
    """
    payload = access_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    return claims["exp"] - claims["iat"]


def get(path: str, token: str) -> Answer:
    request = urllib.request.Request(
        BASE + path, headers={"Authorization": "Bearer " + token}, method="GET")
    return _send(request)


def search(path: str, token: str) -> list:
    """A Zitadel search, which is a POST with an empty body and a result list.

    A refusal carries a message and no list, so reading a list out of one gives
    an empty list, which is what a search that found nothing also gives. The
    caller cannot tell those apart and acts on the wrong one: told that no
    project exists, configure.py creates the project that is already there and
    reports the failure against creating it. Measured on 2026-08-28 by revoking
    the bootstrap token, after which configure.py said "could not create the
    project: 401" when the truth was that its token had been revoked.
    """
    answer = call(path, {}, token)
    if answer.status >= 400:
        raise Refused(
            f"the search {path} was refused: {answer.status} {answer.message()}. "
            "Nothing was created or changed. A 401 here is the token rather "
            "than the search: a revoked or expired one looks exactly like this.")
    return answer.body.get("result") or []


def token_from_environment() -> str:
    return os.environ.get("ORO_IDENTITY_TOKEN", "")


def post_form(path: str, fields: dict) -> Answer:
    """An OAuth token request, which is a form post and carries no bearer."""
    request = urllib.request.Request(
        BASE + path, data=urllib.parse.urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    return _send(request)


def set_password(user_id: str, password: str, token: str) -> Answer:
    """Change a member's password, which is where the new policy applies.

    An imported hash bypasses the complexity policy, because it is a hash rather
    than a password. The policy is checked the first time a member sets a new
    one, which is a different day and a different person's problem.
    """
    return call(f"/v2/users/{user_id}/password",
                {"newPassword": {"password": password, "changeRequired": False}},
                token)
