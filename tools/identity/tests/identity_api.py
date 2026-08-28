"""Calling the identity service from a script, with no browser.

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
