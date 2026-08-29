"""The Open_Access_Control_Ethernet wire protocol, as a codec with no I/O.

Everything hardware specific is in this file and its two neighbours, and
nowhere else in the repository: the query string format, the zero padding to 3
and 8 characters, the trailing logout parameter, the 97 byte request window,
the answer that is always HTTP 200 with errors as strings in the body, and the
slot range.

There is exactly one implementation of this protocol. The fake controller is a
simulation of the device that this codec talks to, so the fake and the real
adapter cannot disagree about the bytes. Reasoning in `../fake/__init__.py`.

Facts here were read from `Open_Access_Control_Ethernet.ino` at the org fork
HEAD 60e499c. Line numbers name that file.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from ...domain.slots import TAG_DELETED, SlotEntry
from ...domain.status import DoorAction
from ..base import ControllerRefused

from .firmware import REQUEST_VISIBLE_BYTES
from .slot_range import check_addressable, check_assignable

_HEADER_END = b"\r\n\r\n"
_TABLE_MARKER = "UserNum"
_DUMP_LINE = re.compile(r"\A(\d{1,3})\t(\d{1,3})\t([0-9A-Fa-f]{1,8})\Z")
_DOOR_LOCK_KEY = re.compile(r"\Adoor_(\d+)_locked\Z")

# Every one of these is answered with HTTP 200, so a client that reads the
# status line reads a refusal as a success. The legacy app did.
_REFUSALS = (
    ("authfail", "The controller refused the password"),
    ("Not logged in.", "The controller was not privileged for this command"),
    ("err:query", "The controller could not parse the request"),
    ("err:door#", "The controller does not have that door"),
    ("Bad user number!", "The controller refused that slot number"),
)

_ADVICE = (" Nothing was changed at the door and cards still work. Check the "
           "door service log for the command it sent.")

# What the firmware prints when a door action ran. `?l=` prints no sentence at
# all, only the status payload, so a lock is confirmed from the flag instead.
_DOOR_ACTION_ANSWER = {
    DoorAction.OPEN: "Opened {:d}.",
    DoorAction.UNLOCK: "Unlocked {:d}.",
}


@dataclass(frozen=True)
class ControllerStatus:
    """The status payload, still in the controller's own numbering."""

    locked: Mapping[int, bool]
    alarm_armed: int
    alarm_activated: int
    zone_tripped: Mapping[int, bool]


# ------------------------------------------------------------------ requests

def build_http_request(path: str) -> bytes:
    """The bytes a socket puts on the wire for one query string.

    HTTP/1.0 and no Host header, because every byte counts against the window
    and the firmware never looks past the request line.
    """
    request = "GET /" + path + " HTTP/1.0\r\n\r\n"
    if len(request.encode("ascii")) > REQUEST_VISIBLE_BYTES:
        raise ValueError(
            f"This request is {len(request)} bytes and the controller sees "
            f"only the first {REQUEST_VISIBLE_BYTES}. It was not sent, because "
            "a truncated request is misparsed rather than refused.")
    return request.encode("ascii")


def status_path() -> str:
    """Status is the only command the firmware serves without a login, lines
    605 to 618. Sending the password with it would set the global privilege bit
    for a read that does not need it."""
    return "?9"


def read_table_path(password: str) -> str:
    return "?a" + _logout(password)


def read_slot_path(slot: int, password: str) -> str:
    return "?s{:03d}".format(check_addressable(slot)) + _logout(password)


def write_slot_path(entry: SlotEntry, password: str) -> str:
    """The only length validation the firmware does is that the offset from
    `?m` to `&t` is exactly 10, so the zero padding is load bearing."""
    check_assignable(entry.slot)
    return "?m{:03d}&p{:03d}&t{}".format(
        entry.slot, entry.mask, entry.tag.zfill(8)) + _logout(password)


def clear_slot_path(slot: int, password: str) -> str:
    """Addressable rather than assignable, so a stray card in a slot the lab
    reserves can still be taken out."""
    return "?r{:03d}".format(check_addressable(slot)) + _logout(password)


def door_action_path(door_number: int, action: DoorAction,
                     password: str) -> str:
    if action is DoorAction.OPEN:
        command = "?o{:d}".format(door_number)
    elif action is DoorAction.UNLOCK:
        command = "?u={:d}".format(door_number)
    elif action is DoorAction.LOCK:
        command = "?l={:d}".format(door_number)
    else:
        raise ControllerRefused(
            f"This controller cannot {action.value} a door. Nothing was sent.")
    return command + _logout(password)


