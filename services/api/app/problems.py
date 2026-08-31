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
app/refusals.py:refused_by_the_router turns both into NO_SUCH_PATH and
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
        "One field in this request is not usable, so nothing was saved. "
        "Every field it could not use is named below with what it expects."
    ),
)

# 401 rather than a status of its own, because it is the status the contract
# declares on every one of these paths, and a sentence that says what actually
# happened, because the reader is about to go looking for a fault that is not
# on their side. The Unauthenticated response in docs/api/members-v1.yaml names
# this slug beside its own.
#
# The last sentence stopped being "ask an admin" on 2026-08-30, when POST /me
# landed. A person reading this has somewhere to go now, and the operation that
# takes them there is named. docs/api/contract-review-notes.md finding 5 is the
# gap it closes.
NO_MEMBER_RECORD = Problem(
    slug="no-member-record",
    status=401,
    title="This sign in is not linked to a member record",
    detail=(
        "The lab knows this sign in and has no member record joined to it, so "
        "there was nothing to read. Writing one is the next thing to do, and "
        "the members portal offers it as a button. If the lab already has a "
        "record for you, an admin joins it to this sign in."
    ),
)

# The words are the contract's, from the 404 on /me/waiver. That a waiver is
# missing is an answer rather than a fault, and the members portal reads this
# status as an empty section: apps/members/index.html carries
# data-empty-on="404" on that view.
NO_WAIVER_RECORDED = Problem(
    slug="no-waiver-recorded",
    status=404,
    title="No waiver is recorded for you",
    detail=(
        "Nobody has recorded a waiver for you, so there was nothing to read. "
        "That is an answer rather than a fault. An admin records one once you "
        "have signed it."
    ),
)

# Raised by the database, never by a check here. members.email is citext UNIQUE
# in db/migrations/001_schema.sql, so this is the constraint speaking and there
# is no way for a caller to talk past it.
EMAIL_ALREADY_KNOWN = Problem(
    slug="email-already-known",
    status=409,
    title="That email already belongs to a member",
    detail=(
        "An email address identifies one member, and another member record "
        "already carries this one, so nothing was saved. An admin can find "
        "that record and merge the two."
    ),
)

# Raised by link_or_create_member in db/migrations/015_removed_records_sign_in.sql,
# never by a check here. A member whose record was removed reads as no member
# at all, so every read sends them to POST /me, and before 015 that operation
# fell through to an INSERT that hit members_identity_subject_key and answered
# 500 every time, forever.
#
# 409 rather than 404, because the record is there and the state it is in is
# what refuses the request, and because POST /me already declares 409 in
# docs/api/members-v1.yaml. Removal is reversible by design, per the deleted_at
# comment in db/migrations/001_schema.sql, so the sentence names the way back.
RECORD_WAS_REMOVED = Problem(
    slug="record-was-removed",
    status=409,
    title="Your member record was removed",
    detail=(
        "This sign in belongs to a member record the lab removed, so nothing "
        "was read or written. Removing a record is reversible and an admin "
        "restores it. Signing up again would leave a second record beside the "
        "first, so this refuses instead."
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
