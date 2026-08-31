#!/usr/bin/env python3
"""GET /me/door-events, which is a member reading the record of their own
entries into a building.

Rule 13 of CLAUDE.md makes this an access record rather than a log line, and
db/migrations/004_security.sql is where that is enforced: a member reads their
own and an admin reads all of them. Every check below goes through the service
over HTTP, so what they prove is that the policy still decides the answer with a
web service in front of it.

What they cannot prove is measured rather than assumed. On 2026-08-30 the WHERE
in app/door_events.py was replaced with `WHERE true` and all fourteen of these
passed anyway, because member_reads_own_door_events filters the same rows and
this suite seats no admin. That WHERE earns its place for a caller holding
admin_reads_all_door_events, and nobody here holds it. Ida's entry is the most
recent of the six so that a leak, on the day one gets past the policy, arrives
at the top of Wren's first page rather than at the bottom of her last.

The rest of the file is the paging the contract declares: a limit, a cursor,
and a page that says whether there is anything older.
"""
import sys

from harness import fetch, mint, run

WREN = "sub-c-wren"
IDA = "sub-c-ida"
# Five entries for Wren in services/api/tests/fixtures.sql, two of them at the
# same instant.
WRENS_ENTRIES = 5
IDAS_ONE_ENTRY = "2025-06-05T21:00:00"


def page(subject, query=""):
    answer = fetch("/me/door-events" + query, mint(subject))
    assert answer.status == 200, (
        f"/me/door-events{query} answered {answer.status}: {answer.body}")
    return answer.json()


def test_a_member_reads_their_own_entries_most_recent_first():
    read = page(WREN)
    times = [entry["occurred_at"] for entry in read["items"]]
    assert len(times) == WRENS_ENTRIES, read
    assert times == sorted(times, reverse=True), times
    assert read["next_cursor"] is None, read


def test_an_entry_carries_what_the_door_reported():
    """The typed columns, and the detail object for whatever else arrived."""
    oldest = sorted(page(WREN)["items"],
                    key=lambda entry: entry["occurred_at"])[0]
    assert oldest["source"] == "controller", oldest
    assert oldest["event_key"] == "G", oldest
    assert oldest["door"] == "front", oldest
    assert oldest["raw_data"] == 42, oldest
    assert oldest["card_id"] is not None, oldest
    assert oldest["occurred_at"].startswith("2025-06-01T17:00:00"), oldest
    assert oldest["recorded_at"].startswith("2025-06-01T17:00:04"), oldest


def test_an_entry_that_was_buffered_says_when_it_happened_and_when_it_landed():
    """Collapsing the two would make every buffered entry look as though it
    happened at flush time, which is what the column comment on recorded_at in
    db/migrations/002_access.sql says the pair is for."""
    buffered = [entry for entry in page(WREN)["items"]
                if entry["source"] == "service"]
    assert len(buffered) == 2, buffered
    for entry in buffered:
        assert entry["occurred_at"].startswith("2025-06-04T20:00:00"), entry
        assert entry["recorded_at"].startswith("2025-06-04T20:11:00"), entry
        assert entry["detail"] == {"buffered": True}, entry


def test_a_member_does_not_read_another_members_entries():
    """Both halves, because Wren's list alone would pass against a service that
    answered everybody with nothing. Ida reads her own entry here to prove the
    row Wren does not get is a row that is there to be leaked."""
    wrens = page(WREN)["items"]
    assert all(not entry["occurred_at"].startswith(IDAS_ONE_ENTRY)
               for entry in wrens), wrens
    idas = page(IDA)["items"]
    assert len(idas) == 1, idas
    assert idas[0]["occurred_at"].startswith(IDAS_ONE_ENTRY), idas


def test_a_page_is_the_size_it_was_asked_for_and_says_where_to_continue():
    first = page(WREN, "?limit=2")
    assert len(first["items"]) == 2, first
    assert first["next_cursor"] is not None, first


