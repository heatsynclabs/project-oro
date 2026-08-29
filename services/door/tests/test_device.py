#!/usr/bin/env python3
"""The fake controller against the firmware it stands in for.

The conformance suite proves the adapter is correct. This file proves the fake
is worth running the suite against, by pinning the firmware behaviours that the
port hides: the 97 byte request window, the erase cycle per byte, and the write
past the end of the EEPROM. Privileged mode has its own file next to this one.

Line numbers and constant names are from `Open_Access_Control_Ethernet.ino`.

    python3 services/door/tests/test_device.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from door.adapters.fake.device import (  # noqa: E402
    EEPROM_ALARM,
    EEPROM_ALARM_ARMED,
    EEPROM_FIRSTUSER,
    EEPROM_SIZE,
    NUMUSERS,
    FakeController,
)
from door.adapters.oac_ethernet import wire  # noqa: E402

PASSWORD = "BEEF"


def _ask(device, path: str) -> str:
    return wire.body_of(device.handle(wire.build_http_request(path)))


def _ask_raw(device, request: str) -> str:
    return wire.body_of(device.handle(request.encode("ascii")))


def _new():
    return FakeController(password=PASSWORD)


# ------------------------------------------------------------------- framing

def test_the_answer_carries_the_fixed_header_and_always_says_200():
    raw = _new().handle(wire.build_http_request("?9"))
    assert raw.startswith(b"HTTP/1.1 200 OK\r\nCache-Control: no-store\r\n"
                          b"Content-Type: text/html\r\n\r\n")


def test_only_the_first_97_bytes_of_a_request_are_seen():
    """`readString` is capped at 100 and initialised as `String(100)`, which in
    Arduino constructs the text "100", so three of the hundred are spent.

    The codec refuses to build a request this long, so the bytes are assembled
    here by hand. That refusal is what stops the truncation ever happening in
    the service, and it has its own test in `test_wire.py`.
    """
    device = _new()
    seen = _ask_raw(device, "GET /?9" + "x" * 200 + " HTTP/1.0\r\n\r\n")
    cut = _ask_raw(device, "GET /?" + "x" * 95 + "9 HTTP/1.0\r\n\r\n")
    assert "armed" in seen
    assert "armed" not in cut, cut


# ------------------------------------------------------------- the card table

def test_the_table_lists_every_slot_the_hardware_has():
    body = _ask(_new(), "?a&e=" + PASSWORD)
    assert body.count("\r\n") == NUMUSERS + 4, body[:80]


def test_a_fresh_controller_holds_no_cards():
    assert wire.parse_card_table(_ask(_new(), "?a&e=" + PASSWORD)) == ()


def test_a_written_slot_reads_back():
    device = _new()
    _ask(device, "?m010&p001&t0000ABCD&e=" + PASSWORD)
    table = wire.parse_card_table(_ask(device, "?a&e=" + PASSWORD))
    assert [(e.slot, e.tag, e.mask) for e in table] == [(10, "ABCD", 1)]


def test_a_slot_holds_four_bytes_of_tag_little_endian_then_the_mask():
    device = _new()
    _ask(device, "?m010&p001&t1A2B3C4D&e=" + PASSWORD)
    at = EEPROM_FIRSTUSER + 10 * 5
    assert list(device.eeprom[at:at + 5]) == [0x4D, 0x3C, 0x2B, 0x1A, 1]


def test_removing_a_slot_sets_all_five_bytes_to_255():
    device = _new()
    _ask(device, "?m010&p001&t0000ABCD&e=" + PASSWORD)
    _ask(device, "?r010&e=" + PASSWORD)
    at = EEPROM_FIRSTUSER + 10 * 5
    assert list(device.eeprom[at:at + 5]) == [255] * 5


def test_removing_a_slot_never_closes_its_pre_tag():
    device = _new()
    assert "</pre>" not in _ask(device, "?r010&e=" + PASSWORD)


def test_a_malformed_write_answers_err_query():
    """The only length validation is that the offset from `?m` to `&t` is
    exactly 10."""
    assert "err:query" in _ask(_new(), "?m1000&p001&t0000ABCD&e=" + PASSWORD)


def test_a_rejected_write_still_answers_with_a_current_value():
    """`addUser` refuses slots above 200 and logs `i`, but `cur:` was already
    printed. This is why a write is only believed after a read back."""
    device = _new()
    body = _ask(device, "?m201&p001&t0000ABCD&e=" + PASSWORD)
    assert "cur:" in body
    assert device.eeprom_writes == 0


def test_slot_200_writes_onto_the_persisted_alarm_state():
    """The bounds check at line 1451 is `userNum > NUMUSERS`, so 200 passes it.
    24 + 200*5 = 1024, and the AVR address register is 10 bits, so the five
    bytes wrap to 0 through 4. Bytes 0 and 1 are alarmActivated and alarmArmed.

    This is the behaviour the adapter's refusal exists to prevent. If this test
    ever goes green by the fake becoming safe, the refusal stops being tested.
    """
    device = _new()
    before = (device.eeprom[EEPROM_ALARM], device.eeprom[EEPROM_ALARM_ARMED])
    _ask(device, "?m200&p001&t0000ABCD&e=" + PASSWORD)
    after = (device.eeprom[EEPROM_ALARM], device.eeprom[EEPROM_ALARM_ARMED])
    assert after != before, (before, after)


def test_slot_199_ends_exactly_at_the_last_byte_of_the_eeprom():
    """Somebody will try to correct the base address to 1000. It is 24."""
    assert EEPROM_FIRSTUSER + 199 * 5 + 5 == EEPROM_SIZE


def test_writing_an_unchanged_byte_still_costs_an_erase_cycle():
    """The firmware calls EEPROM.write and never EEPROM.update. This is the
    whole reason the reconciler diffs instead of rewriting."""
    device = _new()
    _ask(device, "?m010&p001&t0000ABCD&e=" + PASSWORD)
    first = device.eeprom_writes
    _ask(device, "?m010&p001&t0000ABCD&e=" + PASSWORD)
    assert first == 5 and device.eeprom_writes == 10, device.eeprom_writes


# ----------------------------------------------------------------- the doors

def test_both_doors_are_locked_at_boot():
    """Strikes are energised to unlock, so a power cut locks the building. The
    flags are the firmware's intent and are not persisted."""
    assert '"door_1_locked":1' in _ask(_new(), "?9")
    assert '"door_2_locked":1' in _ask(_new(), "?9")


def test_unlocking_one_door_leaves_the_other_locked():
    device = _new()
    body = _ask(device, "?u=1&e=" + PASSWORD)
    assert "Unlocked 1." in body
    assert '"door_1_locked":0' in body and '"door_2_locked":1' in body


def test_locking_an_unrecognised_door_number_locks_everything():
    """There is no `err:door#` on the lock path, so `?l=3` silently locks both.
    The adapter refuses an unknown door before the request is built."""
    device = _new()
    _ask(device, "?u&e=" + PASSWORD)
    body = _ask(device, "?l=3&e=" + PASSWORD)
    assert '"door_1_locked":1' in body and '"door_2_locked":1' in body


def test_opening_a_door_is_a_pulse_that_leaves_it_locked():
    device = _new()
    assert "Opened 1." in _ask(device, "?o1&e=" + PASSWORD)
    assert '"door_1_locked":1' in _ask(device, "?9")


def test_an_unrecognised_door_number_on_the_open_path_is_an_error():
    assert "err:door#" in _ask(_new(), "?o3&e=" + PASSWORD)


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
