"""Everything this service reads out of its environment.

Read once, at start, so a missing setting stops the container instead of
surfacing as a refused request an hour later.
"""

import dataclasses
import os


class MissingSetting(RuntimeError):
    """A required environment variable was empty or absent."""


@dataclasses.dataclass(frozen=True)
class Settings:
    database_url: str
    pool_max: int
    jwks_url: str
    jwks_max_age_seconds: int
    token_issuer: str
    token_audience: str


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingSetting(
            f"{name} is not set, so the service refused to start and has "
            "answered nothing. Set it in the environment of the api container. "
            "services/api/README.md lists every variable this service reads "
            "and what each one is for."
        )
    return value


def read_settings() -> Settings:
    return Settings(
        database_url=_required("ORO_API_DATABASE_URL"),
        # One connection is enough for a few hundred members and it is what the
        # suite runs on, because two requests have to land on the same
        # connection for the identity leak test to mean anything. Ten is the
        # deployment default and nobody has measured a better number yet.
        pool_max=int(os.environ.get("ORO_API_DB_POOL_MAX", "10")),
        jwks_url=_required("ORO_API_JWKS_URL"),
        # The only clock in the token path, and it is two numbers at once. A
        # signing key the provider withdraws stops being accepted here within
        # this long, and a key it newly publishes starts being accepted within
        # this long. app/identity.py says why nothing shortens it in answer to
        # a request, and the suite runs it at a few seconds so that a withdrawn
        # key can be watched stopping.
        jwks_max_age_seconds=int(
            os.environ.get("ORO_API_JWKS_MAX_AGE_SECONDS", "60")),
        token_issuer=_required("ORO_API_TOKEN_ISSUER"),
        token_audience=_required("ORO_API_TOKEN_AUDIENCE"),
    )
