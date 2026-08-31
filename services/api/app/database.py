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

# The constraint db/migrations/001_schema.sql gives members.email. psycopg
# reports it on the diagnostics of a UniqueViolation, and app/main.py turns
# that one constraint into the contract's 409 and every other into a 500,
# because a unique violation nobody predicted is a fault here rather than
# something to tell a member about.
EMAIL_CONSTRAINT = "members_email_key"

# How long a request waits for a free connection before it is answered 500.
# psycopg_pool's own default is thirty seconds, read from ConnectionPool in
# psycopg-pool 3.3.1, and a request that waits that long holds one of the forty
# threadpool slots uvicorn gives a synchronous endpoint for the whole time. So
# thirty seconds of an exhausted pool is forty requests parked and nothing left
# to answer the forty first. Every query here is an indexed read of at most a
# few hundred rows, so two seconds without a free connection means the pool is
# full or the database is unreachable, and neither improves by waiting.
WAIT_FOR_A_CONNECTION_SECONDS = 2

# Ceilings the database applies to itself, in milliseconds, which is the unit
# Postgres takes. They exist because the pool is small: one query nobody is
# waiting for any more can hold a connection out of a pool of ten.
#
# Five seconds is far above anything this service runs. The slowest of its
# queries reads the whole directory, which is a few hundred rows.
STATEMENT_CEILING_MILLISECONDS = 5000
# A transaction that has stopped doing work holds a connection and a row lock
# and does nothing with either. Ten seconds is well past the longest request
# here, which opens a transaction, runs four statements and closes it.
IDLE_TRANSACTION_CEILING_MILLISECONDS = 10000

_log = logging.getLogger("oro.api.database")
_pool: ConnectionPool | None = None


def open_pool(settings) -> None:
    global _pool
    _pool = ConnectionPool(
        conninfo=settings.database_url,
        min_size=1,
        max_size=settings.pool_max,
        timeout=WAIT_FOR_A_CONNECTION_SECONDS,
        kwargs={
            "row_factory": dict_row,
            # libpq hands these to the server at connect time, so every
            # connection in the pool carries them without a statement per
            # checkout.
            "options": (
                f"-c statement_timeout={STATEMENT_CEILING_MILLISECONDS}"
                " -c idle_in_transaction_session_timeout="
                f"{IDLE_TRANSACTION_CEILING_MILLISECONDS}"
            ),
        },
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


def caller_member_id(connection):
    """Which member the database says this transaction is acting as, or None.

    None means a token this service verified for somebody the members database
    has never met. Every path that reads one member's own rows asks this first,
    because the alternative is answering that person with an empty list, which
    reads as "you have no cards" rather than "you have no record".

    It is a second statement rather than the answer to the one
    member_transaction already runs. Keeping that one where it is means the
    refusal of an anonymous caller stays in one place, and this is an indexed
    lookup on a unique column.
    """
    return connection.execute(
        "SELECT current_member_id() AS member_id").fetchone()["member_id"]
