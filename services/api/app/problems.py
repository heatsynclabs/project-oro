"""RFC 9457 problem details, which is the only shape a refusal takes here.

The contract says every refusal carries a sentence a person wrote, naming the
rule that refused. The sentences below are the ones in
docs/api/members-v1.yaml, copied rather than paraphrased, so a client reading
the document and a client reading a response see the same words.
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


def problem_response(problem: Problem, instance: str, errors=()) -> JSONResponse:
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
    )
