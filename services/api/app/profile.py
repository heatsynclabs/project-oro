"""The one operation a member changes their own record with.

Two things decide what a member may change, and neither of them is here.

The field list below is the contract's `MemberSelfUpdate`. It is the operation's
vocabulary: a name it does not carry is refused before anything is sent, which
is what `additionalProperties: false` in docs/api/members-v1.yaml says happens.

What may be written is `enforce_profile_self_edit` in
db/migrations/004_security.sql and the constraints on the members table. That is
the rule, and nothing below repeats any of it. A value goes to the database as
it arrived and the refusal that comes back is turned into the shape the contract
declares. So the link check, the tier check and the address check each live in
exactly one place, which is the point of rule 5.

Finding 9 of docs/api/contract-review-notes.md asked which of those two layers
gets to refuse a field an admin owns, and the answer is written down there and
in the contract: this one, because the alternative hands a name straight to an
UPDATE, and the trigger returns early for an admin. An admin changing
`identity_subject` on their own record through a self service path would point
it at somebody else's sign in.
"""

from typing import Annotated

import psycopg
from psycopg import sql
from pydantic import BaseModel, ConfigDict, StringConstraints

# Trimmed and non empty, for the same reason app/first_sign_in.py trims: a name
# of three spaces is not a name, and members.name is NOT NULL rather than
# non empty, so the database has nothing to say about it.
Typed = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MemberSelfUpdate(BaseModel):
    """The contract's MemberSelfUpdate, property for property.

    Every field is optional and absence is what a PATCH turns on: the request
    carries what is changing and nothing else, so `model_fields_set` is the
    difference between "set this to null" and "leave this alone".
    """

    model_config = ConfigDict(extra="forbid")

    name: Typed | None = None
    display_name: str | None = None
    pronouns: str | None = None
    email: str | None = None
    phone: str | None = None
    postal_code: str | None = None
    tier_id: str | None = None
    current_skills: str | None = None
    desired_skills: str | None = None
    marketing_source: str | None = None
    emergency_name: str | None = None
    emergency_phone: str | None = None
    emergency_email: str | None = None
    twitter_url: str | None = None
    facebook_url: str | None = None
    github_url: str | None = None
    website_url: str | None = None
    email_visible: bool | None = None
    phone_visible: bool | None = None
    listed_in_directory: bool | None = None


# Which field a member should look at when a constraint refuses. This decides
# nothing: the constraints themselves are the rules, and every name below was
# read off the database rather than assumed, with
# `SELECT conname FROM pg_constraint WHERE conrelid = 'members'::regclass`.
LINK_FIELDS = ("twitter_url", "facebook_url", "github_url", "website_url")
LINK_CONSTRAINT = "social_urls_are_http"
TIER_CONSTRAINT = "members_tier_id_fkey"

A_LINK = "A link starts with http:// or https://"
A_TIER = ("That is not one of the lab's membership tiers, so nothing was "
          "saved. Ask for the list of tiers and send the id of one of them.")
NOT_EMPTY = ("This is the one field a member record cannot be without, so "
             "nothing was saved. Send a name, or leave the field out to keep "
             "the one that is there.")


def write_the_change(connection, asked: MemberSelfUpdate) -> None:
    """Send exactly what the request carried, and nothing else.

    A body with no fields in it changes nothing and is not a fault. Every
    property of MemberSelfUpdate is optional, so an empty object is a legal
    request, and an UPDATE with no assignments is not legal SQL.

    The column names are the model's own field names, which are the fixed list
    above and can never come from the request. They are still composed with
    `sql.Identifier` rather than pasted into a string, because the next person
    to add a field should not have to work out why that was safe.
    """
    changes = asked.model_dump(exclude_unset=True)
    if not changes:
        return
    columns = sorted(changes)
    connection.execute(
        sql.SQL("UPDATE members SET {assignments} "
                "WHERE id = current_member_id()").format(
            assignments=sql.SQL(", ").join(
                sql.SQL("{} = {}").format(sql.Identifier(column),
                                          sql.Placeholder())
                for column in columns)),
        [changes[column] for column in columns])


def what_the_database_refused(refusal: psycopg.Error,
                             asked: MemberSelfUpdate) -> list[dict] | None:
    """The database's refusal as the contract's per field errors, or None.

    None means this is not a refusal a member can act on, so it belongs to
    whatever handles it in app/refusals.py. The address already belonging to
    another member is the one that lands there on purpose: the contract answers
    it 409 rather than 422, and one place says that sentence.
    """
    diagnosis = getattr(refusal, "diag", None)
    named = getattr(diagnosis, "constraint_name", None)
    if named == LINK_CONSTRAINT:
        return [{"field": field, "detail": A_LINK}
                for field in _links_the_request_carried(asked)]
    if named == TIER_CONSTRAINT:
        return [{"field": "tier_id", "detail": A_TIER}]
    column = getattr(diagnosis, "column_name", None)
    if isinstance(refusal, psycopg.errors.NotNullViolation) and column:
        return [{"field": column, "detail": NOT_EMPTY}]
    return None


def _links_the_request_carried(asked: MemberSelfUpdate) -> list[str]:
    """Which of the four the member sent, because the constraint checks all
    four at once and reports itself rather than a column.

    Naming every link field when one of them is wrong would put an error on
    three fields a member did not touch. Naming the ones they sent is the most
    this can honestly say: if they sent two, one of the two is not a link and
    the database did not say which.
    """
    sent = [field for field in LINK_FIELDS if field in asked.model_fields_set]
    return sent or list(LINK_FIELDS)
