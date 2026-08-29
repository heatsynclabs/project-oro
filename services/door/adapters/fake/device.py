"""A simulation of the controller, not a second implementation of the client.

This models the device: 1024 bytes of EEPROM, one global privilege bit, two
door lock flags, and the exact strings the firmware prints. The real codec in
`oac_ethernet` then talks to it over the same request bytes it would put on a
socket.

It models the firmware's defects on purpose, because they are the reason the
client is shaped the way it is. It accepts slot 200 and corrupts its own alarm
bytes. It prints a current value line for a write it rejected. It leaves the
privilege bit set after a bare login. A fake that had been cleaned up would let
the client stop defending against any of that and still show green.

Every number comes from `../oac_ethernet/firmware.py`, so the fake and the real
adapter read the same file for them.
"""
from __future__ import annotations

import time
from typing import Dict

from ..oac_ethernet.firmware import (
    DOOR_NUMBERS,
    EEPROM_ADDRESS_MASK,
    EEPROM_ALARM,
    EEPROM_ALARM_ARMED,
    EEPROM_ERASED_BYTE,
    EEPROM_FIRSTUSER,
    EEPROM_SIZE,
    FIXED_RESPONSE_HEADER,
    LOGIN_FAILURES_BEFORE_LOCKOUT,
    LOGIN_LOCKOUT_SECONDS,
    NUMUSERS,
    PASSWORD_HEX_DIGITS,
    REQUEST_VISIBLE_BYTES,
    SLOT_RECORD_BYTES,
)

_NOT_LOGGED_IN = "<a href='/'>Not logged in.</a>"
_HELP = "<h2>Open Access Control</h2><hr/>See help[] source"
_TABLE_HEADING = "<pre>\r\nUserNum: Usermask: TagNum:\r\n"

# armAlarm(4) is door chime mode. Pulsing a door drops the alarm into it, which
# is a real side effect of `?o` and worth having the fake reproduce.
_ALARM_CHIME = 4


