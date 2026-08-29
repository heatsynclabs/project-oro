"""The adapter for the Arduino running Open_Access_Control_Ethernet.

One lock, because the controller's privilege bit is one global boolean for the
whole device. Two operations in flight at once is a correctness bug rather than
a slow path: whichever one logs out first leaves the other running unprivileged
and its command is refused, and in between anything else on the VLAN is
privileged.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Mapping, Tuple

from ...domain.slots import SlotEntry
from ...domain.status import DoorAction, DoorStatus
from ..base import ControllerCapabilities, ControllerRefused, WriteNotVerified
from . import wire
from .firmware import DOOR_NUMBERS, PASSWORD_HEX_DIGITS
from .slot_range import LAST_ADDRESSABLE


@dataclass(frozen=True)
class OacEthernetConfig:
    """What this installation is wired as.

    ASSUMPTION: front is controller door 1 and rear is controller door 2.
    CONFIRM BY: at the lab, `?u=1` and watch which strike releases. The
                firmware names the pins DOORPIN1 and DOORPIN2 and never says
                which is which, and no document in this repository settles it.
    BLAST RADIUS: a member pressing unlock on the front door unlocks the rear
                one instead. Which is why this is configuration rather than a
                constant, and why the door app shows what it asked for.
    """

    password: str
    doors: Mapping[str, int]

    def __post_init__(self) -> None:
        if len(self.password) != PASSWORD_HEX_DIGITS:
            raise ValueError(
                f"The controller password is exactly {PASSWORD_HEX_DIGITS} hex "
                "characters, because the firmware reads that many and passes "
                "them to strtoul. A shorter one makes it read whatever bytes "
                "follow in the request.")
        int(self.password, 16)
        unknown = [door for door, number in self.doors.items()
                   if number not in DOOR_NUMBERS]
        if unknown:
            raise ValueError(
                f"This controller drives doors {DOOR_NUMBERS}, and the "
                f"configuration names {unknown}. Nothing was started.")


class OacEthernetController:
    """Satisfies the DoorController port for the current hardware."""

    def __init__(self, transport, config: OacEthernetConfig) -> None:
        self._transport = transport
        self._config = config
        self._lock = threading.Lock()

    def capabilities(self) -> ControllerCapabilities:
        return ControllerCapabilities(
            # The ceiling this adapter enforces, reported rather than restated,
            # so nothing above it has to hold a number of its own.
            max_slots=LAST_ADDRESSABLE + 1,
            supports_bulk_write=False,
            supports_per_session_auth=False,
            supports_event_stream=False,
        )

    def status(self) -> DoorStatus:
        reading = wire.parse_status(self._ask(wire.status_path()))
        return DoorStatus(
            locked={door: reading.locked[number]
                    for door, number in self._config.doors.items()
                    if number in reading.locked},
            alarm_armed=reading.alarm_armed,
            alarm_activated=reading.alarm_activated,
            alarm_zone_tripped=reading.zone_tripped,
        )

    def read_card_table(self) -> Tuple[SlotEntry, ...]:
        return wire.parse_card_table(
            self._ask(wire.read_table_path(self._config.password)))

    def write_slot(self, slot: int, tag: str, mask: int) -> None:
        wanted = SlotEntry(slot=slot, tag=tag, mask=mask)
        password = self._config.password
        with self._lock:
            self._send(wire.write_slot_path(wanted, password))
            held = wire.parse_slot_dump(
                self._send(wire.read_slot_path(wanted.slot, password)))
        if held != wanted:
            raise WriteNotVerified(
                f"Slot {wanted.slot} was written and reads back as {held}, not "
                f"{wanted}. The card was not changed at the door. The "
                "controller prints its current value before it checks whether "
                "the write succeeded, so a write is only believed after this "
                "read back.")

    def clear_slot(self, slot: int) -> None:
        password = self._config.password
        with self._lock:
            self._send(wire.clear_slot_path(slot, password))
            held = wire.parse_slot_dump(
                self._send(wire.read_slot_path(slot, password)))
        if held is not None:
            raise WriteNotVerified(
                f"Slot {slot} was cleared and still holds {held}. The card "
                "still opens the door. Try again, and if it keeps happening "
                "check the controller log for a rejected slot number.")

    def perform(self, door: str, action: DoorAction) -> None:
        number = self._config.doors.get(door)
        if number is None:
            known = ", ".join(sorted(self._config.doors)) or "none"
            raise ControllerRefused(
                f"This installation has no door called {door!r}, so nothing "
                f"was sent. The doors it has are: {known}.")
        answer = self._ask(wire.door_action_path(number, action,
                                                 self._config.password))
        wire.parse_door_action(answer, number, action)

    def _ask(self, path: str) -> str:
        with self._lock:
            return self._send(path)

    def _send(self, path: str) -> str:
        """Caller holds the lock. The trailing logout parameter is part of
        every privileged path, so one request is one complete sequence and a
        crash cannot leave the controller privileged."""
        return wire.body_of(self._transport.send(path))
