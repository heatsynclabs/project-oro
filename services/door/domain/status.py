"""What a door can be asked to do, and what a controller says about itself.

Pure. Door names here are the lab's names, `front` and `rear`. Which physical
door is controller door 1 is configuration, held in the adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class DoorAction(Enum):
    """The actions the current hardware offers. A replacement controller offers
    a different set and reports it through the capabilities."""

    OPEN = "open"      # Energise the strike, then relock on a timer
    UNLOCK = "unlock"  # Energise the strike and hold it
    LOCK = "lock"


@dataclass(frozen=True)
class DoorStatus:
    """Lock and alarm state as the controller reports it.

    There is no timestamp here on purpose. Time comes from the caller, so this
    stays a reading rather than a claim about when the reading was taken.
    """

    locked: Mapping[str, bool]

    # alarmArmed: 0 disarmed, 1 armed, 4 door chime only. 255 means the EEPROM
    # byte holding it was never written.
    alarm_armed: int

    # alarmActivated: 0 off, 1 siren, 2 strobe with the delay running, 3
    # latched silent. Also 255 for a byte that was never written.
    alarm_activated: int
    alarm_zone_tripped: Mapping[int, bool] = field(default_factory=dict)

    @property
    def any_door_unlocked(self) -> bool:
        """What the public open sign is built from."""
        return not all(self.locked.values())
