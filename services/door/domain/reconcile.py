"""The diff between the card table the lab wants and the one the door holds.

Pure, and deliberately only the diff. The loop around it, its timer, the shrink
guard, the SQLite snapshot, and the buffered event log are phase 5 work and are
not here. What is here is the part the conformance suite needs in order to
prove a second pass writes nothing.

Why a diff rather than a rewrite: the firmware calls EEPROM.write and never
EEPROM.update, so writing a byte that already holds the right value still costs
an erase cycle. Rewriting all 200 slots every fifteen minutes is 35,040 cycles
a year against a rated endurance of 100,000, which wears the card table out in
under three years. It fails as cells that no longer hold a value, and that
presents as cards which intermittently stop working.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple, Union

from .slots import SlotEntry


@dataclass(frozen=True)
class SlotWrite:
    """Put this card in this slot."""

    entry: SlotEntry

    @property
    def slot(self) -> int:
        return self.entry.slot


@dataclass(frozen=True)
class SlotClear:
    """Take whatever card is in this slot out of it."""

    slot: int


SlotChange = Union[SlotWrite, SlotClear]


def plan_changes(desired: Iterable[SlotEntry],
                 actual: Iterable[SlotEntry]) -> Tuple[SlotChange, ...]:
    """What has to change for the controller to hold the desired table.

    Ordered by slot so a volunteer reading the log of a sync sees it count
    upwards, and so two runs against the same inputs produce the same log.
    """
    want = {entry.slot: entry for entry in desired}
    have = {entry.slot: entry for entry in actual}

    changes = []
    for slot in sorted(set(want) | set(have)):
        wanted = want.get(slot)
        held = have.get(slot)
        if wanted == held:
            continue
        changes.append(SlotClear(slot) if wanted is None else SlotWrite(wanted))
    return tuple(changes)
