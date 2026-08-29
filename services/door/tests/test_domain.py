#!/usr/bin/env python3
"""Behaviour of the pure domain layer: slots, tag numbers, and the diff.

Nothing here touches a socket or a controller. Run it with:

    python3 services/door/tests/test_domain.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from door.domain.reconcile import SlotClear, SlotWrite, plan_changes  # noqa: E402
from door.domain.slots import (  # noqa: E402
    InvalidTagNumber,
    SlotEntry,
    SlotOutOfRange,
    normalise_tag,
)


def _raises(exc, fn, *args):
    try:
        fn(*args)
    except exc:
        return True
    return False


# ------------------------------------------------------------- tag numbers

def test_a_tag_number_is_stored_uppercase():
    """Mixed case defeats the diff, so every slot gets rewritten on every pass
    while the run reports success, and the EEPROM wears out."""
    assert SlotEntry(slot=10, tag="abcd", mask=1).tag == "ABCD"


def test_a_tag_number_loses_its_leading_zeros():
    """The controller prints tags with no leading zeros. The legacy database
    allows them, so both sides have to agree or the diff never converges."""
    assert normalise_tag("0000ABCD") == "ABCD"


def test_the_same_card_written_two_ways_compares_equal():
    assert SlotEntry(10, "0000abcd", 1) == SlotEntry(10, "ABCD", 1)


def test_a_tag_number_that_is_not_hex_is_refused():
    assert _raises(InvalidTagNumber, normalise_tag, "GHIJ")


def test_a_tag_number_longer_than_eight_characters_is_refused():
    """The controller reads only the first 8 characters and does not report an
    error. It writes a different tag than the one that was asked for."""
    assert _raises(InvalidTagNumber, normalise_tag, "0123456789")


def test_the_deleted_marker_is_not_a_tag_number():
    assert _raises(InvalidTagNumber, normalise_tag, "FFFFFFFF")


def test_the_never_written_marker_is_not_a_tag_number():
    assert _raises(InvalidTagNumber, normalise_tag, "0")


# ------------------------------------------------------------------- slots

def test_the_domain_holds_no_hardware_ceiling():
    """How many slots a controller has is EEPROM geometry, so it lives in the
    adapter that knows the hardware and is reported through `capabilities()`.
    A domain that hardcoded 199 would be a second place believing it was
    authoritative, and replacing the controller would mean changing it.

    Slot 200 on the current Arduino is refused in `test_wire.py` and again in
    the conformance suite, which asks the adapter for its own ceiling.
    """
    assert SlotEntry(4000, "ABCD", 1).slot == 4000


def test_a_negative_slot_is_refused():
    assert _raises(SlotOutOfRange, SlotEntry, -1, "ABCD", 1)


def test_a_permission_mask_outside_one_byte_is_refused():
    assert _raises(ValueError, SlotEntry, 10, "ABCD", 256)


# ------------------------------------------------------------------- diff

def test_an_unchanged_table_plans_no_writes():
    table = (SlotEntry(10, "ABCD", 1), SlotEntry(11, "BEEF", 1))
    assert plan_changes(desired=table, actual=table) == ()


def test_a_table_that_differs_only_in_case_plans_no_writes():
    """This is the case that would silently rewrite all 200 slots forever."""
    desired = (SlotEntry(10, "abcd", 1),)
    actual = (SlotEntry(10, "ABCD", 1),)
    assert plan_changes(desired=desired, actual=actual) == ()


def test_a_new_card_plans_one_write():
    plan = plan_changes(desired=(SlotEntry(10, "ABCD", 1),), actual=())
    assert plan == (SlotWrite(SlotEntry(10, "ABCD", 1)),)


def test_a_changed_permission_mask_plans_one_write():
    plan = plan_changes(desired=(SlotEntry(10, "ABCD", 255),),
                        actual=(SlotEntry(10, "ABCD", 1),))
    assert plan == (SlotWrite(SlotEntry(10, "ABCD", 255)),)


def test_a_card_the_controller_holds_and_the_database_does_not_plans_a_clear():
    plan = plan_changes(desired=(), actual=(SlotEntry(10, "ABCD", 1),))
    assert plan == (SlotClear(10),)


def test_a_plan_is_ordered_by_slot():
    """A volunteer reading the log of a sync should see it count upwards."""
    desired = (SlotEntry(30, "C", 1), SlotEntry(11, "A", 1))
    plan = plan_changes(desired=desired, actual=(SlotEntry(20, "B", 1),))
    assert [change.slot for change in plan] == [11, 20, 30]


def test_a_plan_survives_the_iterators_being_generators():
    desired = (entry for entry in (SlotEntry(10, "ABCD", 1),))
    actual = (entry for entry in ())
    assert len(plan_changes(desired=desired, actual=actual)) == 1


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
