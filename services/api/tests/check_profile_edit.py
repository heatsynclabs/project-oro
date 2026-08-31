#!/usr/bin/env python3
"""PATCH /me, which is the only way a member changes anything about themselves.

This file writes, so every check that changes something aims at one of the two
members nothing else in the suite reads. Quill is edited and read back. Fen is
who the refusals are aimed at, and after each of them his record has to read
exactly as services/api/tests/fixtures.sql left it.

The rule about what a member may change is `enforce_profile_self_edit` in
db/migrations/004_security.sql and the constraints on the members table. Three
of the checks below are about a refusal that comes from down there rather than
from this service: a link that is not a link, a tier that is not a tier, and an
address another member already holds.
"""
import sys

from harness import fetch, mint, run

QUILL = "sub-c-quill"
FEN = "sub-c-fen"

# Wren's, from the fixture. One address belongs to one member.
WRENS_EMAIL = "wren@example.test"


def change(subject, body):
    return fetch("/me", mint(subject), method="PATCH", body=body)


def record(subject):
    answer = fetch("/me", mint(subject))
    assert answer.status == 200, f"/me answered {answer.status}: {answer.body}"
    return answer.json()


def test_a_member_changes_their_own_name_and_reads_it_back():
    """The answer is the record, so a portal needs no second request for it."""
    answer = change(QUILL, {"name": "Quill Fletcher", "pronouns": "she/her"})
    assert answer.status == 200, f"{answer.status}: {answer.body}"
    changed = answer.json()
    assert changed["name"] == "Quill Fletcher", changed
    assert changed["pronouns"] == "she/her", changed
    read_again = record(QUILL)
    assert read_again["name"] == "Quill Fletcher", read_again
    assert read_again["pronouns"] == "she/her", read_again


def test_a_change_names_only_the_fields_it_carries():
    """A PATCH is not a PUT. Everything the body left out stays as it was."""
    before = record(FEN)
    answer = change(FEN, {"current_skills": "hand tools"})
    assert answer.status == 200, f"{answer.status}: {answer.body}"
    after = answer.json()
    assert after["current_skills"] == "hand tools", after
    assert after["email"] == before["email"], after
    assert after["joined_on"] == before["joined_on"], after


def test_a_member_declares_their_own_tier():
    """Deliberate, and it grants nothing. Membership is a donation rather than
    a subscription, so a member picks a level and arranges payment separately,
    and card access is decided by a vote. The trigger in
    db/migrations/004_security.sql spends five lines saying so."""
    answer = change(FEN, {"tier_id": "associate"})
    assert answer.status == 200, f"{answer.status}: {answer.body}"
    assert answer.json()["tier_id"] == "associate", answer.json()
    assert record(FEN)["standing"] == "unknown", "declaring a tier changed standing"


def test_changing_an_address_clears_the_date_it_was_confirmed_on():
    """The trigger does this, not this service. Quill's address is confirmed in
    the fixture and no operation in the contract can confirm one, so the date
    can only go one way."""
    before = record(QUILL)
    assert before["email_verified_at"] is not None, (
        "the fixture no longer carries a confirmed address, so this check "
        "proves nothing")
    answer = change(QUILL, {"email": "quill.fletcher@example.test"})
    assert answer.status == 200, f"{answer.status}: {answer.body}"
    changed = answer.json()
    assert changed["email"] == "quill.fletcher@example.test", changed
    assert changed["email_verified_at"] is None, changed


def test_a_field_an_admin_owns_is_refused_and_nothing_is_written():
    """Standing is set by an admin. This service does not take the field, so
    the request never reaches the database and the record cannot move.

    Finding 9 of docs/api/contract-review-notes.md is the decision behind the
    status: the contract declares what a member may change and this operation
    takes that and nothing else, so a name it does not take is a 422 rather
    than a 403.
    """
    refused = change(FEN, {"standing": "good"})
    assert refused.status == 422, f"{refused.status}: {refused.body}"
    assert refused.headers["Content-Type"].startswith(
        "application/problem+json"), refused.headers["Content-Type"]
    problem = refused.json()
    assert problem["type"].endswith("/invalid-request"), problem
    assert problem["instance"] == "/me", problem
    named = [entry["field"] for entry in problem["errors"]]
    assert named == ["standing"], problem
    assert record(FEN)["standing"] == "unknown", "standing was written anyway"


