"""RFC 9457 problem details, which is the only shape a refusal takes here.

The contract says every refusal carries a sentence a person wrote, naming the
rule that refused. The sentences below are the ones in
docs/api/members-v1.yaml, copied rather than paraphrased, so a client reading
the document and a client reading a response see the same words.

Only shape is meant literally, and it took two problems below to make it so.
An unknown path and a method a path does not take are answered by Starlette
before any endpoint here runs, and its answer is `{"detail": ...}` as
`application/json`. That is a second shape, and the contract opens by saying
errors are problem details in one shape everywhere.
app/main.py:refused_by_the_router turns both into NO_SUCH_PATH and
WRONG_METHOD, and check_members_api.py holds it there.
"""

import dataclasses

from fastapi.responses import JSONResponse

ERROR_BASE = "https://oro.heatsynclabs.org/errors/"


@dataclasses.dataclass(frozen=True)
class Problem:
    slug: str
    status: int
    title: str
    detail: str


UNAUTHENTICATED = Problem(
    slug="unauthenticated",
    status=401,
    title="Sign in first",
    detail=(
        "This request carried no valid access token, so nothing was read or "
        "changed. Sign in again, and if you keep getting sent back, your "
        "session has expired."
    ),
)

NOT_IN_DIRECTORY = Problem(
    slug="not-in-directory",
    status=404,
    title="Not in the directory",
    detail=(
        "Nobody with that id is listed. Members choose whether to appear, so "
        "somebody can be a member and still not be here."
    ),
)

INVALID_REQUEST = Problem(
    slug="invalid-request",
    status=422,
    title="That request could not be applied",
    detail=(
        "One field in this request is not usable, so nothing was saved. The "
        "errors list says which one and what it expects."
    ),
)

# Not a shape the contract declares, and the gap is real rather than an
# oversight in this service. /me declares 200 and 401 only, and a token this
# service verified whose subject matches no member row is neither. The database
# function that would claim or create that row, link_or_create_member in
# db/migrations/008_system_paths.sql, is called by no operation in the
# contract. docs/api/contract-review-notes.md finding 5 is the same gap.
#
# 401 because it is the status the contract does declare, and a sentence that
# says what actually happened, because the reader is about to go looking for a
# fault that is not on their side.
NO_MEMBER_RECORD = Problem(
    slug="no-member-record",
    status=401,
    title="This sign in is not linked to a member record",
    detail=(
        "The lab knows this sign in and has no member record joined to it, so "
        "there was nothing to read. Nothing here can join the two yet. Ask an "
        "admin to link your record."
    ),
)

# Starlette's own two refusals, said in the contract's shape. Neither is a
# response the contract declares, because it declares paths rather than the
# absence of them, and both are reachable from any client that guesses a URL.
NO_SUCH_PATH = Problem(
    slug="no-such-path",
    status=404,
    title="Nothing is served at that path",
    detail=(
        "This API has no operation at that path, so nothing was read or "
        "changed. Check the path against docs/api/members-v1.yaml, which "
        "lists every one there is."
    ),
)

WRONG_METHOD = Problem(
    slug="wrong-method",
    status=405,
    title="That path does not take this method",
    detail=(
        "This path exists and answers a different HTTP method, so nothing was "
        "read or changed. The Allow header on this response names the methods "
        "it does take."
    ),
)

UNEXPECTED = Problem(
    slug="unexpected",
    status=500,
    title="Something here is broken",
    detail=(
        "This request failed for a reason the service did not expect, so "
        "nothing was changed. The api container's log carries the fault. "
        "Try again, and tell an admin if it keeps happening."
    ),
)


def problem_response(problem: Problem, instance: str, errors=(),
                     headers=None) -> JSONResponse:
    """One refusal, in the one shape.

    `headers` carries through the headers whatever refused already set. The
    only one today is Allow on a 405, which RFC 9110 requires and which
    Starlette had put there before this replaced its body.
    """
    body = {
        "type": ERROR_BASE + problem.slug,
        "title": problem.title,
        "status": problem.status,
        "detail": problem.detail,
        "instance": instance,
    }
    if errors:
        body["errors"] = list(errors)
    return JSONResponse(
        status_code=problem.status,
        content=body,
        media_type="application/problem+json",
        headers=headers,
    )
