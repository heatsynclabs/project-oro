#!/usr/bin/env python3
"""The wire protocol codec, checked against the bytes the firmware emits.

Every literal in this file was taken from the protocol reference read directly
from `Open_Access_Control_Ethernet.ino`. If the controller is ever reflashed,
these are the tests that go red first.

    python3 services/door/tests/test_wire.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from door.adapters.base import ControllerRefused  # noqa: E402
from door.adapters.oac_ethernet import firmware, slot_range, wire  # noqa: E402
from door.domain.slots import SlotEntry, SlotOutOfRange  # noqa: E402
from door.domain.status import DoorAction  # noqa: E402

PASSWORD = "1234"

TABLE_BODY = (
    "authok\r\n<pre>\r\nUserNum: Usermask: TagNum:\r\n"
    "0\t255\t0\r\n"
    "10\t1\tABCD\r\n"
    "11\t255\tFFFFFFFF\r\n"
    "12\t1\t1A2B3C4D\r\n"
    "</pre>\r\n"
)

STATUS_BODY = (
    '{\r\n"armed":0,"activated":0\r\n,"alarm_3":1\r\n,"alarm_2":1\r\n'
    ',"door_1_locked":1\r\n,"door_2_locked":0\r\n}\r\n'
)


def _raises(exc, fn, *args):
    try:
        fn(*args)
    except exc:
        return True
    return False


# --------------------------------------------------------------- requests

def test_the_status_request_carries_no_password():
    """Status is the only unauthenticated command. Sending the password with it
    would set the global privilege bit for the whole VLAN, for a read that does
    not need it."""
    assert PASSWORD not in wire.status_path()


def test_the_status_request_is_the_status_command():
    assert wire.status_path() == "?9"


def test_a_privileged_request_logs_out_in_the_same_request():
    """The trailing form makes login and logout atomic, so a crash between them
    cannot strand the controller privileged on the VLAN."""
    assert wire.read_table_path(PASSWORD).endswith("&e=" + PASSWORD)


def test_a_slot_write_zero_pads_the_slot_the_mask_and_the_tag():
    entry = SlotEntry(10, "ABCD", 1)
    assert wire.write_slot_path(entry, PASSWORD) == "?m010&p001&t0000ABCD&e=1234"


def test_the_offset_from_the_write_command_to_the_tag_is_exactly_ten():
    """The firmware's only length validation is that `&t` sits exactly 10
    characters after `?m`. Anything else answers `err:query`."""
    path = wire.write_slot_path(SlotEntry(199, "1A2B3C4D", 255), PASSWORD)
    assert path.index("&t") - path.index("?m") == 10


def test_a_slot_clear_names_the_slot_zero_padded():
    assert wire.clear_slot_path(10, PASSWORD) == "?r010&e=1234"


def test_opening_a_door_is_a_pulse_and_unlocking_it_is_not():
    assert wire.door_action_path(1, DoorAction.OPEN, PASSWORD) == "?o1&e=1234"
    assert wire.door_action_path(1, DoorAction.UNLOCK, PASSWORD) == "?u=1&e=1234"
    assert wire.door_action_path(2, DoorAction.LOCK, PASSWORD) == "?l=2&e=1234"


def test_a_request_is_refused_if_the_controller_would_truncate_it():
    """The firmware accumulates the request into a String capped at 100 and
    initialised as `String(100)`, which constructs the text "100", so only the
    first 97 bytes are ever seen."""
    assert _raises(ValueError, wire.build_http_request, "?a&" + "x" * 200)


def test_the_request_line_is_what_a_socket_would_put_on_the_wire():
    assert wire.build_http_request("?9") == b"GET /?9 HTTP/1.0\r\n\r\n"


# --------------------------------------------------------------- responses

def test_the_body_is_taken_from_after_the_fixed_header_block():
    raw = (b"HTTP/1.1 200 OK\r\nCache-Control: no-store\r\n"
           b"Content-Type: text/html\r\n\r\nauthok\r\n")
    assert wire.body_of(raw) == "authok\r\n"


def test_the_card_table_reports_only_occupied_slots():
    table = wire.parse_card_table(TABLE_BODY)
    assert [entry.slot for entry in table] == [10, 12]


def test_a_never_written_slot_is_not_a_card():
    """A slot that has never held a card prints tag 0."""
    assert all(entry.tag != "0" for entry in wire.parse_card_table(TABLE_BODY))


def test_a_deleted_slot_is_not_a_card():
    """Deleting a slot sets all five bytes to 0xFF."""
    assert 11 not in [entry.slot for entry in wire.parse_card_table(TABLE_BODY)]


def test_the_card_table_keeps_the_permission_mask():
    table = wire.parse_card_table(TABLE_BODY)
    assert table[0].mask == 1 and table[0].tag == "ABCD"


def test_the_status_payload_parses_despite_its_embedded_line_breaks():
    status = wire.parse_status(STATUS_BODY)
    assert status.locked == {1: True, 2: False}


def test_the_status_payload_reports_the_alarm():
    status = wire.parse_status(STATUS_BODY)
    assert status.alarm_armed == 0 and status.alarm_activated == 0


def test_an_unwritten_alarm_byte_is_reported_as_255_rather_than_guessed():
    body = ('{\r\n"armed":255,"activated":255\r\n,"alarm_3":0\r\n,"alarm_2":0\r\n'
            ',"door_1_locked":1\r\n,"door_2_locked":1\r\n}\r\n')
    assert wire.parse_status(body).alarm_armed == 255


def test_the_status_payload_parses_when_an_action_printed_before_it():
    body = "authok\r\nUnlocked 1." + STATUS_BODY
    assert wire.parse_status(body).locked == {1: True, 2: False}


def test_a_failed_login_is_an_error_and_not_an_empty_table():
    """The status code is always 200. Errors are strings in the body, so a
    client that trusts the status line reads a failure as an empty card table
    and then plans to clear every slot."""
    assert _raises(ControllerRefused, wire.parse_card_table, "authfail\r\n")


def test_a_command_sent_without_a_login_is_an_error():
    assert _raises(ControllerRefused, wire.parse_card_table,
                   "<a href='/'>Not logged in.</a>")


def test_a_malformed_query_is_an_error():
    assert _raises(ControllerRefused, wire.parse_slot_dump, "err:query\r\n")


def test_a_bad_door_number_is_an_error():
    assert _raises(ControllerRefused, wire.parse_status, "err:door#\r\n")


# --------------------------------------------------------- the door actions

def test_a_door_action_the_controller_refused_is_an_error():
    """Every answer is HTTP 200 with the error as a string in the body, so an
    unlock refused for a stale password looks exactly like one that worked
    unless the body is read. The member standing at the door is told it
    opened."""
    assert _raises(ControllerRefused, wire.parse_door_action,
                   "authfail\r\n", 1, DoorAction.UNLOCK)


def test_a_door_action_the_controller_did_not_confirm_is_an_error():
    """`?o1` answers `Opened 1.`. Anything else means the pulse did not run."""
    assert _raises(ControllerRefused, wire.parse_door_action,
                   "authok\r\n", 1, DoorAction.OPEN)


def test_an_unlock_is_believed_when_the_controller_names_the_door():
    wire.parse_door_action("authok\r\nUnlocked 1." + STATUS_BODY, 1,
                           DoorAction.UNLOCK)


def test_a_lock_is_believed_from_the_flag_the_controller_reports():
    """`?l=1` prints no sentence at all, only the status payload, so the flag
    is the only evidence there is."""
    wire.parse_door_action("authok\r\n" + STATUS_BODY, 1, DoorAction.LOCK)


def test_a_lock_that_did_not_take_is_an_error():
    """Door 2 is unlocked in this payload, so a lock of door 2 that answers it
    did not happen."""
    assert _raises(ControllerRefused, wire.parse_door_action,
                   "authok\r\n" + STATUS_BODY, 2, DoorAction.LOCK)


# ----------------------------------------------------------------- the slots

def test_the_slot_past_the_end_of_the_eeprom_is_refused_by_the_adapter():
    """The firmware's own bounds check at line 1451 reads `>` and not `>=`, so
    slot 200 passes it and its five bytes land on the persisted alarm state.
    The range is EEPROM geometry, so the refusal is the adapter's rather than
    the domain's."""
    past_the_end = slot_range.LAST_ADDRESSABLE + 1
    assert _raises(SlotOutOfRange, wire.write_slot_path,
                   SlotEntry(past_the_end, "ABCD", 1), PASSWORD)


