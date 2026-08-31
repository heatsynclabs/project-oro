#!/usr/bin/env python3
"""The four self service reads: cards, certifications, waiver, eligibility.

Every check goes through the running service over HTTP, for the reason
check_members_api.py gives: db/tests already proves the policies at the
database, and what is new here is that they still hold with a web service in
front of them.

Each endpoint is asked three questions. What it answers the member it belongs
to, what it answers a caller who is somebody else, and what it answers a caller
who is nobody. The middle one is the check that would catch a WHERE clause
going missing, and every one of these endpoints reads a table where another
member's rows are sitting one policy away.
"""
import sys

from harness import IDA, SOLDER, WREN, fetch, mint, run

# Wren's live card, from services/api/tests/fixtures.sql. The full number is
# here so a check can require it never to appear in a response.
WRENS_TAG = "A1B2C4D9"
SOLDERS_CARD = "dddddddd-0000-0000-0000-000000000003"


def read(path, subject):
    """One self service read, with a readable failure when it is refused."""
    answer = fetch(path, mint(subject))
    assert answer.status == 200, f"{path} answered {answer.status}: {answer.body}"
    return answer.json()


# ------------------------------------------------------------------- cards

def test_a_member_reads_their_own_cards_newest_first():
    cards = read("/me/cards", "sub-c-wren")
    assert len(cards) == 2, cards
    assert cards[0]["label"] == "Front desk spare", cards[0]
    assert cards[0]["active"] is True, cards[0]
    assert cards[0]["revoked_at"] is None, cards[0]
    assert cards[1]["active"] is False, cards[1]
    assert cards[1]["revoked_reason"] == "Left in a taxi.", cards[1]


def test_a_card_never_carries_a_door_controller_address():
    """MyCard rather than Card, and this is what holds it there.

    A slot is an EEPROM address on the controller. Wren's live card has one, so
    an endpoint that returned the row would return a real address rather than a
    null. Finding 1 of docs/api/contract-review-notes.md, and
    tools/mock/tests/check_contract.py holds the same rule against the mock.
    """
    for card in read("/me/cards", "sub-c-wren"):
        for hardware in ("controller_slot", "permission_mask"):
            assert hardware not in card, (
                f"/me/cards handed a member {hardware}, which names the door "
                f"hardware: {card}")


def test_a_tag_number_is_masked_to_its_last_four_characters():
    answer = fetch("/me/cards", mint("sub-c-wren"))
    assert answer.status == 200, answer.body
    assert answer.json()[0]["tag_number"] == "C4D9", answer.json()[0]
    assert WRENS_TAG not in answer.body, (
        "the full tag number of a card is in the response, so a photograph of "
        "the screen is a card somebody can clone")


def test_a_member_does_not_see_another_members_card():
    """The refusal half. Solder's card exists, and Wren must not be holding it.

    Read Wren's list alone and this passes against a service that returns
    nothing at all, so Solder reads his own card here to prove the row is
    there to be leaked.
    """
    wrens = read("/me/cards", "sub-c-wren")
    assert all(card["id"] != SOLDERS_CARD for card in wrens), wrens
    solders = read("/me/cards", "sub-c-solder")
    assert [card["id"] for card in solders] == [SOLDERS_CARD], solders


def test_a_member_with_no_card_gets_an_empty_list():
    assert read("/me/cards", "sub-c-ida") == []


def test_nobody_reads_a_card_without_a_token():
    refused = fetch("/me/cards")
    assert refused.status == 401, refused.body
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body


# ---------------------------------------------------------- certifications

def test_a_member_reads_their_own_certifications_with_the_tool_on_each():
    held = read("/me/certifications", "sub-c-wren")
    assert len(held) == 2, held
    by_tool = {row["certification_id"]: row for row in held}
    laser = by_tool["laser"]
    assert laser["certification"]["name"] == "Laser cutter", laser
    assert laser["certification"]["validity_months"] == 24, laser
    assert laser["note"] == "Signed off on the sample cut", laser
    assert laser["revoked_at"] is None, laser


def test_a_revoked_certification_stays_in_the_list_with_its_reason():
    """Somebody can be certified, revoked, and certified again, and an
    instructor needs the history. A list of live grants would lose it."""
    held = {row["certification_id"]: row
            for row in read("/me/certifications", "sub-c-wren")}
    mill = held["mill"]
    assert mill["revoked_at"] is not None, mill
    assert mill["revoked_reason"] == "Refresher owed after the head crash", mill


def test_a_member_does_not_see_another_members_certification():
    wrens = read("/me/certifications", "sub-c-wren")
    assert all(row["member_id"] == WREN for row in wrens), wrens
    idas = read("/me/certifications", "sub-c-ida")
    assert [row["member_id"] for row in idas] == [IDA], idas
    assert idas[0]["certification_id"] == "laser", idas


def test_nobody_reads_a_certification_without_a_token():
    refused = fetch("/me/certifications")
    assert refused.status == 401, refused.body
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body


# ------------------------------------------------------------------ waiver

