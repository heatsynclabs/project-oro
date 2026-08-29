#!/usr/bin/env python3
"""Conformance checks about the card table: which slots may hold a card, what a
tag number looks like, and the rule that a second pass writes nothing.

Firmware line numbers name `Open_Access_Control_Ethernet.ino`.
"""
from __future__ import annotations

from conformance import Skipped, WriteCounter, apply_plan, refuses
from door.adapters.base import WriteNotVerified
from door.domain.reconcile import plan_changes
from door.domain.slots import SlotEntry, SlotOutOfRange

# ------------------------------------------------------------------- the slots

def check_the_slot_past_the_end_is_refused(new):
    """On the current Arduino that is slot 200. It passes the firmware's own
    bounds check, which reads `userNum > NUMUSERS` at line 1451 rather than
    `>=`. Its offset is 24 + 200*5 = 1024, and the AVR address register is 10
    bits, so those five bytes land on the persisted alarm state. The refusal
    has to be ours.

    The number is taken from `capabilities()` rather than written here, so the
    check is asking the adapter about its own hardware. A ceiling that is
    advertised and a ceiling that is enforced must be the same number.
    """
    fixture = new()
    past_the_end = fixture.controller.capabilities().max_slots
    assert refuses(SlotOutOfRange,
                    fixture.controller.write_slot, past_the_end, "ABCD", 1)
    assert fixture.requests() == [], fixture.requests()


def check_clearing_the_slot_past_the_end_is_refused(new):
    """`deleteUser` carries the same off by one at line 1475."""
    fixture = new()
    past_the_end = fixture.controller.capabilities().max_slots
    assert refuses(SlotOutOfRange, fixture.controller.clear_slot, past_the_end)
    assert fixture.requests() == []


def check_the_last_slot_the_controller_has_is_accepted(new):
    """On the current Arduino that is 199. 24 + 199*5 = 1019 and the record ends
    at 1023, the last byte of the 1024 byte EEPROM. Somebody will try to correct
    the base address to 1000. It is 24, from EEPROM_FIRSTUSER at line 130."""
    fixture = new()
    last = fixture.controller.capabilities().max_slots - 1
    fixture.controller.write_slot(last, "ABCD", 1)
    assert SlotEntry(last, "ABCD", 1) in fixture.controller.read_card_table()


def check_a_slot_the_lab_reserves_is_refused(new):
    """Slots 0 to 9 are reserved for testing, which is why the database
    constrains a card to 10 to 199."""
    fixture = new()
    assert refuses(SlotOutOfRange, fixture.controller.write_slot, 9, "ABCD", 1)


# ------------------------------------------------------------ the card table

def check_a_tag_number_comes_back_uppercase(new):
    """A tag that reads back in different case than it was written defeats the
    diff, so every slot is rewritten on every pass while the run reports
    success. The firmware calls EEPROM.write and never EEPROM.update, so that
    costs an erase cycle per byte per pass."""
    fixture = new()
    fixture.controller.write_slot(10, "abcd", 1)
    assert fixture.controller.read_card_table()[0].tag == "ABCD"


def check_a_write_that_did_not_take_is_reported_as_a_failure(new):
    """The firmware prints `cur:` before it knows whether `addUser` succeeded,
    so the legacy app's success test never detected a rejected write. A write
    is only believed after reading the slot back."""
    fixture = new()
    if fixture.sabotage_writes is None:
        raise Skipped("this installation cannot induce a silent rejection")
    with fixture.sabotage_writes():
        assert refuses(WriteNotVerified,
                        fixture.controller.write_slot, 10, "ABCD", 1)


def check_clearing_a_slot_removes_the_card(new):
    fixture = new()
    fixture.controller.write_slot(10, "ABCD", 1)
    fixture.controller.clear_slot(10)
    assert fixture.controller.read_card_table() == ()


def check_a_read_after_a_write_returns_what_was_written(new):
    fixture = new()
    fixture.controller.write_slot(10, "ABCD", 1)
    fixture.controller.write_slot(11, "1A2B3C4D", 255)
    assert fixture.controller.read_card_table() == (
        SlotEntry(10, "ABCD", 1), SlotEntry(11, "1A2B3C4D", 255))


def check_a_second_pass_writes_nothing(new):
    """Idempotence, and it is a hardware requirement. A blind rewrite every
    fifteen minutes is 35,040 erase cycles a year against a rated 100,000, so
    the card table wears out in under three years and presents as cards that
    intermittently stop working."""
    fixture = new()
    counted = WriteCounter(fixture.controller)
    desired = (SlotEntry(10, "ABCD", 1), SlotEntry(11, "BEEF", 1))

    apply_plan(counted, plan_changes(desired, counted.read_card_table()))
    first_pass = counted.writes
    apply_plan(counted, plan_changes(desired, counted.read_card_table()))

    assert first_pass == 2, first_pass
    assert counted.writes == first_pass, counted.writes


def check_reading_twice_and_writing_nothing_changes_nothing(new):
    fixture = new()
    fixture.controller.write_slot(10, "ABCD", 1)
    before = fixture.controller.read_card_table()
    assert fixture.controller.read_card_table() == before
