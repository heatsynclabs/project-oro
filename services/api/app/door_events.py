"""A member reading the record of their own entries into a building.

Rule 13 of CLAUDE.md: this is an access record rather than a log, readable by
the member it concerns and by admins and by nobody else, and
`member_reads_own_door_events` in db/migrations/004_security.sql is where that
is decided. The WHERE below is a second question rather than a second copy of
that policy, for the reason app/self_service.py gives about every other /me
path: an admin holds `admin_reads_all_door_events`, so a query with no member
in it would answer an admin's own history with the whole building's.
"""

import base64
import binascii
import datetime

# The columns the contract's DoorEvent declares. dedupe_key is not one of them:
# it belongs to the door service's retry handling, per the column comment in
# db/migrations/002_access.sql, and a member has no use for it.
COLUMNS = """
SELECT id, occurred_at, recorded_at, source, event_key, door, card_id,
       raw_data, detail
  FROM door_events
 WHERE member_id = current_member_id()
"""

# Newest first, and the id breaks a tie. Two entries can share an instant: the
# door service buffers while the link is down and flushes on reconnect, so a
# cursor that carried only the time would either repeat one of a pair or lose
# it. door_events_member in db/migrations/002_access.sql indexes exactly
# (member_id, occurred_at DESC), which is this read.
NEWEST_FIRST = " ORDER BY occurred_at DESC, id DESC LIMIT %s"

# Two statements rather than one carrying a null cursor, because a comparison
# the planner has to keep for a value that is usually absent is a comparison
# that stops the index being used for the common page.
FIRST_PAGE = COLUMNS + NEWEST_FIRST
LATER_PAGE = COLUMNS + """
   AND (occurred_at, id) < (%s::timestamptz, %s::bigint)""" + NEWEST_FIRST

CURSOR_IS_NOT_ONE = ("A cursor is the next_cursor a page came back with, and "
                     "this is not one, so nothing was read. Ask for the first "
                     "page by leaving it out.")


class CursorIsNotOne(Exception):
    """What the endpoint turns into a 422 naming `cursor`.

    Not the contract's. listMyDoorEvents in docs/api/members-v1.yaml declares
    200 and 401 and nothing else, so this status is a gap in the contract
    rather than something it asks for. The same gap sits on ?fields= against
    the directory, where finding 2 of docs/api/contract-review-notes.md
    records it.
    """


def read_page(connection, limit: int, cursor: str | None) -> dict:
    """One page of the caller's own entries, and where to continue.

    One row more than the page is read, and it is the only way to know whether
    there is anything older without counting the whole table. That row is not
    returned: it is the answer to "is there a next page", and it becomes the
    cursor on the last row that is.
    """
    if cursor is None:
        rows = connection.execute(FIRST_PAGE, (limit + 1,)).fetchall()
    else:
        occurred_at, identifier = _read_cursor(cursor)
        rows = connection.execute(
            LATER_PAGE, (occurred_at, identifier, limit + 1)).fetchall()
    items = rows[:limit]
    there_is_more = len(rows) > limit
    return {
        "items": items,
        "next_cursor": _write_cursor(items[-1]) if there_is_more else None,
    }


def _write_cursor(row: dict) -> str:
    """Where a page stopped, as one opaque string.

    Base64 rather than the two values in the open, because the contract calls
    this opaque and because a timestamp written plainly carries a `+` that a
    query string reads as a space.
    """
    place = f"{row['occurred_at'].isoformat()} {row['id']}"
    return base64.urlsafe_b64encode(place.encode()).decode().rstrip("=")


def _read_cursor(cursor: str) -> tuple[datetime.datetime, int]:
    """The place a cursor names, or a refusal.

    Everything a caller could send is refused the same way, because a cursor is
    a value this API handed out and there is nothing useful to say about how a
    particular one is wrong.
    """
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        when, _, identifier = base64.urlsafe_b64decode(
            padded).decode().rpartition(" ")
        return datetime.datetime.fromisoformat(when), int(identifier)
    except (ValueError, binascii.Error, UnicodeDecodeError) as unreadable:
        raise CursorIsNotOne(CURSOR_IS_NOT_ONE) from unreadable