def test_a_slot_the_lab_reserves_cannot_be_written_but_can_be_cleared():
    """0 to 9 are reserved for testing, so a card is issued into 10 to 199. A
    stray card in a reserved slot still has to come out."""
    assert _raises(SlotOutOfRange, wire.write_slot_path,
                   SlotEntry(9, "ABCD", 1), PASSWORD)
    assert wire.clear_slot_path(9, PASSWORD) == "?r009&e=1234"


def test_the_ceiling_that_is_enforced_is_the_one_the_hardware_has():
    """`slot_range` derives from `firmware.py`, so reflashing the controller
    moves the refusal and the reported capability together instead of leaving
    two numbers that agree by coincidence."""
    assert slot_range.LAST_ADDRESSABLE + 1 == firmware.NUMUSERS


def test_a_write_reports_the_value_the_controller_now_holds():
    body = ("authok\r\n<pre>\r\nprev:\r\n10\t1\t0\r\ncur:\r\n10\t1\tABCD\r\n"
            "</pre>\r\n")
    assert wire.parse_slot_dump(body) == SlotEntry(10, "ABCD", 1)


def test_a_cleared_slot_reports_no_card():
    """`?r` never closes its `<pre>` tag, so the parser cannot rely on it."""
    body = ("authok\r\nr\r\n<pre>\r\nprev:\r\n10\t1\tABCD\r\ncur:\r\n"
            "10\t255\tFFFFFFFF\r\n")
    assert wire.parse_slot_dump(body) is None


def _run() -> int:
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in fns:
        try:
            fn()
        except AssertionError as exc:
            failed.append((name, exc))
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - len(failed)}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
