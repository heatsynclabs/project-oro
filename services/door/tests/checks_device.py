#!/usr/bin/env python3
"""Conformance checks about the device itself: what it can do, its one global
privilege bit, and its doors. Run through `test_conformance_fake.py`.

Firmware line numbers name `Open_Access_Control_Ethernet.ino`.
"""
from __future__ import annotations

import threading

from conformance import every_operation, refuses
from door.adapters.base import ControllerRefused
from door.domain.status import DoorAction

# ------------------------------------------------------- what the hardware is

def check_capabilities_describe_this_hardware(new):
    """A replacement controller reports different numbers here and nothing
    above the adapter changes."""
    caps = new().controller.capabilities()
    assert caps.max_slots == 200, caps
    assert caps.supports_bulk_write is False
    assert caps.supports_per_session_auth is False
    assert caps.supports_event_stream is False


# ------------------------------------------------------------ the privilege bit

def check_status_carries_no_password(new):
    """Status is the only command the firmware serves unauthenticated (lines
    605 to 618), so polling it must never set the bit for the whole VLAN."""
    fixture = new()
    fixture.controller.status()
    assert not any(fixture.password in line for line in fixture.requests())


def check_status_leaves_the_privilege_bit_clear(new):
    fixture = new()
    fixture.controller.status()
    assert fixture.privilege_bit_set() is False


def check_every_operation_leaves_the_privilege_bit_clear(new):
    """`privmodeEnabled` is one global boolean for the device (line 230). While
    it is set, anything on the VLAN is privileged."""
    for operate in every_operation():
        fixture = new()
        operate(fixture.controller)
        assert fixture.privilege_bit_set() is False, operate


def check_a_lost_response_leaves_the_privilege_bit_clear(new):
    """The crash case. Login and logout travel in one request using the
    trailing `&e=` form, so losing the answer cannot strand the controller
    privileged."""
    fixture = new()
    fixture.drop_next_response()
    try:
        fixture.controller.read_card_table()
    except Exception:  # noqa: BLE001
        pass
    assert fixture.privilege_bit_set() is False


def check_an_operation_after_a_crash_does_not_assume_privilege(new):
    """An earlier run died holding the bit. The next operation still logs in
    for itself and still logs out, rather than riding somebody else's."""
    fixture = new()
    fixture.force_privileged()
    fixture.controller.read_card_table()
    assert fixture.privilege_bit_set() is False


def check_operations_serialise_through_one_lock(new):
    """Two operations in flight at once against a device with one global
    privilege bit is a correctness bug, not a slow path."""
    fixture = new()
    threads = [threading.Thread(target=fixture.controller.status)
               for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert fixture.max_concurrent_requests() == 1


# ------------------------------------------------------------- refused, not done

def check_a_refused_door_action_is_not_reported_as_done(new):
    """The controller answers HTTP 200 with the refusal as a string in the
    body, so an unlock that never happened is indistinguishable from one that
    did unless the body is read. A password rotated at the controller and the
    firmware's own lockout after five failed logins both arrive this way.

    Whoever is standing at the door is told what actually happened.
    """
    fixture = new()
    stale = fixture.controller_with_a_stale_password()
    assert refuses(ControllerRefused, stale.perform, "front", DoorAction.UNLOCK)
    assert fixture.controller.status().locked["front"] is True


def check_a_refused_table_read_is_not_an_empty_table(new):
    """An empty table is the input that makes a reconciler plan to clear every
    slot on the controller, which is every card in the building."""
    fixture = new()
    stale = fixture.controller_with_a_stale_password()
    assert refuses(ControllerRefused, stale.read_card_table)


def check_status_still_answers_when_the_password_is_wrong(new):
    """Status is the only unauthenticated command, so the public open sign
    keeps working through an outage of everything else, a password the service
    no longer has right included."""
    fixture = new()
    stale = fixture.controller_with_a_stale_password()
    assert stale.status().locked == {"front": True, "rear": True}


# ----------------------------------------------------------------- the doors
def check_a_door_action_reaches_the_named_door(new):
    fixture = new()
    fixture.controller.perform("front", DoorAction.UNLOCK)
    assert fixture.controller.status().locked["front"] is False


def check_locking_a_door_leaves_the_other_alone(new):
    fixture = new()
    fixture.controller.perform("front", DoorAction.UNLOCK)
    fixture.controller.perform("rear", DoorAction.UNLOCK)
    fixture.controller.perform("front", DoorAction.LOCK)
    locked = fixture.controller.status().locked
    assert locked["front"] is True and locked["rear"] is False, locked


def check_an_unknown_door_is_refused(new):
    """A door this installation does not have is a configuration mistake, and
    it must not become an unlock of whichever door the firmware defaults to."""
    fixture = new()
    assert refuses(ControllerRefused,
                    fixture.controller.perform, "side", DoorAction.UNLOCK)


def check_status_reports_both_doors_locked_at_rest(new):
    """The lock flags are the firmware's intent, not a sensor, and they reset
    to locked on every boot. Strikes are energised to unlock, so a power cut
    locks the building."""
    fixture = new()
    locked = fixture.controller.status().locked
    assert locked == {"front": True, "rear": True}, locked
