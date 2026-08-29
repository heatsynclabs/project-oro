"""The only way this service reaches the members database.

Two settings go on before any query runs, and both are transaction local.

`SET LOCAL ROLE oro_api` because the service logs in as oro_api_login, which
holds nothing on its own. services/api/oro_api_login.sql says why the login
role and the policy role are two roles rather than one.

`set_config('oro.identity_subject', subject, true)` because that third argument
is what makes it SET LOCAL rather than SET. A plain SET survives the
transaction, and a pooled connection is handed to the next request, so one
member's identity would answer somebody else's call. That is not a theoretical
risk: db/migrations/004_security.sql spends four lines of its own hint text on
it.

There is exactly one function below that names that setting, and no route can
reach the database except through it. A second call site is how the plain form
comes back.

No guard runs when a connection returns to the pool, and that is on purpose. A
reset hook that noticed a leaked identity and cleared it would also stop
services/api/tests/check_identity_isolation.py from ever seeing one, which
would leave the rule enforced by a comment and the test green either way.
"""

import contextlib
import logging

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# The text db/migrations/004_security.sql raises when a query runs with no
# identity on the transaction. The service turns it into the contract's 401
# rather than a 500, and logs that the database is what refused.
NO_IDENTITY_REFUSAL = "No identity set on this transaction"

_log = logging.getLogger("oro.api.database")
_pool: ConnectionPool | None = None


def open_pool(settings) -> None:
    global _pool
    _pool = ConnectionPool(
        conninfo=settings.database_url,
        min_size=1,
        max_size=settings.pool_max,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    _pool.wait(timeout=30)
    _log.info("connected to the members database")


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextlib.contextmanager
def member_transaction(subject: str | None):
    """One transaction, acting as one member, or as nobody.

    `subject` is the `sub` claim off a token this service verified. Pass None
    for a caller that presented no token or an unusable one: the transaction
    then runs with no identity and the database refuses it, which is where the
    refusal belongs. An anonymous caller is not turned away by an `if` in this
    service.
    """
    if _pool is None:
        raise RuntimeError(
            "The database pool is not open, so this request was not answered. "
            "The pool opens in the application lifespan in app/main.py, which "
            "means the service is being used outside it."
        )
    with _pool.connection() as connection:
        with connection.transaction():
            connection.execute("SET LOCAL ROLE oro_api")
            if subject is not None:
                connection.execute(
                    "SELECT set_config('oro.identity_subject', %s, true)",
                    (subject,),
                )
            # Ask the database who this is, once, before the endpoint runs its
            # own query. current_member_id() raises when no identity is set, so
            # this is where a caller with no usable token is refused, and the
            # database is what refuses them.
            #
            # It is here rather than left to the endpoint's own query because a
            # query that matches no row may never evaluate the function at all.
            # member_directory carries `current_member_id() IS NOT NULL` in its
            # WHERE, and the planner is free to test the cheap qualifier first,
            # so a lookup of an id nobody holds can come back empty without ever
            # asking. That would answer an anonymous caller with 404 instead of
            # 401, which reports on somebody who was never read.
            connection.execute("SELECT current_member_id()")
            yield connection
