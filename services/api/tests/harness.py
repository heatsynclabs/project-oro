#!/usr/bin/env python3
"""The parts of the members API checks that are not themselves checks.

An HTTP client pointed at the running service, a token minter, and the runner
that prints the result. The check files hold checks and nothing else, which is
what keeps each of them inside the ceiling in rule 6 of CLAUDE.md.

Tokens are minted here with openssl rather than with a library, so this file
needs nothing installed on the machine running it. An RS256 signature is
RSASSA-PKCS1-v1_5 over SHA-256, which is exactly what `openssl dgst -sha256
-sign` produces, and the JWKS is built from the modulus and public exponent
openssl prints for the same key. The service verifies these tokens the way it
will verify the identity provider's: it fetches a JWKS over HTTP and checks a
signature it did not make.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

BASE = os.environ["ORO_API_TEST_URL"]
ISSUER = os.environ["ORO_API_TEST_ISSUER"]
AUDIENCE = os.environ["ORO_API_TEST_AUDIENCE"]
SIGNING_KEY = os.environ["ORO_API_TEST_KEY"]
KEY_ID = os.environ["ORO_API_TEST_KID"]
# A second key the service has never seen. A token signed with it is a forgery.
STRANGER_KEY = os.environ["ORO_API_TEST_STRANGER_KEY"]

WREN = "cccccccc-0000-0000-0000-000000000001"
IDA = "cccccccc-0000-0000-0000-000000000002"
SOLDER = "cccccccc-0000-0000-0000-000000000003"
ANVIL = "cccccccc-0000-0000-0000-000000000004"


class Answer:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        return json.loads(self.body)


def fetch(path, token=None, method="GET", body=None):
    """One request, and the answer whatever its status.

    `body` is sent as JSON when it is anything but None, which includes an
    empty object: a check about a request body with nothing in it needs to be
    able to send one.
    """
    headers = {"Accept": "application/json, application/problem+json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    sent = None
    if body is not None:
        sent = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=sent, headers=headers,
                                     method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as answer:
            return Answer(answer.status, answer.headers, answer.read().decode())
    except urllib.error.HTTPError as refused:
        return Answer(refused.code, refused.headers, refused.read().decode())


def base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _openssl(arguments, stdin=None) -> bytes:
    ran = subprocess.run(["openssl", *arguments], input=stdin,
                         capture_output=True, check=True)
    return ran.stdout


def public_numbers(key_path: str) -> tuple[bytes, bytes]:
    """The modulus and the public exponent of an RSA key, as big endian bytes.

    The exponent is read rather than assumed. openssl picks 65537 and this has
    no reason to believe that harder than it can check it.
    """
    printed = _openssl(["rsa", "-in", key_path, "-noout", "-modulus"]).decode()
    modulus = bytes.fromhex(printed.strip().split("=", 1)[1])
    text = _openssl(["rsa", "-in", key_path, "-noout", "-text"]).decode()
    found = re.search(r"publicExponent: (\d+) ", text)
    assert found, "openssl did not print a public exponent for " + key_path
    exponent = int(found.group(1))
    width = (exponent.bit_length() + 7) // 8
    return modulus, exponent.to_bytes(width, "big")


def jwks_document(key_path: str, kid: str) -> str:
    modulus, exponent = public_numbers(key_path)
    return json.dumps({"keys": [{
        "kty": "RSA", "use": "sig", "alg": "RS256", "kid": kid,
        "n": base64url(modulus), "e": base64url(exponent),
    }]})


def token_claims(subject) -> dict:
    """The claims the identity provider puts on an access token.

    A check that wants a token the service has to refuse changes one key of
    this and signs the result, so what it changed is the whole of what it is
    asking about.
    """
    now = int(time.time())
    return {
        "sub": subject,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        # Ten minutes, which is what the identity service is configured for and
        # what tools/identity/tests/check_identity.py asserts off a real token.
        "exp": now + 600,
    }


def signing_input(header: dict, claims: dict) -> str:
    """The two base64url parts a JWT signature is taken over."""
    return base64url(json.dumps(header).encode()) + "." + \
        base64url(json.dumps(claims).encode())


def signed_token(header: dict, claims: dict, key_path=None) -> str:
    """Exactly this header and these claims, RS256 signed with this key."""
    part = signing_input(header, claims)
    signature = _openssl(
        ["dgst", "-sha256", "-sign", key_path or SIGNING_KEY],
        stdin=part.encode(),
    )
    return part + "." + base64url(signature)


def public_key_pem(key_path=None) -> bytes:
    """The public half of a signing key, in the PEM anybody can fetch.

    Public is the point of it. A check about algorithm confusion needs the
    bytes an attacker already has.
    """
    return _openssl(["rsa", "-in", key_path or SIGNING_KEY, "-pubout"])


def mint(subject, key_path=None, issuer=None, audience=None) -> str:
    """An access token in the shape the contract's memberToken scheme names."""
    claims = token_claims(subject)
    if issuer is not None:
        claims["iss"] = issuer
    if audience is not None:
        claims["aud"] = audience
    header = {"alg": "RS256", "typ": "JWT", "kid": KEY_ID}
    return signed_token(header, claims, key_path)


def run(checks, what: str) -> int:
    """Run every test_ function in a namespace and report what failed."""
    found = [(name, function) for name, function in sorted(checks.items())
             if name.startswith("test_") and callable(function)]
    failed = []
    for name, function in found:
        try:
            function()
        except AssertionError as problem:
            failed.append(name)
            print(f"FAIL  {name}\n        {problem}")
        except Exception as problem:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}\n        {type(problem).__name__}: {problem}")
        else:
            print(f"ok    {name}")
    print(f"\n{len(found) - len(failed)}/{len(found)} {what} checks passed")
    return 1 if failed else 0
