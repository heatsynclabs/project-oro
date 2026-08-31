"""Every refusal that is not an endpoint's own, said in the contract's shape.

The contract opens by saying errors are RFC 9457 problem details in one shape
everywhere. Four things answer a request before or instead of an endpoint here,
and each of them has a shape of its own: Starlette answers an unknown path and
an unsupported method, FastAPI answers a body it could not read, the database
raises, and anything else falls out as a 500. This file is where those become
the one shape.

It is separate from app/main.py because rule 6 puts a ceiling on a file and
main.py is the routes. `install` is called once, from there.
"""

import logging

import psycopg
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as RouterRefusal

from . import database, problems

_log = logging.getLogger("oro.api")


def install(app) -> None:
    """Every handler below, on the application app/main.py builds."""
    app.add_exception_handler(psycopg.errors.RaiseException,
                              refused_by_the_database)
    app.add_exception_handler(psycopg.errors.UniqueViolation,
                              refused_by_a_unique_constraint)
    app.add_exception_handler(RouterRefusal, refused_by_the_router)
    app.add_exception_handler(RequestValidationError, refused_before_the_endpoint)
    app.add_exception_handler(Exception, anything_else)


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
    if database.REMOVED_RECORD_REFUSAL in message:
        _log.info("refused by the database: %s", message)
        return problems.problem_response(
            problems.RECORD_WAS_REMOVED, request.url.path
        )
    _log.warning("the database refused this request: %s", message)
    return problems.problem_response(problems.UNEXPECTED, request.url.path)


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


async def refused_before_the_endpoint(request: Request,
                                      refusal: RequestValidationError):
    """A request FastAPI could not read, said in the contract's shape.

    FastAPI answers this one itself, as `{"detail": [...]}` in
    application/json, which is the third shape after the two
    refused_by_the_router catches. `loc` starts with the word body or the word
    query, and what a caller wants is the field it named.
    """
    errors = [
        {"field": ".".join(str(part) for part in named["loc"][1:]) or "body",
         "detail": _readable(named)}
        for named in refusal.errors()
    ]
    return problems.problem_response(
        problems.INVALID_REQUEST, request.url.path, errors=errors)


# Pydantic's sentence for a field an operation does not take is "Extra inputs
# are not permitted", which reads as a machine talking about itself. The rest
# of its messages name the value and are worth passing on as they are.
# Read by a person as often as by a client, because the members portal shows
# each field's message beside the box it is about. So it says what to do first
# and where the full list is second.
NOT_A_FIELD_HERE = ("This does not change that, so nothing was saved. An admin "
                    "sets it. docs/api/members-v1.yaml lists what this "
                    "operation does take.")


def _readable(named: dict) -> str:
    if named.get("type") == "extra_forbidden":
        return NOT_A_FIELD_HERE
    return named["msg"]


async def anything_else(request: Request, fault: Exception):
    _log.exception("unhandled fault answering %s", request.url.path)
    return problems.problem_response(problems.UNEXPECTED, request.url.path)
