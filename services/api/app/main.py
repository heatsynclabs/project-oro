"""The members API, ten operations of the twenty four in the contract.

Read services/api/README.md first. It says which ten, why the service exists
before the phase it belongs to, and what is deliberately missing. Every refusal
that is not an endpoint's own lives in app/refusals.py.

The generated OpenAPI document and the interactive pages FastAPI would serve
are turned off. docs/api/members-v1.yaml is the contract, it was written before
this service, and a second document describing ten operations would disagree
with it on the other fourteen. Rule 10 asks for the document to be verified
against the running service, and that check belongs with the operation that
completes the set rather than with the tenth.
"""

import contextlib
import logging

import psycopg
from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from . import (config, database, door_events, first_sign_in, identity, members,
               problems, profile, refusals, self_service)

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
refusals.install(app)


def _subject(request: Request) -> str | None:
    return identity.subject_from(request.headers.get("authorization"))


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


@app.patch("/me")
def update_me(request: Request, asked: profile.MemberSelfUpdate):
    """A member changing their own record, and reading it back in one request.

    The refusals that reach the caller from down in the database are here
    rather than in app/refusals.py because naming the field one of them is
    about needs the request, and a handler only has the exception. Everything
    it does not recognise is re-raised and answered there, which is what
    carries the 409 on an address another member already holds.
    """
    try:
        with database.member_transaction(_subject(request)) as connection:
            if database.caller_member_id(connection) is None:
                return _no_member_record(request)
            profile.write_the_change(connection, asked)
            return members.read_own_member(connection)
    except psycopg.errors.IntegrityError as refused:
        errors = profile.what_the_database_refused(refused, asked)
        if errors is None:
            raise
        return problems.problem_response(
            problems.INVALID_REQUEST, request.url.path, errors=errors)


@app.get("/me/door-events")
def list_my_door_events(request: Request, cursor: str | None = None,
                        limit: int = Query(50, ge=1, le=200)):
    """A page of the caller's own entries into the building.

    The cursor is refused inside the transaction for the reason list_directory
    gives about `fields`: a caller the database has not identified is
    anonymous, and 401 is the honest answer before anything is said about what
    they asked for.
    """
    with database.member_transaction(_subject(request)) as connection:
        if database.caller_member_id(connection) is None:
            return _no_member_record(request)
        try:
            return door_events.read_page(connection, limit, cursor)
        except door_events.CursorIsNotOne as refused:
            return problems.problem_response(
                problems.INVALID_REQUEST, request.url.path,
                errors=[{"field": "cursor", "detail": str(refused)}])


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
