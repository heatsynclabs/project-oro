"""The members API, three operations of the twenty three in the contract.

Read services/api/README.md first. It says which three, why the service exists
before the phase it belongs to, and what is deliberately missing.

The generated OpenAPI document and the interactive pages FastAPI would serve
are turned off. docs/api/members-v1.yaml is the contract, it was written before
this service, and a second document describing three operations would disagree
with it on the other twenty. Rule 10 asks for the document to be verified
against the running service, and that check belongs with the operation that
completes the set rather than with the first three.
"""

import contextlib
import logging

import psycopg
from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException as RouterRefusal

from . import config, database, identity, members, problems

# uvicorn configures its own loggers and leaves the root logger alone, so
# without this the service's own lines are dropped below WARNING and the only
# thing in the log is a list of status codes. What a volunteer reading the log
# during an outage needs is the sentence naming what refused a request.
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

_log = logging.getLogger("oro.api")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = config.read_settings()
    identity.open_verifier(settings)
    database.open_pool(settings)
    yield
    database.close_pool()


app = FastAPI(
    title="HeatSync Labs members API",
    lifespan=lifespan,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)


def _subject(request: Request) -> str | None:
    return identity.subject_from(request.headers.get("authorization"))


@app.exception_handler(psycopg.errors.RaiseException)
async def refused_by_the_database(request: Request, refusal: Exception):
    message = str(refusal).strip()
    if database.NO_IDENTITY_REFUSAL in message:
        # The database's own sentence, not a constant from this file, because
        # the fact worth being able to check later is that the database refused
        # this and not the service.
        _log.info("refused by the database: %s", message)
        return problems.problem_response(
            problems.UNAUTHENTICATED, request.url.path
        )
    _log.warning("the database refused this request: %s", message)
    return problems.problem_response(problems.UNEXPECTED, request.url.path)


@app.exception_handler(RouterRefusal)
async def refused_by_the_router(request: Request, refusal: RouterRefusal):
    """Starlette's 404 and 405, said in the shape app/problems.py promises.

    Starlette answers an unknown path and an unsupported method itself, before
    any endpoint here runs, and its body is `{"detail": ...}` served as
    `application/json`. The contract opens by saying errors are RFC 9457
    problem details in one shape everywhere, so this is where the second shape
    stops. Its headers are carried through: the Allow header on a 405 is
    required by RFC 9110 and Starlette had already worked out what belongs in
    it.
    """
    known = {404: problems.NO_SUCH_PATH, 405: problems.WRONG_METHOD}
    problem = known.get(refusal.status_code)
    if problem is None:
        _log.warning(
            "the router refused %s with %s, which app/problems.py has no "
            "sentence for: %s", request.url.path, refusal.status_code,
            refusal.detail)
        problem = problems.UNEXPECTED
    return problems.problem_response(
        problem, request.url.path, headers=refusal.headers)


@app.exception_handler(Exception)
async def anything_else(request: Request, fault: Exception):
    _log.exception("unhandled fault answering %s", request.url.path)
    return problems.problem_response(problems.UNEXPECTED, request.url.path)


@app.get("/me")
def get_me(request: Request):
    with database.member_transaction(_subject(request)) as connection:
        member = members.read_own_member(connection)
    if member is None:
        return problems.problem_response(
            problems.NO_MEMBER_RECORD, request.url.path
        )
    return member


@app.get("/members")
def list_directory(request: Request, fields: str | None = None):
    # The fields are read before the transaction and refused inside it. Order
    # matters both ways round. A request naming a field the directory does not
    # carry has no answer whoever sent it, so reading the directory first was a
    # round trip spent on a response nobody would see. But an anonymous caller
    # asking for one is still anonymous, and 401 is the honest answer, so the
    # refusal waits until the database has said who this is.
    wanted, unknown = members.chosen_fields(fields)
    with database.member_transaction(_subject(request)) as connection:
        if unknown:
            return _unknown_fields(request, unknown)
        listed = members.read_directory(connection)
    return [members.keep_fields(row, wanted) for row in listed]


@app.get("/members/{member_id}")
def get_directory_member(request: Request, member_id: str, fields: str | None = None):
    wanted, unknown = members.chosen_fields(fields)
    with database.member_transaction(_subject(request)) as connection:
        if unknown:
            return _unknown_fields(request, unknown)
        member = members.read_directory_member(connection, member_id)
    if member is None:
        return problems.problem_response(
            problems.NOT_IN_DIRECTORY, request.url.path
        )
    return members.keep_fields(member, wanted)


def _unknown_fields(request: Request, unknown: list[str]):
    """One entry per field the directory cannot answer, and one list.

    The list of what the directory does carry is named once, against the
    `fields` parameter it is an answer about, rather than repeated in every
    entry. Repeating it made a request naming eight unknown fields into a
    response of fifteen hundred bytes that said the same sentence eight times.
    """
    errors = [
        {"field": name, "detail": "The directory does not carry this field."}
        for name in unknown
    ]
    errors.append({
        "field": "fields",
        "detail": "The directory carries "
                  + ", ".join(sorted(members.DIRECTORY_FIELDS)) + ".",
    })
    return problems.problem_response(
        problems.INVALID_REQUEST, request.url.path, errors=errors)
