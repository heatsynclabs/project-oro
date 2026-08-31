"""Turning a verified sign in into a member record. The only write here.

`link_or_create_member` in db/migrations/008_system_paths.sql is the one path
in this system that writes a member without an admin.
tools/bootstrap/seat_one_admin.sql calls it to seat the first three admins, and
until POST /me existed that was its only caller: a person the identity service
knew and the members database did not was answered 401 and told to find an
admin. Finding 5 of docs/api/contract-review-notes.md is that gap from the
contract's side.

**No address from the request reaches that function**, and everything below
turns on it. The function claims an existing record when the address matches
one that has no sign in yet, which is how the paying members who never signed
up were meant to arrive. Claiming a person's record hands over their phone
number, their emergency contact, their waiver and their door history, so it
needs the address proved. An access token from the identity service in
compose.yaml carries no address to prove it with: measured on 2026-08-30
against a token from a real sign in through the real screens, one carries
`iss`, `sub`, `aud`, `exp`, `iat`, `nbf`, `client_id` and `jti`, and nothing
else. So this passes NULL, the claim branch cannot fire, and a member whose
record already exists is joined to it by an admin.

What that costs, and it is worth writing down for whoever closes it: a legacy
member who signs in before an admin has linked them gets a second, empty
record. The way out is a token carrying a verified address, which is a change
to what the portal asks for and to what the identity service asserts, not a
change here.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

# Trimmed, because a name of three spaces is not a name and members.name is
# NOT NULL. The refusal a caller gets says which field, per app/main.py.
Typed = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class FirstSignIn(BaseModel):
    """The body POST /me takes, which is the contract's FirstSignIn schema.

    `extra="forbid"` is the contract's `additionalProperties: false` and it is
    load bearing rather than tidiness. Standing, tier, orientation and the
    identity a record is joined by belong to an admin, and a first sign in is
    where somebody would try to set one.
    """

    model_config = ConfigDict(extra="forbid")

    name: Typed
    email: Typed | None = None


# The subject comes out of the transaction rather than out of the request. It
# is the same value either way, and taking it from the setting the transaction
# is already acting under means the record cannot be written for one person
# while the policies answer for another.
WRITE_THE_RECORD = """
SELECT link_or_create_member(
         current_setting('oro.identity_subject'), NULL::citext, %s) AS member_id
"""

# Only ever the caller's own row, and only when it has no address. This is not
# how a member changes their address later: PATCH /me is, and the trigger
# `profile_self_edit` in db/migrations/004_security.sql is what governs that.
#
# members.email is citext UNIQUE, so an address another record already carries
# is refused here, by the database, and the whole request rolls back with the
# record it had just written. That refusal is the answer to somebody typing
# another member's address into this operation.
SET_THE_ADDRESS = """
UPDATE members SET email = %s
 WHERE id = current_member_id() AND email IS NULL
"""

CALLER_ALREADY_KNOWN = "SELECT current_member_id() AS member_id"


def claim_or_create(connection, asked: FirstSignIn) -> bool:
    """Write the caller's member record if they have none. True when it wrote.

    The answer is what tells 201 from 200. It is read before the write rather
    than inferred from it, because `link_or_create_member` answers with an id
    whether it wrote a record or found one.
    """
    known = connection.execute(CALLER_ALREADY_KNOWN).fetchone()["member_id"]
    connection.execute(WRITE_THE_RECORD, (asked.name,))
    if known is None and asked.email is not None:
        connection.execute(SET_THE_ADDRESS, (asked.email,))
    return known is None
