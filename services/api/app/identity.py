"""Turning an Authorization header into the identity subject on the token.

The contract's memberToken scheme describes an OIDC access token validated
offline against the provider's published JWKS. Offline is the point: this
service holds no credential of the identity provider's and asks it nothing on
the request path, so the provider being down slows nothing here down.

The provider's key set is read on a clock and never in answer to a request.
That one decision covers two failures that pull against each other, and both
were measured against a running service before this was written.

A token naming a `kid` nobody published costs no outbound request at all. It is
refused from the set already in memory. PyJWKClient re-reads the JWKS whenever
it is handed a kid it does not hold, and no valid signature is needed to hand
it one, so an unauthenticated caller could otherwise spend one HTTP timeout per
request out of a threadpool that holds forty. Measured with the JWKS server
paused: forty five such requests took a member's own call from 0.06 seconds to
a timeout.

A signing key the provider withdraws stops being accepted here within
ORO_API_JWKS_MAX_AGE_SECONDS, one minute by default. PyJWKClient's per key
cache has no expiry, so a key withdrawn because it leaked would otherwise stay
trusted until somebody restarted the container.

The same window is what a key rotation costs: a token signed with a key the
provider published after the last read is refused until the next read. That is
the price of the first paragraph, and one minute of it is the number chosen.

What this module never does is decide whether the caller may see anything. It
answers one question, which is who the token says they are, and a subject that
matches no member is a subject like any other. The database is what decides.
"""

import logging
import threading
import time

import jwt
from jwt import PyJWKClient

_log = logging.getLogger("oro.api.identity")

# The identity provider signs with RS256. Naming the algorithm rather than
# reading it off the token is what stops a token that asks to be verified with
# `none`, or with the public key treated as an HMAC secret.
ALGORITHMS = ["RS256"]

# How long one read of the key set may take. PyJWKClient's own default is
# thirty seconds, read from jwt/jwks_client.py in pyjwt 2.13.0. The provider is
# one hop away, and a read that has not finished in three seconds is one this
# service should stop waiting on and answer the next request from what it
# already holds.
KEY_SET_READ_TIMEOUT_SECONDS = 3

_client: PyJWKClient | None = None
_settings = None
_signing_keys: dict[str, object] = {}
# Nothing read yet, so the first look finds the set stale whatever the clock
# says. time.monotonic() has no fixed zero.
_read_at = float("-inf")
# A read happens under this lock and no request ever waits for it.
_reading = threading.Lock()


def open_verifier(settings) -> None:
    global _client, _settings, _signing_keys, _read_at
    _settings = settings
    _client = PyJWKClient(
        settings.jwks_url,
        # Both caches PyJWKClient offers are off, and read_key_set below is
        # what replaces them. Its per key cache never expires an entry, and its
        # set cache re-reads the JWKS on any kid it does not hold, which is the
        # read an unauthenticated caller can ask for once per request.
        cache_keys=False,
        cache_jwk_set=False,
        timeout=KEY_SET_READ_TIMEOUT_SECONDS,
    )
    _signing_keys = {}
    _read_at = float("-inf")
    # Once here, so the first member to sign in after a deploy is not refused
    # while the first read is still in flight. A provider that is down at this
    # moment is logged and the service starts anyway, because refusing to start
    # would turn a provider outage into an outage of this service too.
    read_key_set()


def read_key_set() -> None:
    """Replace the keys held in memory with what the provider publishes now.

    Never waits for the lock. A caller that finds another thread already
    reading is answered from the set this service already holds, so a slow
    provider costs one thread rather than every thread that arrives during it.
    """
    global _signing_keys, _read_at
    if not _reading.acquire(blocking=False):
        return
    try:
        # Stamped before the read rather than after it, so a provider that is
        # down costs one attempt per window rather than one attempt per
        # request. The keys already held are replaced only on success.
        _read_at = time.monotonic()
        _signing_keys = {
            published.key_id: published.key
            for published in _client.get_signing_keys()
        }
    except Exception as unreadable:
        _log.warning(
            "the identity provider's key set at %s could not be read (%s), so "
            "tokens are still being checked against the %d key(s) read before "
            "this. A token signed with a key published since then is refused. "
            "Check that the provider answers, and expect members to be sent "
            "back to sign in if it does not.",
            _settings.jwks_url, unreadable, len(_signing_keys),
        )
    finally:
        _reading.release()


def _signing_key(kid: str | None):
    """The public key published under this `kid`, or None for anything else.

    None here has cost no outbound request. That is the whole point of it.
    """
    if time.monotonic() - _read_at > _settings.jwks_max_age_seconds:
        read_key_set()
    return _signing_keys.get(kid)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def subject_from(authorization: str | None) -> str | None:
    """The `sub` claim off a token this service verified, or None.

    None covers every way a caller can arrive without a usable identity: no
    header, a header that is not a bearer token, a signature this service
    cannot verify, an expired token, and a token minted for somebody else's
    audience. They all mean the same thing to the caller and they all end at
    the same refusal, so they are one answer here.
    """
    token = _bearer_token(authorization)
    if token is None:
        return None
    if _client is None or _settings is None:
        raise RuntimeError(
            "The token verifier is not open, so this request was not "
            "answered. It opens in the application lifespan in app/main.py."
        )
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.InvalidTokenError as unreadable:
        _log.info("token refused: %s", unreadable)
        return None
    key = _signing_key(kid)
    if key is None:
        _log.info("token refused: no published signing key has kid %r", kid)
        return None
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            issuer=_settings.token_issuer,
            audience=_settings.token_audience,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception as refusal:
        # The token itself is never logged. It is a live credential for ten
        # minutes and a log is read by more people than a session is.
        _log.info("token refused: %s", refusal)
        return None
    return claims.get("sub")