def test_the_identity_a_record_is_joined_by_is_not_a_field_either():
    """The one that would matter. The trigger lets an admin past it, so an
    endpoint that forwarded whatever it was given would let an admin point
    their own record at somebody else's sign in."""
    refused = change(FEN, {"identity_subject": "sub-c-somebody-else"})
    assert refused.status == 422, f"{refused.status}: {refused.body}"
    assert record(FEN)["name"] == "Fen", "the refused change wrote something"
    assert fetch("/me", mint(FEN)).status == 200, (
        "Fen can no longer read his own record, so the subject moved")


def test_a_link_that_is_not_a_link_is_refused_by_the_database():
    """`social_urls_are_http` in db/migrations/001_schema.sql is the rule. This
    service holds no second copy of it: it sends the value and turns what comes
    back into the contract's 422."""
    refused = change(FEN, {"website_url": "fen.example.test"})
    assert refused.status == 422, f"{refused.status}: {refused.body}"
    problem = refused.json()
    assert problem["type"].endswith("/invalid-request"), problem
    assert [entry["field"] for entry in problem["errors"]] == ["website_url"], \
        problem
    assert "http://" in problem["errors"][0]["detail"], problem
    assert record(FEN)["website_url"] == "https://fen.example.test", \
        "the refused link was written anyway"


def test_a_tier_that_is_not_a_tier_is_refused():
    """Tiers are rows in a table, so the refusal is a foreign key rather than a
    list in this service."""
    refused = change(FEN, {"tier_id": "platinum"})
    assert refused.status == 422, f"{refused.status}: {refused.body}"
    problem = refused.json()
    assert [entry["field"] for entry in problem["errors"]] == ["tier_id"], problem
    assert record(FEN)["tier_id"] != "platinum", problem


def test_a_member_cannot_take_an_address_another_member_holds():
    """members.email is citext UNIQUE, so this is the database refusing and
    there is no way for a caller to talk past it."""
    refused = change(FEN, {"email": WRENS_EMAIL})
    assert refused.status == 409, f"{refused.status}: {refused.body}"
    problem = refused.json()
    assert problem["type"].endswith("/email-already-known"), problem
    assert record(FEN)["email"] == "fen@example.test", \
        "the address was taken anyway"


def test_a_change_carrying_nothing_reads_the_record_back():
    """A body with no fields in it asks for nothing, which is an answer rather
    than a fault. Every property of MemberSelfUpdate is optional."""
    answer = change(FEN, {})
    assert answer.status == 200, f"{answer.status}: {answer.body}"
    assert answer.json()["name"] == "Fen", answer.json()


def test_a_null_on_a_field_that_cannot_be_null_is_refused_by_name():
    """Four columns are NOT NULL and the contract types none of them nullable.

    A null used to pass the model, reach the UPDATE, and come back as the
    database's NotNullViolation turned into one sentence: "Send a name". So a
    member who cleared their directory listing was told to send a name. The
    model refuses it now, and names the field the null was on.
    """
    for field in ("name", "listed_in_directory", "email_visible",
                  "phone_visible"):
        refused = change(FEN, {field: None})
        assert refused.status == 422, f"{field}: {refused.status} {refused.body}"
        errors = refused.json()["errors"]
        assert [named["field"] for named in errors] == [field], (
            f"a null on {field} was reported against {errors}")


def test_a_sign_in_with_no_member_record_cannot_change_a_profile():
    refused = change("sub-c-nobody-editing", {"name": "Nobody"})
    assert refused.status == 401, f"{refused.status}: {refused.body}"
    problem = refused.json()
    assert problem["type"].endswith("/no-member-record"), problem
    assert problem["instance"] == "/me", problem


def test_nobody_changes_a_profile_without_a_token():
    refused = fetch("/me", method="PATCH", body={"name": "Anybody"})
    assert refused.status == 401, refused.body
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body


sys.exit(run(dict(globals()), "profile edit"))
