#!/usr/bin/env python3
"""When this service reads the identity provider's keys, and when it will not.

Two failures that pull against each other, so they are checked in one file.
Reading the JWKS too eagerly hands an unauthenticated caller an outbound HTTP
request per request. Reading it too rarely leaves a withdrawn signing key
working. app/identity.py answers both with one clock, and these are the checks
that hold it there.

The service under test runs with ORO_API_JWKS_MAX_AGE_SECONDS at a few seconds
rather than the deployed minute, so a key can be withdrawn and watched stopping
inside a check rather than inside a coffee break. run.sh sets it and passes the
same number here.
"""
import os
import pathlib
import subprocess
import sys
import threading
import time

from harness import (KEY_ID, SIGNING_KEY, STRANGER_KEY, fetch, jwks_document,
                     mint, run, signed_token, token_claims)

JWKS_CONTAINER = os.environ["ORO_API_TEST_JWKS_CONTAINER"]
PUBLISHED = pathlib.Path(os.environ["ORO_API_TEST_JWKS_DIR"]) / "jwks.json"
MAX_AGE_SECONDS = int(os.environ["ORO_API_TEST_JWKS_MAX_AGE"])

# One window plus a second, which is how long a check waits to be sure the
# service has had the chance to read the key set again.
PAST_ONE_WINDOW = MAX_AGE_SECONDS + 1


def publish(document: str) -> None:
    """Replace what the JWKS server serves. The directory is a bind mount."""
    PUBLISHED.write_text(document)


def jwks_reads() -> int:
    """How many times the service has fetched the JWKS, off the server's log."""
    printed = subprocess.run(["docker", "logs", JWKS_CONTAINER],
                             capture_output=True, text=True, check=False)
    return (printed.stdout + printed.stderr).count("GET /jwks.json")


def token_naming(kid: str) -> str:
    """A correctly signed token whose header points at a key by this name."""
    return signed_token({"alg": "RS256", "typ": "JWT", "kid": kid},
                        token_claims("sub-c-wren"))


def test_a_key_withdrawn_from_the_jwks_stops_being_accepted():
    """A signing key retired at the provider stops working here on its own.

    PyJWKClient's per key cache has no expiry at all, which is what
    app/identity.py turns off. With it on, a key removed from the published
    JWKS was still verifying freshly minted tokens six minutes later, and the
    JWKS had been read once in the whole life of the container. A key withdrawn
    because it leaked would have stayed trusted until somebody noticed and
    restarted the service.
    """
    assert fetch("/me", mint("sub-c-wren")).status == 200, "the key set is wrong"

    publish(jwks_document(STRANGER_KEY, "rotated-in"))
    try:
        time.sleep(PAST_ONE_WINDOW)
        refused = fetch("/me", mint("sub-c-wren"))
        assert refused.status == 401, (
            "a key the provider no longer publishes still verified a token "
            f"{PAST_ONE_WINDOW} seconds after it was withdrawn: {refused.body}")
    finally:
        publish(jwks_document(SIGNING_KEY, KEY_ID))

    # The same clock in the other direction. A key the provider publishes after
    # the last read is accepted within one window, which is what the window
    # costs when a rotation is planned rather than an emergency.
    time.sleep(PAST_ONE_WINDOW)
    restored = fetch("/me", mint("sub-c-wren"))
    assert restored.status == 200, (
        "a key back in the published JWKS was still refused one window "
        f"later: {restored.body}")


def test_a_kid_nobody_published_costs_no_read_of_the_jwks():
    """The cheap half of the denial of service, counted rather than timed.

    PyJWKClient re-reads the JWKS whenever it is handed a kid it does not hold,
    and no valid signature is needed to hand it one. That is an outbound HTTP
    request, on the request path, that any caller can ask for.
    """
    before = jwks_reads()
    for attempt in range(20):
        refused = fetch("/me", token_naming(f"never-published-{attempt}"))
        assert refused.status == 401, refused.body
    reads = jwks_reads() - before
    # Not zero. The clock in app/identity.py is running the whole time, and at
    # the few seconds this suite sets it to, a burst of twenty requests can
    # cross the window. What is being refused here is one read per request.
    assert reads <= 2, (
        f"twenty tokens naming keys nobody published cost {reads} reads of "
        "the JWKS. An unauthenticated caller is choosing when this service "
        "makes an outbound request.")


def test_a_members_own_call_is_answered_while_unknown_kids_arrive():
    """The expensive half, with the provider unreachable, which is the point.

    Every route handler is a synchronous def, so it runs in Starlette's forty
    slot threadpool. Measured against the service before this was fixed: with
    the JWKS server paused, forty five requests naming keys nobody published
    took a member's own call from 0.06 seconds to a timeout.
    """
    good = mint("sub-c-wren")
    assert fetch("/me", good).status == 200, "the key set is wrong"
    flood = [token_naming(f"unknown-under-load-{n}") for n in range(45)]

    subprocess.run(["docker", "pause", JWKS_CONTAINER],
                   check=True, capture_output=True)
    try:
        for token in flood:
            threading.Thread(target=fetch, args=("/me", token),
                             daemon=True).start()
        time.sleep(1)
        started = time.monotonic()
        answer = fetch("/me", good)
        took = time.monotonic() - started
    finally:
        subprocess.run(["docker", "unpause", JWKS_CONTAINER],
                       check=True, capture_output=True)

    assert answer.status == 200, (
        "a member's own call was refused while unknown keys were arriving: "
        + answer.body)
    # Ten seconds is generous on purpose. The number that matters is that it is
    # not the thirty second HTTP timeout PyJWKClient uses by default, times
    # however many of those a caller can start at once.
    assert took < 10, (
        f"a member's own call took {took:.1f} seconds while the provider was "
        "unreachable and unknown keys were arriving")


sys.exit(run(dict(globals()), "signing key"))
