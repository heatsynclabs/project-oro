#!/usr/bin/env python3
"""What every conformance check is handed, and the small tools they share.

The checks themselves are in `checks_device.py` and `checks_card_table.py`.
`checks()` collects them, and `test_conformance_fake.py` binds them to the
fake. Phase 5 binds the same list to `oac_ethernet` against the hardware, and a
check that only the fake can pass is a check that proved nothing.

Every check exists because of a failure that was read in the firmware or seen
in the legacy system, not because it seemed like good practice.

A fixture supplies the controller under test plus eight things the port itself
cannot show:

    controller                       the adapter, satisfying DoorController
    password                         the controller password this fixture uses
    privilege_bit_set()              is the device privileged right now
    requests()                       the raw request lines sent so far
    force_privileged()               leave the device privileged, as a crash would
    drop_next_response()             send the next request, lose the answer
    max_concurrent_requests()        the most requests in flight at once
    controller_with_a_stale_password()  the same door, a password it will refuse
    sabotage_writes()                accept a write and do not apply it, or None

All of them are answerable against real hardware. A stale password is one line
of configuration and it is what a controller reflashed without the service
being told leaves behind. `sabotage_writes` is the one an installation may
decline, and a declined check is reported as skipped by name rather than
passing quietly.
"""
from __future__ import annotations

from door.domain.status import DoorAction


class Skipped(Exception):
    """A check this installation declined, reported by name rather than
    counted as a pass."""


class WriteCounter:
    """Counts what the reconciler asked the controller to change.

    Counting at the port rather than inside the fake is what lets the same
    check run against hardware.
    """

    def __init__(self, controller):
        self._controller = controller
        self.writes = 0

    def __getattr__(self, name):
        return getattr(self._controller, name)

    def write_slot(self, slot, tag, mask):
        self.writes += 1
        self._controller.write_slot(slot, tag, mask)

    def clear_slot(self, slot):
        self.writes += 1
        self._controller.clear_slot(slot)


def apply_plan(controller, plan) -> None:
    """Carry out a diff. The reconcile loop, its shrink guard, and its snapshot
    are phase 5. This is the smallest thing that lets the suite prove a second
    pass writes nothing."""
    for change in plan:
        entry = getattr(change, "entry", None)
        if entry is None:
            controller.clear_slot(change.slot)
        else:
            controller.write_slot(entry.slot, entry.tag, entry.mask)


def refuses(exc, fn, *args):
    """True when the call was refused with that error and nothing else."""
    try:
        fn(*args)
    except exc:
        return True
    return False


def every_operation():
    """One call of each kind the port offers."""
    return (
        lambda c: c.status(),
        lambda c: c.read_card_table(),
        lambda c: c.write_slot(10, "ABCD", 1),
        lambda c: c.clear_slot(10),
        lambda c: c.perform("front", DoorAction.OPEN),
    )


def checks():
    """Every check in the suite, named for the report."""
    import checks_card_table
    import checks_device

    found = []
    for module in (checks_device, checks_card_table):
        found.extend((name[len("check_"):], fn)
                     for name, fn in sorted(vars(module).items())
                     if name.startswith("check_") and callable(fn))
    return found
