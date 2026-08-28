"""A slot in the controller's card table, and the rules a slot obeys.

Pure. Nothing here opens a socket or knows what a URL is.

A slot is an EEPROM address on the controller, not a surrogate key. That is the
fact the whole file exists to defend: renumbering a slot silently maps a member
to somebody else's door permission, and the door still opens.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 0xFFFFFFFF is a slot that was deleted and 0x00000000 is one that was never
# written. checkUser treats both as no card, so neither can be a real tag.
TAG_DELETED = "FFFFFFFF"
TAG_NEVER_WRITTEN = "0"

_HEX = re.compile(r"\A[0-9A-F]{1,8}\Z")


class SlotOutOfRange(ValueError):
    """A slot number the controller cannot safely hold a card in."""


class InvalidTagNumber(ValueError):
    """A tag number the controller would store as something else."""


def normalise_tag(tag: str) -> str:
    """The one canonical form of a tag number, used on both sides of the diff.

    Uppercase, no leading zeros. The controller prints tags that way and the
    legacy database does not, so without one form the diff differs forever:
    every slot is rewritten on every pass, the run reports success, and the
    EEPROM wears out.
    """
    trimmed = tag.strip().upper().lstrip("0") or "0"
    if not _HEX.match(trimmed):
        raise InvalidTagNumber(
            "A tag number is 1 to 8 uppercase hex characters. This one is "
            f"{tag!r}, which was not written and no card was changed. Check "
            "the tag number on the card record.")
    if trimmed in (TAG_DELETED, TAG_NEVER_WRITTEN):
        raise InvalidTagNumber(
            f"{trimmed} is how the controller marks a slot with no card in "
            "it, so it cannot be a tag number. Nothing was written.")
    return trimmed


def check_slot_number(slot: int) -> int:
    """A slot is an EEPROM address on some controller, so it is a whole number
    and it is not negative.

    How high it may go is not decided here. That is the geometry of one piece of
    hardware, it lives in the adapter that knows it, and the adapter reports it
    through `capabilities()`. For the current Arduino it is
    `adapters/oac_ethernet/slot_range.py`.
    """
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise SlotOutOfRange(f"A slot is a whole number. This one is {slot!r}.")
    if slot < 0:
        raise SlotOutOfRange(
            f"Slot {slot} is negative, so nothing was sent to any controller "
            "and no card changed.")
    return slot


@dataclass(frozen=True)
class SlotEntry:
    """One card, in one slot, with one permission mask.

    Mask 1 is full access and mask 255 is locked out. The mask is a lookup
    value rather than a bitmask, despite the name: processTagAccess switches on
    it, and 0, 10, 20 and 255 each mean something specific.
    """

    slot: int
    tag: str
    mask: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot", check_slot_number(self.slot))
        object.__setattr__(self, "tag", normalise_tag(self.tag))
        if isinstance(self.mask, bool) or not isinstance(self.mask, int):
            raise ValueError(f"A permission mask is a whole number, not {self.mask!r}.")
        if not 0 <= self.mask <= 255:
            raise ValueError(
                f"A permission mask is one byte, 0 to 255. This one is "
                f"{self.mask}, so nothing was written.")
