#!/usr/bin/env python3
"""POST /me, which is the only way a sign in becomes a member record.

This file writes to the database, which nothing else in the suite does, so
three things about it are deliberate.

Every check signs in as a subject of its own. harness.run calls the checks in
the order their names sort, which is not the order they are written in, so two
checks sharing a subject would pass or fail on which one ran first.

It runs after check_members_api.py, because the shell glob in run.sh is sorted
and `members_api` sorts before `members_first_sign_in`. A record written here
is listed in the directory, since `listed_in_directory` defaults true in
db/migrations/001_schema.sql, and the directory checks assert exactly who is in
it.

It also deletes what it wrote, whether or not a check failed, so that ordering
is a second belt rather than the only one. The deletion runs as the superuser,
which is what a fixture needs and what no check is allowed to use.
"""
import os
import subprocess
import sys

from harness import STRANGER_KEY, fetch, mint, run

DATABASE_CONTAINER = os.environ["ORO_API_TEST_DATABASE_CONTAINER"]

# Every subject this file signs in as. They share a prefix, so the cleanup at
# the bottom names them in one statement and cannot reach a fixture person.
SUBJECT_PREFIX = "sub-c-first-sign-in-"
WRITES = SUBJECT_PREFIX + "writes"
READS_BACK = SUBJECT_PREFIX + "reads-back"
GRANTS_NOTHING = SUBJECT_PREFIX + "grants-nothing"
TWICE = SUBJECT_PREFIX + "twice"
TAKEN = SUBJECT_PREFIX + "taken-address"
NAMELESS = SUBJECT_PREFIX + "nameless"
FORGED = SUBJECT_PREFIX + "forged"

# Ida's address, which belongs to a record somebody is already signed in to.
IDAS_EMAIL = "ida@example.test"


def in_the_database(statement: str) -> str:
    """One value out of the database, read as the superuser.

    Only the checks about what was written use this. Everything else asks the
    service, because a check that queried the database directly would be asking
    a different question.
    """
    printed = subprocess.run(
        ["docker", "exec", DATABASE_CONTAINER, "psql", "-U", "postgres",
         "-d", "oro", "-tAq", "-c", statement],
        capture_output=True, text=True, check=True)
    return printed.stdout.strip()


def records_for(subject: str) -> int:
    return int(in_the_database(
        f"SELECT count(*) FROM members WHERE identity_subject = '{subject}'"))


def first_sign_in(subject: str, body: dict):
    return fetch("/me", mint(subject), method="POST", body=body)


def test_a_first_sign_in_writes_a_member_record():
    answer = first_sign_in(WRITES, {"name": "Kestrel Newcomer",
                                    "email": "kestrel@example.test"})
    assert answer.status == 201, f"{answer.status}: {answer.body}"
    assert answer.headers["Location"] == "/me", dict(answer.headers)
    made = answer.json()
    assert made["name"] == "Kestrel Newcomer", made
    assert made["email"] == "kestrel@example.test", made
    assert made["id"], made
    assert records_for(WRITES) == 1, records_for(WRITES)


def test_the_record_a_first_sign_in_writes_is_the_one_get_me_answers():
    """The pair a portal actually makes: sign in, then read yourself.

    Before this operation existed, a verified token for somebody with no record
    was the end of the road, and services/api/README.md said so under what was
    deliberately missing.
    """
    made = first_sign_in(READS_BACK, {"name": "Reads Back"})
    assert made.status == 201, f"{made.status}: {made.body}"
    read = fetch("/me", mint(READS_BACK))
    assert read.status == 200, f"{read.status}: {read.body}"
    assert read.json()["id"] == made.json()["id"], read.body
    assert read.json()["name"] == "Reads Back", read.body


def test_a_first_sign_in_grants_nothing():
    """No role, no tier, no card, standing unknown. The one path that writes a
    member record without an admin must not be a way to become one."""
    made = first_sign_in(GRANTS_NOTHING,
                         {"name": "Grants Nothing",
                          "email": "grants-nothing@example.test"}).json()
    assert made["roles"] == [], made
    assert made["tier_id"] is None, made
    assert made["standing"] == "unknown", made
    assert made["email_verified_at"] is None, (
        f"an address nothing has checked came back verified: {made}")
    assert fetch("/me/cards", mint(GRANTS_NOTHING)).json() == []


