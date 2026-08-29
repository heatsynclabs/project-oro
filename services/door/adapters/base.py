"""The port every door controller must satisfy.

Defined by what a door controller must do, not by what this Arduino happens to
do. The adapter declares its own limits through `capabilities()` rather than
the layers above hardcoding them, so replacing the controller is one component
and not a project.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from ..domain.slots import SlotEntry
from ..domain.status import DoorAction, DoorStatus


@dataclass(frozen=True)
class ControllerCapabilities:
    """What the hardware underneath can do, in its own words."""

    max_slots: int
    supports_bulk_write: bool

    # False here is the current Arduino admitting that its privilege bit is one
    # global boolean for the whole device rather than a session. That is what
    # makes the serialising lock an adapter problem rather than one the API and
    # the domain have to know about. A replacement sets it true and the lock
    # stops being necessary, with nothing above the adapter changing.
    supports_per_session_auth: bool

    supports_event_stream: bool


class ControllerError(Exception):
    """Anything that stopped a controller operation from completing."""


class ControllerUnreachable(ControllerError):
    """The controller did not answer. Nothing was sent, or the answer was lost.

    Cards still open the door: the controller matches them against its own
    EEPROM with no network involved.
    """


class ControllerRefused(ControllerError):
    """The controller answered, and the answer says the command did not run.

    Every answer is HTTP 200 with the error as a string in the body, so a
    client that trusts the status line reads a refusal as success.
    """


class WriteNotVerified(ControllerError):
    """The write was accepted and the slot does not hold the value.

    The firmware prints its current value line before it knows whether the
    write succeeded, so a write is only believed after the slot is read back.
    """


@runtime_checkable
class DoorController(Protocol):
    """One door installation, as everything above the adapter sees it."""

    def capabilities(self) -> ControllerCapabilities: ...

    def status(self) -> DoorStatus: ...

    def read_card_table(self) -> Sequence[SlotEntry]: ...

    def write_slot(self, slot: int, tag: str, mask: int) -> None: ...

    def clear_slot(self, slot: int) -> None: ...

    def perform(self, door: str, action: DoorAction) -> None: ...
