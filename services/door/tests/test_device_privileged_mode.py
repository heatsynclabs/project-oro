#!/usr/bin/env python3
"""The fake controller's privileged mode, against the real firmware.

One global boolean for the whole device, a login that logs out only in the
chained form, and a lockout after five failures that arms exactly once. Every
one of these is a trap the door service is shaped around, so the fake keeps them
rather than cleaning them up.

Line numbers and constant names are from `Open_Access_Control_Ethernet.ino`.

    python3 services/door/tests/test_device_privileged_mode.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from door.adapters.fake.device import FakeController  # noqa: E402
from door.adapters.oac_ethernet import wire  # noqa: E402
from door.adapters.oac_ethernet.firmware import (  # noqa: E402
    LOGIN_FAILURES_BEFORE_LOCKOUT,
    LOGIN_LOCKOUT_SECONDS,
)

PASSWORD = "BEEF"


class _HandWoundClock:
    """A clock the test moves itself. The lockout window is five minutes and no
    test waits five minutes."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds


def _ask(device, path: str) -> str:
    return wire.body_of(device.handle(wire.build_http_request(path)))


def _new():
    return FakeController(password=PASSWORD)


def test_status_answers_without_a_login():
    """Lines 605 to 618. It is the only command that does."""
    device = _new()
    assert "door_1_locked" in _ask(device, "?9")
    assert device.privileged is False


def test_any_other_command_without_a_login_is_refused():
    device = _new()
    assert "Not logged in." in _ask(device, "?a")


def test_a_wrong_password_does_not_set_the_bit():
    device = _new()
    assert "authfail" in _ask(device, "?a&e=0000")
    assert device.privileged is False


def test_the_trailing_login_form_logs_out_in_the_same_request():
    device = _new()
    body = _ask(device, "?a&e=" + PASSWORD)
    assert body.startswith("authok\r\n")
    assert device.privileged is False


def test_a_bare_login_leaves_the_controller_privileged_to_the_whole_vlan():
    """This is the form the door service must never use. It is here so that a
    fake which stopped modelling the trap fails this file."""
    device = _new()
    _ask(device, "?e=" + PASSWORD)
    assert device.privileged is True


def test_a_command_issued_while_somebody_else_left_the_bit_set_succeeds():
    """Any client on the VLAN is privileged while the bit is set, regardless of
    who set it."""
    device = _new()
    _ask(device, "?e=" + PASSWORD)
    assert "UserNum" in _ask(device, "?a")


def test_enough_failed_logins_lock_privileged_mode_out():
    """Five failures and the controller refuses privileged mode for five
    minutes, so a correct password is answered `authfail` too. This is the
    likeliest way a live installation meets a refusal, and the adapter has to
    report it rather than read it as success."""
    device = _new()
    for _ in range(LOGIN_FAILURES_BEFORE_LOCKOUT):
        _ask(device, "?a&e=0000")
    assert "authfail" in _ask(device, "?a&e=" + PASSWORD)
    assert device.privileged is False


def test_one_failed_login_short_of_the_lockout_still_lets_the_service_in():
    device = _new()
    for _ in range(LOGIN_FAILURES_BEFORE_LOCKOUT - 1):
        _ask(device, "?a&e=0000")
    assert "authok" in _ask(device, "?a&e=" + PASSWORD)


def test_the_lockout_is_spent_once_its_window_has_passed():
    """The window is armed only while the failure count is zero, so once the
    first five minutes elapse the guard can never become true again and the
    throttle is gone for the life of the boot. It is modelled because a fake
    that quietly fixed it would let the service assume a protection that is not
    there."""
    clock = _HandWoundClock()
    device = FakeController(password=PASSWORD, clock=clock)
    for _ in range(LOGIN_FAILURES_BEFORE_LOCKOUT * 2):
        _ask(device, "?a&e=0000")
    clock.seconds += LOGIN_LOCKOUT_SECONDS
    for _ in range(LOGIN_FAILURES_BEFORE_LOCKOUT * 2):
        _ask(device, "?a&e=0000")
    assert "authok" in _ask(device, "?a&e=" + PASSWORD)


def _run() -> int:
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in fns:
        try:
            fn()
        except AssertionError as exc:
            failed.append((name, exc))
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - len(failed)}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