def test_signing_in_twice_answers_the_same_record_and_writes_one_row():
    """The question a portal that cannot remember asks by accident.

    Two POSTs, and the second is 200 rather than 201 because nothing was
    written. link_or_create_member answers with the record it already holds for
    a subject before it looks at anything else, so the second call is a read.
    """
    first = first_sign_in(TWICE, {"name": "Twice Over"})
    second = first_sign_in(TWICE, {"name": "Somebody Else Entirely"})
    assert first.status == 201, f"{first.status}: {first.body}"
    assert second.status == 200, f"{second.status}: {second.body}"
    assert second.json()["id"] == first.json()["id"], second.body
    assert second.json()["name"] == "Twice Over", (
        f"the second call rewrote the name, so it was not a read: {second.body}")
    assert records_for(TWICE) == 1, (
        f"{records_for(TWICE)} member records for one sign in")


def test_a_first_sign_in_never_claims_a_record_by_the_address_typed_in():
    """The reason no address from a request body reaches link_or_create_member.

    That function claims an unclaimed record carrying a matching address, which
    is how the paying members who never signed up were meant to arrive.
    Claiming somebody's record by their address needs the address proved, and
    an access token from the identity service carries no address to prove it
    with, measured on 2026-08-30. So this operation passes none, and the unique
    constraint on members.email is what answers.
    """
    refused = first_sign_in(TAKEN, {"name": "Not Ida", "email": IDAS_EMAIL})
    assert refused.status == 409, f"{refused.status}: {refused.body}"
    problem = refused.json()
    assert problem["type"].endswith("/email-already-known"), problem
    assert problem["status"] == 409, problem
    assert records_for(TAKEN) == 0, (
        "a record was written for a request that was refused, so the refusal "
        "did not roll back")
    still_hers = in_the_database(
        f"SELECT identity_subject FROM members WHERE email = '{IDAS_EMAIL}'")
    assert still_hers == "sub-c-ida", (
        f"Ida's record is now signed in to by {still_hers!r}")


def test_a_first_sign_in_with_no_name_is_refused_in_the_one_shape():
    """FastAPI answers a body it cannot read itself, and its answer is the
    wrong shape. members.name is NOT NULL and the token carries no name, so a
    request with none has nothing to write."""
    refused = first_sign_in(NAMELESS, {})
    assert refused.status == 422, f"{refused.status}: {refused.body}"
    assert refused.headers["Content-Type"].startswith(
        "application/problem+json"), refused.headers["Content-Type"]
    problem = refused.json()
    assert problem["type"].endswith("/invalid-request"), problem
    assert problem["errors"][0]["field"] == "name", problem
    assert records_for(NAMELESS) == 0, "a record with no name was written"


def test_a_name_of_nothing_but_spaces_is_refused():
    refused = first_sign_in(NAMELESS, {"name": "   "})
    assert refused.status == 422, f"{refused.status}: {refused.body}"
    assert refused.json()["errors"][0]["field"] == "name", refused.body


def test_a_field_this_operation_does_not_take_is_refused():
    """Standing, tier and the identity a record is joined by belong to an
    admin, and a first sign in is the moment somebody would try to set one."""
    refused = first_sign_in(NAMELESS, {"name": "Chancer", "standing": "good"})
    assert refused.status == 422, f"{refused.status}: {refused.body}"
    assert "standing" in refused.body, refused.body
    assert records_for(NAMELESS) == 0, "the request wrote a record anyway"


def test_a_first_sign_in_with_no_token_writes_nothing():
    refused = fetch("/me", method="POST", body={"name": "Anonymous"})
    assert refused.status == 401, f"{refused.status}: {refused.body}"
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body


def test_a_first_sign_in_on_a_forged_token_writes_nothing():
    """A signature this service cannot verify is not a sign in at all, and a
    write path is where that matters most."""
    refused = fetch("/me", mint(FORGED, key_path=STRANGER_KEY),
                    method="POST", body={"name": "Forged"})
    assert refused.status == 401, f"{refused.status}: {refused.body}"
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body
    assert records_for(FORGED) == 0, "a forged token wrote a member record"


def clean_up() -> None:
    """Remove every record this file wrote, whatever happened above."""
    in_the_database("DELETE FROM members WHERE identity_subject LIKE "
                    f"'{SUBJECT_PREFIX}%'")


try:
    failures = run(dict(globals()), "first sign in")
finally:
    clean_up()
sys.exit(failures)
