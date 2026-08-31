#!/usr/bin/env python3
"""Who the service thinks you are, and how long that lasts.

The check this file exists for is the last one. Everything above it is the
setting that makes the last one readable.

db/migrations/004_security.sql spends four lines of hint text on the
difference between SET and SET LOCAL, because a plain SET survives the
transaction and a pooled connection is handed to the next request. The suite
runs the service with a pool of exactly one connection, so every request here
lands on the same connection and a leak has nowhere to hide.
"""
import hashlib
import hmac
import os
import subprocess
import sys

from harness import (IDA, KEY_ID, STRANGER_KEY, WREN, base64url, fetch, mint,
                     public_key_pem, run, signed_token, signing_input,
                     token_claims)

SERVICE_CONTAINER = os.environ["ORO_API_TEST_CONTAINER"]


def test_an_anonymous_caller_is_refused_everywhere():
    for path in ("/me", "/members", "/members/" + WREN):
        refused = fetch(path)
        assert refused.status == 401, f"{path} answered {refused.status}"
        assert refused.headers["Content-Type"].startswith(
            "application/problem+json"), path
        problem = refused.json()
        assert problem["title"] == "Sign in first", problem
        assert problem["type"].endswith("/unauthenticated"), problem


def test_the_database_is_what_refuses_an_anonymous_caller():
    """Not a check in the service, which is where it would be easiest to put.

    There is no `if there is no token then refuse` anywhere in app/. A caller
    with no usable token reaches the database with no identity set and
    current_member_id() raises. The service logs that refusal in the database's
    own words, and this reads the log back.
    """
    fetch("/me")
    printed = subprocess.run(["docker", "logs", SERVICE_CONTAINER],
                             capture_output=True, text=True, check=False)
    log = printed.stdout + printed.stderr
    wanted = "refused by the database: No identity set on this transaction"
    assert wanted in log, log[-2000:]


def test_a_token_signed_by_somebody_else_is_refused():
    forged = mint("sub-c-wren", key_path=STRANGER_KEY)
    refused = fetch("/me", forged)
    assert refused.status == 401, refused.body
    assert refused.json()["title"] == "Sign in first", refused.body


def test_a_token_that_asks_for_no_signature_is_refused():
    """`alg: none`, which is the oldest attack there is on a JWT library.

    The header names the key this service does publish, so the refusal is
    about the algorithm and nothing else.

    Two things hold it shut, which was measured rather than assumed. First,
    app/identity.py names RS256 instead of reading the algorithm off the
    token. Second, NoneAlgorithm.verify in pyjwt 2.13.0 returns False for
    every signature, so putting "none" in ALGORITHMS on its own still refuses
    this. Loosen both, by accepting "none" and by making that verify return
    True, and this comes back 200 carrying Wren.
    """
    header = {"alg": "none", "typ": "JWT", "kid": KEY_ID}
    forged = signing_input(header, token_claims("sub-c-wren")) + "."
    refused = fetch("/me", forged)
    assert refused.status == 401, refused.body
    assert refused.json()["title"] == "Sign in first", refused.body


def test_a_token_signed_with_the_public_key_as_an_hmac_secret_is_refused():
    """The other half of the pair, and the one that still catches libraries.

    The provider's public key is public. A caller who treats those bytes as an
    HMAC secret can sign any claims they like, and a verifier that reads `alg`
    off the token checks the signature against exactly that key and believes
    it.

    Two things hold this one shut as well. Adding HS256 to ALGORITHMS in
    app/identity.py is not enough on its own, because HMACAlgorithm.prepare_key
    in pyjwt 2.13.0 refuses a key that reads as a public key. Loosen both, by
    accepting HS256 and by handing that check something it will take, and this
    comes back 200 carrying Wren.
    """
    header = {"alg": "HS256", "typ": "JWT", "kid": KEY_ID}
    part = signing_input(header, token_claims("sub-c-wren"))
    forged = part + "." + base64url(
        hmac.new(public_key_pem(), part.encode(), hashlib.sha256).digest())
    refused = fetch("/me", forged)
    assert refused.status == 401, refused.body
    assert refused.json()["title"] == "Sign in first", refused.body