def test_the_pages_walked_end_to_end_are_the_whole_list_and_no_more():
    """Two entries share an instant, so a cursor carrying only the time would
    either repeat one of them or drop it. This is the check that catches it."""
    seen = []
    cursor = None
    for _ in range(WRENS_ENTRIES + 2):
        query = "?limit=2" + (f"&cursor={cursor}" if cursor else "")
        read = page(WREN, query)
        seen.extend(read["items"])
        cursor = read["next_cursor"]
        if cursor is None:
            break
    assert cursor is None, "the pages never ended"
    ids = [entry["id"] for entry in seen]
    assert len(ids) == WRENS_ENTRIES, seen
    assert len(set(ids)) == WRENS_ENTRIES, f"a page repeated an entry: {ids}"
    whole = [entry["id"] for entry in page(WREN)["items"]]
    assert ids == whole, f"walked {ids}, in one page {whole}"


def test_the_last_page_says_there_is_nothing_older():
    """A page that came back short is the end of the list, and it has to say so
    rather than leave a client asking for a page that is always empty."""
    read = page(WREN, "?limit=" + str(WRENS_ENTRIES))
    assert len(read["items"]) == WRENS_ENTRIES, read
    assert read["next_cursor"] is None, read


def test_a_cursor_is_a_place_in_a_list_and_not_a_permission():
    """Ida asks with a cursor Wren's page handed out.

    That place is older than Ida's only entry, so the honest answer is nothing
    at all, and a page carrying anything is carrying somebody else's.
    """
    wrens_place = page(WREN, "?limit=1")["next_cursor"]
    assert wrens_place is not None, "Wren's first page ended the list"
    borrowed = page(IDA, "?cursor=" + wrens_place)
    assert borrowed["items"] == [], borrowed
    assert borrowed["next_cursor"] is None, borrowed


def test_a_member_with_no_entries_gets_an_empty_page():
    read = page("sub-c-solder")
    assert read["items"] == [], read
    assert read["next_cursor"] is None, read


def test_a_limit_outside_what_the_contract_declares_is_refused():
    """1 to 200, from the Limit parameter in docs/api/members-v1.yaml."""
    for asked in ("0", "201", "-1", "many"):
        refused = fetch("/me/door-events?limit=" + asked, mint(WREN))
        assert refused.status == 422, f"limit={asked}: {refused.body}"
        problem = refused.json()
        assert problem["type"].endswith("/invalid-request"), problem
        assert problem["errors"][0]["field"] == "limit", problem


def test_a_cursor_that_did_not_come_from_a_page_is_refused():
    refused = fetch("/me/door-events?cursor=halfway", mint(WREN))
    assert refused.status == 422, refused.body
    problem = refused.json()
    assert problem["type"].endswith("/invalid-request"), problem
    assert problem["errors"][0]["field"] == "cursor", problem
    assert "page" in problem["errors"][0]["detail"], problem


def test_a_sign_in_with_no_member_record_is_told_so():
    refused = fetch("/me/door-events", mint("sub-c-nobody-at-the-door"))
    assert refused.status == 401, refused.body
    problem = refused.json()
    assert problem["type"].endswith("/no-member-record"), problem
    assert problem["instance"] == "/me/door-events", problem


def test_nobody_reads_an_entry_without_a_token():
    refused = fetch("/me/door-events")
    assert refused.status == 401, refused.body
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body


def test_an_anonymous_caller_with_a_bad_cursor_is_still_anonymous():
    """The cursor is refused inside the transaction, after the database has
    said who this is, for the reason app/main.py gives about `fields` on the
    directory: a caller who may read nothing is told that first."""
    refused = fetch("/me/door-events?cursor=halfway")
    assert refused.status == 401, refused.body
    assert refused.json()["type"].endswith("/unauthenticated"), refused.body


sys.exit(run(dict(globals()), "door events"))
