#!/usr/bin/env python3
"""What the three implemented operations return, and what they withhold.

Every check here goes through the running service over HTTP. None of them
queries the database, because a check that queried it would be asking a
different question: db/tests/directory.sql and db/tests/profile.sql already
prove the policies hold at the database, and what is new here is that they
still hold with a web service in front of them.
"""
import os
import subprocess
import sys

from harness import IDA, SOLDER, WREN, fetch, mint, run

DATABASE_CONTAINER = os.environ["ORO_API_TEST_DATABASE_CONTAINER"]

DIRECTORY_KEYS = {"id", "name", "pronouns", "email", "phone", "current_skills",
                  "desired_skills", "joined_on"}


def test_a_member_reads_their_own_record():
    answer = fetch("/me", mint("sub-c-wren"))
    assert answer.status == 200, answer.body
    me = answer.json()
    assert me["id"] == WREN, me
    assert me["name"] == "Wren Kestrel", me
    assert me["phone"] == "480 555 0101", me
    assert me["postal_code"] == "85201", me
    assert me["emergency_phone"] == "480 555 0102", me
    assert me["standing"] == "good", me


def test_the_own_record_carries_the_tier_and_the_live_role():
    answer = fetch("/me", mint("sub-c-wren"))
    assert answer.status == 200, answer.body
    me = answer.json()
    assert me["tier_id"] == "basic", me
    assert me["tier"]["monthly_cents"] == 5000, me["tier"]
    assert me["tier"]["card_eligible"] is True, me["tier"]
    assert [held["role_id"] for held in me["roles"]] == ["host"], me["roles"]
    granted = me["roles"][0]
    assert granted["role"]["name"] == "Host", granted
    assert granted["role"]["grants_roles"] is False, granted
    assert granted["approval_id"] is None, granted


def test_the_own_record_withholds_the_columns_the_contract_reserves():
    answer = fetch("/me", mint("sub-c-wren"))
    assert answer.status == 200, answer.body
    me = answer.json()
    for withheld in ("identity_subject", "legacy_id", "legacy_member_level",
                     "deleted_at"):
        assert withheld not in me, f"/me handed back {withheld}"


def listed_directory(subject):
    """The directory, and a readable failure when it is a refusal instead.

    Without the status assertion a refused call fails later with a TypeError
    about string indices, which sends the reader after a fault in the check
    rather than the one in the service.
    """
    answer = fetch("/members", mint(subject))
    assert answer.status == 200, answer.body
    return answer.json()


def test_the_directory_lists_the_members_who_opted_in():
    listed = listed_directory("sub-c-wren")
    assert [row["id"] for row in listed] == [IDA, WREN], listed


def test_a_member_who_opted_out_is_not_in_the_directory():
    listed = listed_directory("sub-c-wren")
    assert all(row["id"] != SOLDER for row in listed), listed


def test_a_member_cannot_read_another_members_hidden_phone_number():
    """Half of the phase 3 exit criterion, proved through the service.

    The second half of this check is what makes the first half mean anything.
    A directory row with no phone number in it proves nothing on its own: the
    fixture might simply have none. Ida's own record carries hers, so the
    number exists and the directory is what withheld it.
    """
    listed = listed_directory("sub-c-wren")
    ida = [row for row in listed if row["id"] == IDA][0]
    assert ida["phone"] is None, f"Wren read Ida's phone number: {ida}"
    assert ida["email"] is None, f"Wren read Ida's email address: {ida}"

    hers = fetch("/me", mint("sub-c-ida"))
    assert hers.status == 200, hers.body
    herself = hers.json()
    assert herself["phone"] == "480 555 0102", herself
    assert herself["email"] == "ida@example.test", herself


def test_the_directory_shows_a_phone_number_its_owner_published():
    listed = listed_directory("sub-c-ida")
    wren = [row for row in listed if row["id"] == WREN][0]
    assert wren["phone"] == "480 555 0101", wren
    assert wren["email"] == "wren@example.test", wren


def test_the_directory_carries_the_view_columns_and_nothing_else():
    listed = listed_directory("sub-c-wren")
    for row in listed:
        assert set(row) == DIRECTORY_KEYS, sorted(set(row) ^ DIRECTORY_KEYS)


def test_the_directory_name_is_the_display_name_where_there_is_one():
    one = fetch("/members/" + IDA, mint("sub-c-wren"))
    assert one.status == 200, one.body
    assert one.json()["name"] == "Bram", one.body


def test_an_unlisted_member_is_not_found():
    refused = fetch("/members/" + SOLDER, mint("sub-c-wren"))
    assert refused.status == 404, refused.body
    assert refused.headers["Content-Type"].startswith(
        "application/problem+json"), refused.headers["Content-Type"]
    problem = refused.json()
    assert problem["type"].endswith("/not-in-directory"), problem
    assert problem["title"] == "Not in the directory", problem
    assert problem["status"] == 404, problem
    assert "Members choose whether to appear" in problem["detail"], problem
    assert problem["instance"] == "/members/" + SOLDER, problem


