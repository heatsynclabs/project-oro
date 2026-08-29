"""Turning an Authorization header into the identity subject on the token.

The contract's memberToken scheme describes an OIDC access token validated
offline against the provider's published JWKS. Offline is the point: this
service holds no credential of the identity provider's and asks it nothing on
the request path, so the provider being down slows nothing here down.

What this module never does is decide whether the caller may see anything. It
answers one question, which is who the token says they are, and a subject that
matches no member is a subject like any other. The database is what decides.
"""

import logging

import jwt
from jwt import PyJWKClient

_log = logging.getLogger("oro.api.identity")
_keys: PyJWKClient | None = None
_settings = None

# The identity provider signs with RS256. Naming the algorithm rather than
# reading it off the token is what stops a token that asks to be verified with
# `none`, or with the public key treated as an HMAC secret.
ALGORITHMS = ["RS256"]


def open_verifier(settings) -> None:
    global _keys, _settings
    _settings = settings
    _keys = PyJWKClient(settings.jwks_url, cache_keys=True)


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
    if _keys is None or _settings is None:
        raise RuntimeError(
            "The token verifier is not open, so this request was not "
            "answered. It opens in the application lifespan in app/main.py."
        )
    try:
        key = _keys.get_signing_key_from_jwt(token).key
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