def test_a_member_reads_the_most_recent_waiver_recorded_for_them():
    waiver = read("/me/waiver", "sub-c-wren")
    assert waiver["storage"] == "google-form", waiver
    assert waiver["reference"] == "response-8814", waiver
    assert waiver["signed_at"].startswith("2025-01-18"), waiver
    assert waiver["expires_at"] is None, waiver
    assert waiver["member_id"] == WREN, waiver


def test_a_waiver_carries_nothing_that_is_on_the_document():
    """The table holds no personal information on purpose, and this is the
    check that an endpoint did not start joining some in. db/tests/waivers.sql
    asserts the same thing about the column list."""
    waiver = read("/me/waiver", "sub-c-wren")
    for absent in ("name", "address", "emergency_name", "guardian",
                   "signature", "signature_ip"):
        assert absent not in waiver, f"/me/waiver handed back {absent}"


def test_a_member_with_no_waiver_gets_the_404_the_portal_reads_as_empty():
    """apps/members/index.html declares data-empty-on="404" on this section,
    so the status is load bearing rather than cosmetic."""
    refused = fetch("/me/waiver", mint("sub-c-ida"))
    assert refused.status == 404, refused.body
    assert refused.headers["Content-Type"].startswith(
        "application/problem+json"), refused.headers["Content-Type"]
    problem = refused.json()
    assert problem["type"].endswith("/no-waiver-recorded"), problem
    assert problem["title"] == "No waiver is recorded for you", problem
    assert problem["instance"] == "/me/waiver", problem


def test_a_member_does_not_read_another_members_waiver():
    """Ida gets a 404 while Wren's two rows sit in the table, so the 404 above
    is a refusal to leak rather than an empty table."""
    assert fetch("/me/waiver", mint("sub-c-ida")).status == 404
    assert read("/me/waiver", "sub-c-wren")["member_id"] == WREN


def test_nobody_reads_a_waiver_without_a_token():
    refused = fetch("/me/waiver")
    assert refused.status == 401, refused.body
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body


# -------------------------------------------------------- card eligibility

def test_a_member_who_meets_every_rule_is_eligible():
    """Wren is on the basic tier, in good standing, and joined in January 2025.
    card_access.tenure_months is 2 in db/seed/001_reference.sql."""
    standing = read("/me/card-eligibility", "sub-c-wren")
    assert standing["eligible"] is True, standing
    assert standing["eligible_on"] == "2025-03-06", standing
    assert standing["reason"].startswith("Eligible."), standing


def test_the_answer_carries_the_process_because_that_is_most_of_it():
    standing = read("/me/card-eligibility", "sub-c-wren")
    assert "nominates" in standing["process"], standing
    assert "Hack Your Hackerspace" in standing["process"], standing


def test_a_tier_below_the_minimum_is_refused_by_the_tier_rule():
    """Ida is a volunteer, which sorts below basic. The sentence names the
    tier the governance parameter holds rather than a number in this service."""
    standing = read("/me/card-eligibility", "sub-c-ida")
    assert standing["eligible"] is False, standing
    assert standing["reason"] == "Card access needs the basic tier or higher.", \
        standing


def test_a_lapsed_member_on_a_paying_tier_is_refused_by_standing():
    """Anvil is the only fixture who reaches this branch: everybody else fails
    on tier or tenure first and the function stops at the first failure."""
    standing = read("/me/card-eligibility", "sub-c-anvil")
    assert standing["eligible"] is False, standing
    assert standing["reason"] == "Card access needs a member in good standing.", \
        standing


def test_eligibility_answers_for_the_caller_and_not_for_whoever_asks_last():
    """Two members, two answers, in one suite. A service that read the wrong
    member id would answer both the same and every check above would still
    pass."""
    assert read("/me/card-eligibility", "sub-c-wren")["eligible"] is True
    assert read("/me/card-eligibility", "sub-c-anvil")["eligible"] is False


def test_nobody_reads_an_eligibility_without_a_token():
    refused = fetch("/me/card-eligibility")
    assert refused.status == 401, refused.body
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body


# ------------------------------- a sign in the members database has not met

def test_a_sign_in_with_no_member_record_is_told_so_by_every_one_of_them():
    """Not an empty list, and not an eligibility of false.

    A token this service verified whose subject matches no member record is a
    person who has not finished signing in, and every one of these paths says
    so in the same sentence. Answering /me/cards with [] would tell somebody
    who has cards that they have none.
    """
    for path in ("/me/cards", "/me/certifications", "/me/waiver",
                 "/me/card-eligibility"):
        refused = fetch(path, mint("sub-c-nobody-here"))
        assert refused.status == 401, f"{path}: {refused.status} {refused.body}"
        problem = refused.json()
        assert problem["type"].endswith("/no-member-record"), f"{path}: {problem}"
        assert problem["instance"] == path, problem


def test_the_unlisted_member_still_reads_their_own_things():
    """Solder is not in the directory. That is a directory setting and not a
    membership one, so nothing on these paths turns on it."""
    assert read("/me/cards", "sub-c-solder")[0]["id"] == SOLDERS_CARD
    assert read("/me/card-eligibility", "sub-c-solder")["eligible"] is False
    assert fetch("/me/waiver", mint("sub-c-solder")).status == 404
    assert read("/me/certifications", "sub-c-solder") == []


sys.exit(run(dict(globals()), "self service"))