class FakeController:
    """One Arduino, in memory."""

    def __init__(self, password: str, clock=time.monotonic) -> None:
        if len(password) != PASSWORD_HEX_DIGITS:
            raise ValueError("The firmware reads exactly "
                             f"{PASSWORD_HEX_DIGITS} password characters.")
        self.password = password
        # Injected so a test can reach the far side of the five minute lockout
        # window without waiting five minutes.
        self._clock = clock
        self.failed_logins = 0
        self._lockout_armed_at = 0.0
        self.eeprom = bytearray([EEPROM_ERASED_BYTE] * EEPROM_SIZE)
        self.privileged = False
        # Not persisted, and true at boot: the strikes are energised to unlock,
        # so a power cut locks the building.
        self.door_locked = {number: True for number in DOOR_NUMBERS}
        self.eeprom_writes = 0
        self.reject_writes_silently = False

    # ------------------------------------------------------------ the wire

    def handle(self, request: bytes) -> bytes:
        visible = request.decode("latin-1")[:REQUEST_VISIBLE_BYTES]
        return FIXED_RESPONSE_HEADER + self._body(visible).encode("latin-1")

    def _body(self, visible: str) -> str:
        chained = "&e=" in visible
        if chained and not self._login(visible.split("&e=", 1)[1]):
            return "authfail\r\n"
        try:
            return ("authok\r\n" if chained else "") + self._dispatch(visible)
        finally:
            if chained:
                self.privileged = False

    def _dispatch(self, visible: str) -> str:
        if "?" not in visible:
            return _HELP
        command = visible[visible.index("?") + 1]
        if command == "9":
            return self._status()
        if command == "e":
            return self._bare_login(visible)
        if not self.privileged:
            return _NOT_LOGGED_IN
        handler = self._privileged_commands().get(command)
        return handler(visible) if handler else ""

    def _privileged_commands(self) -> Dict[str, object]:
        return {"a": self._table, "s": self._show_slot, "m": self._write_slot,
                "r": self._remove_slot, "o": self._open, "u": self._unlock,
                "l": self._lock}

    # ------------------------------------------------------- the priv bit

    def _login(self, supplied: str) -> bool:
        if self._locked_out():
            self.privileged = False
            return False
        self.privileged = supplied[:PASSWORD_HEX_DIGITS] == self.password
        if self.privileged:
            self.failed_logins = 0
        else:
            self._count_a_failure()
        return self.privileged

    def _locked_out(self) -> bool:
        """A correct password inside the window is refused too, because this is
        checked before the password is."""
        if self.failed_logins < LOGIN_FAILURES_BEFORE_LOCKOUT:
            return False
        return self._clock() - self._lockout_armed_at < LOGIN_LOCKOUT_SECONDS

    def _count_a_failure(self) -> None:
        """`consolefailTimer` is set only while the failure count is zero, which
        is why the lockout can never arm a second time."""
        if self.failed_logins == 0:
            self._lockout_armed_at = self._clock()
        self.failed_logins += 1

    def _bare_login(self, visible: str) -> str:
        """`?e=` on its own. It logs in and never logs out, so the bit stays set
        for everything on the VLAN until a reboot. The door service never sends
        this form, and the fake keeps it so that stays testable."""
        supplied = visible.split("?e=", 1)[1][:PASSWORD_HEX_DIGITS]
        return "authok\r\n" if self._login(supplied) else "authfail\r\n"

    # ---------------------------------------------------------- the EEPROM

    def _address(self, slot: int) -> int:
        return (EEPROM_FIRSTUSER + slot * SLOT_RECORD_BYTES) & EEPROM_ADDRESS_MASK

    def _read_byte(self, at: int) -> int:
        return self.eeprom[at & EEPROM_ADDRESS_MASK]

    def _write_byte(self, at: int, value: int) -> None:
        """EEPROM.write, never EEPROM.update. An unchanged byte still costs an
        erase cycle, and that is what makes a blind rewrite destructive."""
        self.eeprom[at & EEPROM_ADDRESS_MASK] = value
        self.eeprom_writes += 1

    def _dump(self, slot: int) -> str:
        at = self._address(slot)
        tag = sum(self._read_byte(at + i) << (8 * i) for i in range(4))
        return "{:d}\t{:d}\t{:X}\r\n".format(slot, self._read_byte(at + 4), tag)

    def _store(self, slot: int, tag: int, mask: int) -> None:
        at = self._address(slot)
        for i in range(4):
            self._write_byte(at + i, (tag >> (8 * i)) & 0xFF)
        self._write_byte(at + 4, mask & 0xFF)

    # ------------------------------------------------------ the card table

    def _table(self, visible: str) -> str:
        return (_TABLE_HEADING
                + "".join(self._dump(slot) for slot in range(NUMUSERS))
                + "</pre>\r\n")

    def _show_slot(self, visible: str) -> str:
        at = visible.index("?s")
        # atoi's result is assigned to a byte, so ?s256 shows slot 0.
        slot = int(visible[at + 2:at + 5]) & 0xFF
        if slot >= NUMUSERS:
            return "Bad user number!\r\n"
        return _TABLE_HEADING + self._dump(slot) + "</pre>\r\n"

    def _write_slot(self, visible: str) -> str:
        at, tag_at = visible.index("?m"), visible.find("&t")
        if tag_at - at != 10:
            return "err:query\r\n"
        slot = int(visible[at + 2:at + 5])
        previous = self._dump(slot)
        # addUser's bounds check is `userNum > NUMUSERS`, so 200 gets through.
        if 0 <= slot <= NUMUSERS and not self.reject_writes_silently:
            self._store(slot, int(visible[tag_at + 2:tag_at + 10], 16),
                        int(visible[at + 7:at + 10]))
        # Printed whether or not the write happened, which is why the client
        # reads the slot back rather than believing this.
        return ("<pre>\r\nprev:\r\n" + previous
                + "cur:\r\n" + self._dump(slot) + "</pre>\r\n")

    def _remove_slot(self, visible: str) -> str:
        at = visible.index("?r")
        slot = int(visible[at + 2:at + 5])
        previous = self._dump(slot)
        if 0 <= slot <= NUMUSERS and not self.reject_writes_silently:
            self._store(slot, 0xFFFFFFFF, EEPROM_ERASED_BYTE)
        # `</pre>` is never closed on this path.
        return ("r\r\n<pre>\r\nprev:\r\n" + previous
                + "cur:\r\n" + self._dump(slot))

    # ---------------------------------------------------------- the doors

    def _open(self, visible: str) -> str:
        """A pulse. The strike releases and the relock timer puts it back, so
        the lock flag never changes. It also disarms the alarm and drops it
        into chime mode, which is why this is not a harmless read."""
        number = self._door_number(visible, visible.index("?o") + 2)
        if number is None:
            return "err:door#\r\n"
        self._write_byte(EEPROM_ALARM, 0)
        self._write_byte(EEPROM_ALARM_ARMED, _ALARM_CHIME)
        return "Opened {:d}.".format(number)

    def _unlock(self, visible: str) -> str:
        if "?u=" not in visible:
            self._set_all(False)
            return "Unlocked all." + self._status()
        number = self._door_number(visible, visible.index("?u=") + 3)
        if number is None:
            return "err:door#\r\n" + self._status()
        self.door_locked[number] = False
        return "Unlocked {:d}.".format(number) + self._status()

    def _lock(self, visible: str) -> str:
        """There is no err:door# on this path. `?l=3` silently locks
        everything, so an unknown door has to be refused by the client."""
        if "?l=" in visible:
            number = self._door_number(visible, visible.index("?l=") + 3)
            if number is not None:
                self.door_locked[number] = True
                return self._status()
        self._set_all(True)
        return "Locked all." + self._status()

    def _set_all(self, locked: bool) -> None:
        for number in self.door_locked:
            self.door_locked[number] = locked

    def _door_number(self, visible: str, at: int):
        digit = visible[at:at + 1]
        number = int(digit) if digit.isdigit() else None
        return number if number in DOOR_NUMBERS else None

    # ---------------------------------------------------------- the status

    def _status(self, visible: str = "") -> str:
        """printStatus mixes print and println, so the payload carries line
        breaks inside it. It is valid JSON and it is not pretty."""
        doors = "".join(',"door_{:d}_locked":{:d}\r\n'.format(
            number, int(self.door_locked[number])) for number in DOOR_NUMBERS)
        return ('{{\r\n"armed":{:d},"activated":{:d}\r\n'
                # Zones 2 and 3 are the door position sensors. This fake has no
                # sensors wired, so it reports them quiet.
                ',"alarm_3":0\r\n,"alarm_2":0\r\n{}}}\r\n').format(
                    self.eeprom[EEPROM_ALARM_ARMED],
                    self.eeprom[EEPROM_ALARM], doors)