def test_an_expired_token_is_refused():
    """A token this service signed off on an hour ago is not a session.

    Drop verify_exp from the options in app/identity.py and this comes back
    200, which is a stolen token working for as long as somebody keeps it.
    """
    claims = token_claims("sub-c-wren")
    claims["exp"] = claims["iat"] - 60
    stale = signed_token({"alg": "RS256", "typ": "JWT", "kid": KEY_ID}, claims)
    refused = fetch("/me", stale)
    assert refused.status == 401, refused.body
    assert refused.json()["title"] == "Sign in first", refused.body


def test_a_token_with_no_expiry_at_all_is_refused():
    """The same attack with the claim missing rather than in the past.

    Checking `exp` is not enough on its own: a token that carries none passes
    an expiry check that only looks at the claims present. app/identity.py
    requires exp, iss, aud and sub. Take "exp" out of that list and this comes
    back 200 holding a credential that never stops working.
    """
    claims = token_claims("sub-c-wren")
    del claims["exp"]
    forever = signed_token({"alg": "RS256", "typ": "JWT", "kid": KEY_ID}, claims)
    refused = fetch("/me", forever)
    assert refused.status == 401, refused.body
    assert refused.json()["title"] == "Sign in first", refused.body


def test_a_token_naming_a_key_that_was_never_published_is_refused():
    """A correctly signed token whose header points at nothing.

    The signature is real and made with the real key. Only the `kid` is wrong,
    so what refuses this is the key lookup rather than the signature check.
    Make app/identity.py fall back to any published key when the kid matches
    none and this comes back 200.
    """
    header = {"alg": "RS256", "typ": "JWT", "kid": "a-key-nobody-published"}
    stranger = signed_token(header, token_claims("sub-c-wren"))
    refused = fetch("/me", stranger)
    assert refused.status == 401, refused.body
    assert refused.json()["title"] == "Sign in first", refused.body


def test_a_token_minted_for_another_audience_is_refused():
    refused = fetch("/me", mint("sub-c-wren", audience="somebody-elses-api"))
    assert refused.status == 401, refused.body


def test_a_token_from_another_issuer_is_refused():
    refused = fetch("/me", mint("sub-c-wren", issuer="http://not.the.lab"))
    assert refused.status == 401, refused.body


def test_a_verified_token_with_no_member_row_says_so():
    """The sentence changed on 2026-08-30 and the check changed with it.

    It used to send the reader to an admin, because nothing in the contract
    could join a sign in to a record. POST /me can, so the sentence names it
    and this asserts on the way out rather than on the old dead end.
    """
    refused = fetch("/me", mint("sub-c-nobody-at-all"))
    assert refused.status == 401, refused.body
    problem = refused.json()
    assert problem["type"].endswith("/no-member-record"), problem
    assert "POST /me" in problem["detail"], problem


def test_an_identity_does_not_survive_on_a_pooled_connection():
    """Three requests, one connection, three different callers.

    With `SET LOCAL` the setting dies with the transaction and each request
    starts from nothing. With a plain `SET` the first request's subject is
    still on the connection when the second arrives, so the anonymous call in
    the middle comes back 200 carrying Wren's record, and this goes red.
    """
    first = fetch("/me", mint("sub-c-wren"))
    assert first.status == 200, first.body
    assert first.json()["id"] == WREN, first.body

    between = fetch("/me")
    assert between.status == 401, (
        "an anonymous request on the same connection was answered "
        f"{between.status}: {between.body}")

    second = fetch("/me", mint("sub-c-ida"))
    assert second.status == 200, second.body
    assert second.json()["id"] == IDA, (
        "the second caller was handed the first caller's record: "
        + second.body)


sys.exit(run(dict(globals()), "identity isolation"))
