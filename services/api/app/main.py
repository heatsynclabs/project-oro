"""The members API, eight operations of the twenty four in the contract.

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
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as RouterRefusal

from . import (config, database, first_sign_in, identity, members, problems,
               self_service)

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


@app.exception_handler(psycopg.errors.UniqueViolation)
async def refused_by_a_unique_constraint(request: Request, refusal: Exception):
    """The one constraint a member can hit, said in the contract's shape.

    Only members.email is turned into a refusal a person is shown. Any other
    unique violation is a fault in this service rather than something the
    caller did, and saying otherwise would send them looking for a mistake they
    did not make.
    """
    named = getattr(getattr(refusal, "diag", None), "constraint_name", None)
    if named == database.EMAIL_CONSTRAINT:
        _log.info("refused by the database: the address on this request "
                  "already belongs to another member record (%s)", named)
        return problems.problem_response(
            problems.EMAIL_ALREADY_KNOWN, request.url.path)
    _log.warning("a unique constraint refused this request: %s", refusal)
    return problems.problem_response(problems.UNEXPECTED, request.url.path)


@app.exception_handler(RequestValidationError)
async def refused_before_the_endpoint(request: Request,
                                      refusal: RequestValidationError):
    """A request body FastAPI could not read, said in the contract's shape.

    FastAPI answers this one itself, as `{"detail": [...]}` in
    application/json, which is the third shape after the two
    refused_by_the_router catches. `loc` starts with the word body, and what a
    caller wants is the field it named.
    """
    errors = [
        {"field": ".".join(str(part) for part in named["loc"][1:]) or "body",
         "detail": named["msg"]}
        for named in refusal.errors()
    ]
    return problems.problem_response(
        problems.INVALID_REQUEST, request.url.path, errors=errors)


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


@app.post("/me")
def create_me(request: Request, asked: first_sign_in.FirstSignIn):
    """A first sign in, which is the only way a member record is written here.

    201 when this call wrote it and 200 when it was already there, so a portal
    that cannot tell a first sign in from a fifth may send this once and read
    what comes back. app/first_sign_in.py says why no address in the body ever
    reaches link_or_create_member.
    """
    with database.member_transaction(_subject(request)) as connection:
        written = first_sign_in.claim_or_create(connection, asked)
        member = members.read_own_member(connection)
    if member is None:
        # Unreachable as written: link_or_create_member either answers with a
        # record id or raises. Left in place because the alternative is
        # answering 200 with nothing in it.
        _log.error("a first sign in wrote no record and raised nothing")
        return problems.problem_response(problems.UNEXPECTED, request.url.path)
    if not written:
        return member
    return JSONResponse(status_code=201, content=jsonable_encoder(member),
                        headers={"Location": "/me"})


@app.get("/me/cards")
def list_my_cards(request: Request):
    with database.member_transaction(_subject(request)) as connection:
        if database.caller_member_id(connection) is None:
            return _no_member_record(request)
        return self_service.read_own_cards(connection)


@app.get("/me/certifications")
def list_my_certifications(request: Request):
    with database.member_transaction(_subject(request)) as connection:
        if database.caller_member_id(connection) is None:
            return _no_member_record(request)
        return self_service.read_own_certifications(connection)


@app.get("/me/waiver")
def get_my_waiver(request: Request):
    with database.member_transaction(_subject(request)) as connection:
        if database.caller_member_id(connection) is None:
            return _no_member_record(request)
        waiver = self_service.read_own_waiver(connection)
    if waiver is None:
        return problems.problem_response(
            problems.NO_WAIVER_RECORDED, request.url.path)
    return waiver


@app.get("/me/card-eligibility")
def get_my_card_eligibility(request: Request):
    with database.member_transaction(_subject(request)) as connection:
        if database.caller_member_id(connection) is None:
            return _no_member_record(request)
        return self_service.read_card_eligibility(connection)


def _no_member_record(request: Request):
    """What every self service read answers a sign in with no record behind it.

    Not an empty list. A member whose record an admin has not joined to their
    sign in yet has cards, and answering /me/cards with [] would tell them they
    have none.
    """
    return problems.problem_response(
        problems.NO_MEMBER_RECORD, request.url.path)


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
