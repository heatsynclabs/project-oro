"""Which slots this controller can hold a card in.

The range is EEPROM geometry, so it belongs to this adapter rather than to the
domain. A replacement controller has a different one, and the layers above ask
`capabilities()` instead of holding a number of their own.

Both ends derive from `firmware.py`, so reflashing the controller moves the
refusal and the reported capability together. Two constants that happen to
agree are two places that each believe they are authoritative.
"""
from __future__ import annotations

from ...domain.slots import SlotOutOfRange
from .firmware import NUMUSERS

# Slots are numbered from 0, so the last one whose 5 byte record fits inside the
# EEPROM is NUMUSERS - 1, which is 199. Its record runs from 24 + 199*5 = 1019
# to 1023, the last byte there is. Slot 200 passes the firmware's own bounds
# check at line 1451, which reads `userNum > NUMUSERS` rather than `>=`, and its
# five bytes wrap onto the persisted alarm state. The refusal has to be ours.
# `deleteUser` carries the same off by one at line 1475.
FIRST_ADDRESSABLE = 0
LAST_ADDRESSABLE = NUMUSERS - 1

# The lab reserves 0 to 9 for testing, so a card is issued into 10 to 199. The
# same range is a CHECK constraint on cards.controller_slot in
# db/migrations/002_access.sql.
FIRST_ASSIGNABLE = 10
LAST_ASSIGNABLE = LAST_ADDRESSABLE


def check_addressable(slot: int) -> int:
    """A slot this controller can address at all. Clearing uses this range, so
    a stray card in a reserved slot can still be taken out."""
    return _check(slot, FIRST_ADDRESSABLE, LAST_ADDRESSABLE)


def check_assignable(slot: int) -> int:
    """A slot a card may be issued into."""
    return _check(slot, FIRST_ASSIGNABLE, LAST_ASSIGNABLE)


def _check(slot: int, first: int, last: int) -> int:
    if first <= slot <= last:
        return slot
    raise SlotOutOfRange(
        f"Slot {slot} is outside {first} to {last} on this controller, so "
        "nothing was sent and no card changed. Slot 200 in particular passes "
        "the firmware's own bounds check and writes onto the alarm state "
        "bytes. Pick a slot in range, or free one.")