def _logout(password: str) -> str:
    """The trailing form logs in before the command and out after it, in one
    request, lines 616 to 618. A bare `?e=` login leaves the whole VLAN
    privileged until something logs out or the device reboots, so a crash
    between two requests would strand the door open to anyone on the segment.
    """
    return "&e=" + password


# ----------------------------------------------------------------- responses

def body_of(answer: bytes) -> str:
    """Everything after the fixed header block.

    Latin-1 rather than UTF-8: the event log can carry a NUL byte and a
    truncated tag can carry anything, and a decode error must not turn a
    readable answer into an exception.
    """
    parts = answer.split(_HEADER_END, 1)
    if len(parts) != 2:
        raise ControllerRefused(
            "The controller's answer had no header block, so the reply was "
            "cut short." + _ADVICE)
    return parts[1].decode("latin-1")


def parse_card_table(body: str) -> Tuple[SlotEntry, ...]:
    """The occupied slots, in slot order.

    A body that is not a card table raises rather than reading as an empty
    table. An empty table is the input that makes a reconciler plan to clear
    every slot on the controller.
    """
    _refuse_on_error(body)
    if _TABLE_MARKER not in body:
        raise ControllerRefused(
            "The controller answered something that is not a card table, so "
            "the table was not read and nothing was changed. The answer "
            f"started {body[:40]!r}.")
    return tuple(entry for entry in
                 (_entry_from(line) for line in body.split("\r\n"))
                 if entry is not None)


def parse_slot_dump(body: str) -> Optional[SlotEntry]:
    """The value a slot holds after a write or a clear, or None if it holds no
    card. The section after `cur:` is what the controller currently has."""
    _refuse_on_error(body)
    tail = body.rsplit("cur:", 1)[-1]
    for line in tail.split("\r\n"):
        if _DUMP_LINE.match(line.strip()):
            return _entry_from(line)
    raise ControllerRefused(
        "The controller answered a slot command with no slot in it, so what "
        "the slot now holds is unknown." + _ADVICE)


def parse_status(body: str) -> ControllerStatus:
    _refuse_on_error(body)
    opened, closed = body.find("{"), body.rfind("}")
    if opened < 0 or closed < opened:
        raise ControllerRefused(
            "The controller answered the status command without a status in "
            f"it. The answer started {body[:40]!r}.")
    try:
        payload = json.loads(body[opened:closed + 1])
    except ValueError as exc:
        raise ControllerRefused(
            f"The controller's status did not parse: {exc}.") from exc
    return ControllerStatus(
        locked={int(m.group(1)): bool(payload[key])
                for key, m in ((k, _DOOR_LOCK_KEY.match(k)) for k in payload)
                if m},
        alarm_armed=int(payload.get("armed", 255)),
        alarm_activated=int(payload.get("activated", 255)),
        zone_tripped={zone: bool(payload["alarm_%d" % zone])
                      for zone in (2, 3) if ("alarm_%d" % zone) in payload},
    )


def parse_door_action(body: str, door_number: int,
                      action: DoorAction) -> None:
    """Whether the door actually moved.

    The status line is always 200, so the body is the only evidence there is.
    Without this, an unlock the controller refused for a stale password or for
    its own login lockout returns quietly and the member at the door is told it
    opened.
    """
    _refuse_on_error(body)
    if action is DoorAction.LOCK:
        _refuse_unless_locked(body, door_number)
        return
    said = _DOOR_ACTION_ANSWER[action].format(door_number)
    if said not in body:
        raise ControllerRefused(
            f"The controller did not confirm {action.value} on door "
            f"{door_number}. It answered {body[:60]!r} rather than {said!r}, so "
            "the door did not move." + _ADVICE)


def _refuse_unless_locked(body: str, door_number: int) -> None:
    if parse_status(body).locked.get(door_number) is not True:
        raise ControllerRefused(
            f"The controller was asked to lock door {door_number} and then "
            "reported that door still unlocked, so it is still open." + _ADVICE)


def _entry_from(line: str) -> Optional[SlotEntry]:
    """One line of a slot dump, or None if the slot holds no card.

    A deleted slot reads FFFFFFFF and one that was never written reads 0.
    checkUser skips both.
    """
    match = _DUMP_LINE.match(line.strip())
    if match is None:
        return None
    tag = match.group(3).upper()
    if tag.lstrip("0") in ("", TAG_DELETED):
        return None
    return SlotEntry(slot=int(match.group(1)), tag=tag, mask=int(match.group(2)))


def _refuse_on_error(body: str) -> None:
    for marker, what_happened in _REFUSALS:
        if marker in body:
            raise ControllerRefused(what_happened + "." + _ADVICE)
