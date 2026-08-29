#!/usr/bin/env python3
"""What the three implemented operations return, and what they withhold.

Every check here goes through the running service over HTTP. None of them
queries the database, because a check that queried it would be asking a
different question: db/tests/directory.sql and db/tests/profile.sql already
prove the policies hold at the database, and what is new here is that they
still hold with a web service in front of them.
"""
import sys

from harness import IDA, SOLDER, WREN, fetch, mint, run

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


sys.exit(run(dict(globals()), "members API"))