def test_an_id_that_is_not_a_uuid_is_not_found_rather_than_a_fault():
    refused = fetch("/members/nobody-at-all", mint("sub-c-wren"))
    assert refused.status == 404, refused.body
    assert refused.json()["title"] == "Not in the directory", refused.body


def test_a_member_id_spelled_in_uppercase_finds_the_same_member():
    """RFC 4122 lets a uuid be written in either case.

    The contract types this parameter `format: uuid` and says nothing about
    case, so both spellings below are the same member. Postgres prints a uuid
    in lowercase, and comparing the stored id as text against the parameter as
    written answered 404 for a member who is listed.
    """
    lower = fetch("/members/" + IDA, mint("sub-c-wren"))
    upper = fetch("/members/" + IDA.upper(), mint("sub-c-wren"))
    assert lower.status == 200, lower.body
    assert upper.status == 200, (
        "a listed member spelled in uppercase was answered "
        f"{upper.status}: {upper.body}")
    assert upper.json() == lower.json(), upper.body


def test_an_unknown_path_is_refused_in_the_one_shape():
    """FastAPI answers this itself, and its own answer is the wrong shape.

    The contract opens by saying errors are RFC 9457 problem details served as
    application/problem+json, in one shape everywhere. Starlette's default for
    a path nothing serves is {"detail": "Not Found"} as application/json.
    """
    refused = fetch("/nothing-is-served-here", mint("sub-c-wren"))
    assert refused.status == 404, refused.body
    assert refused.headers["Content-Type"].startswith(
        "application/problem+json"), refused.headers["Content-Type"]
    problem = refused.json()
    assert problem["type"].endswith("/no-such-path"), problem
    assert problem["status"] == 404, problem
    assert problem["instance"] == "/nothing-is-served-here", problem


def test_a_method_a_path_does_not_take_is_refused_in_the_one_shape():
    """The other default, and the Allow header RFC 9110 requires with it.

    This asked POST /me until 2026-08-30, when POST /me became an operation.
    The directory is the path that still takes one method, and a 405 has to be
    asked for on a path that has an operation: a path with none answers 404.
    """
    refused = fetch("/members", mint("sub-c-wren"), method="POST")
    assert refused.status == 405, refused.body
    assert refused.headers["Content-Type"].startswith(
        "application/problem+json"), refused.headers["Content-Type"]
    assert refused.headers["Allow"] == "GET", dict(refused.headers)
    problem = refused.json()
    assert problem["type"].endswith("/wrong-method"), problem
    assert problem["status"] == 405, problem


def test_fields_narrows_the_object_and_keeps_the_id():
    answer = fetch("/members?fields=name,pronouns", mint("sub-c-wren"))
    assert answer.status == 200, answer.body
    for row in answer.json():
        assert set(row) == {"id", "name", "pronouns"}, row


def test_fields_naming_something_the_directory_cannot_answer_is_refused():
    refused = fetch("/members?fields=emergency_phone", mint("sub-c-wren"))
    assert refused.status == 422, refused.body
    problem = refused.json()
    assert problem["type"].endswith("/invalid-request"), problem
    assert problem["errors"][0]["field"] == "emergency_phone", problem
    assert "does not carry this field" in problem["errors"][0]["detail"], problem


def test_the_refusal_names_what_the_directory_carries_once():
    """A small request should not buy a large response.

    The list of columns the directory has is one sentence about the `fields`
    parameter, not one sentence per name in it. Repeated per name, eight
    unknown names made a fifteen hundred byte response that said the same
    thing eight times.
    """
    asked = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta"]
    refused = fetch("/members?fields=" + ",".join(asked), mint("sub-c-wren"))
    assert refused.status == 422, refused.body
    assert refused.body.count("The directory carries") == 1, refused.body
    problem = refused.json()
    named = [entry["field"] for entry in problem["errors"]]
    assert named == asked + ["fields"], problem


def test_a_field_the_directory_cannot_answer_never_reads_the_directory():
    """The refusal is free, because the query that has no reader never runs.

    The suite's Postgres runs with log_statement=all, so every statement the
    service sends is in its log and this can count them. Read the directory
    before checking the fields and this goes red.
    """
    before = directory_reads()
    refused = fetch("/members?fields=emergency_phone", mint("sub-c-wren"))
    assert refused.status == 422, refused.body
    after = directory_reads()
    assert after == before, (
        "a request nobody could answer read the directory anyway: "
        f"{before} directory statements in the log before it, {after} after")


def test_an_anonymous_caller_asking_for_an_unanswerable_field_is_anonymous():
    """Which is why the field check waits for the database to say who this is.

    Nothing in this service turns an anonymous caller away, per rule 5 and the
    README. Moving the field check in front of the transaction would answer
    this 422, which reports on a directory the caller was never allowed to
    read.
    """
    refused = fetch("/members?fields=emergency_phone")
    assert refused.status == 401, refused.body
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body


def directory_reads() -> int:
    """How many times the directory view has been selected from, off the log."""
    printed = subprocess.run(["docker", "logs", DATABASE_CONTAINER],
                             capture_output=True, text=True, check=False)
    return (printed.stdout + printed.stderr).count("FROM member_directory")


sys.exit(run(dict(globals()), "members API"))
