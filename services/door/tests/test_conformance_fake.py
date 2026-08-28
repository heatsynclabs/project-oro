#!/usr/bin/env python3
"""Runs the conformance suite against the fake controller.

The fixture below is the only part specific to the fake. Phase 5 writes the
same eight answers against the hardware on the door VLAN and runs the identical
list of checks.

    python3 services/door/tests/test_conformance_fake.py
"""
from __future__ import annotations

import contextlib
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import conformance  # noqa: E402
from door.adapters.fake import FakeController, FakeTransport  # noqa: E402
from door.adapters.oac_ethernet import OacEthernetConfig, OacEthernetController  # noqa: E402

# Invented, and it is four hex characters because the firmware parses exactly
# four and passes them to strtoul base 16. The live value is in a secret store
# and is never in this repository.
TEST_PASSWORD = "BEEF"

# Long enough that eight unsynchronised threads would overlap, short enough
# that the suite still runs in well under a second.
FAKE_REQUEST_MILLISECONDS = 0.004

# Four hex characters, and not the device's. This is what a controller reflashed
# with a new password leaves the door service holding.
STALE_PASSWORD = "0000"


class ObservingTransport:
    """Wraps a transport to answer the questions the port cannot.

    Every method here is answerable against the real controller too: the same
    wrapper around a socket transport records the same things.
    """

    def __init__(self, inner):
        self._inner = inner
        self._lock = threading.Lock()
        self.sent = []
        self.in_flight = 0
        self.most_in_flight = 0
        self.lose_next_response = False

    def send(self, path: str) -> bytes:
        with self._lock:
            self.sent.append(path)
            self.in_flight += 1
            self.most_in_flight = max(self.most_in_flight, self.in_flight)
        try:
            time.sleep(FAKE_REQUEST_MILLISECONDS)
            answer = self._inner.send(path)
            if self.lose_next_response:
                self.lose_next_response = False
                raise ConnectionResetError(
                    "the fixture dropped this answer on purpose")
            return answer
        finally:
            with self._lock:
                self.in_flight -= 1


class FakeFixture:
    """What the conformance suite needs to know about a controller."""

    def __init__(self):
        self.password = TEST_PASSWORD
        self.device = FakeController(password=TEST_PASSWORD)
        self.transport = ObservingTransport(FakeTransport(self.device))
        self.controller = OacEthernetController(
            self.transport,
            OacEthernetConfig(password=TEST_PASSWORD,
                              doors={"front": 1, "rear": 2}),
        )

    def privilege_bit_set(self) -> bool:
        return self.device.privileged

    def requests(self):
        return list(self.transport.sent)

    def force_privileged(self) -> None:
        """What a crashed run that used a bare `?e=` login would leave behind."""
        self.device.privileged = True

    def drop_next_response(self) -> None:
        self.transport.lose_next_response = True

    def max_concurrent_requests(self) -> int:
        return self.transport.most_in_flight

    def controller_with_a_stale_password(self):
        """The same door and the same wires, holding a password the controller
        will refuse. On the real installation this is one line of configuration,
        and it costs one of the five failed logins the firmware allows before it
        locks privileged mode out for five minutes."""
        return OacEthernetController(
            self.transport,
            OacEthernetConfig(password=STALE_PASSWORD,
                              doors={"front": 1, "rear": 2}),
        )

    @contextlib.contextmanager
    def sabotage_writes(self):
        """The firmware path where `addUser` refuses a write and `printStatus`
        prints `cur:` regardless, so the answer claims a value the EEPROM does
        not hold."""
        self.device.reject_writes_silently = True
        try:
            yield
        finally:
            self.device.reject_writes_silently = False


def _bind(check):
    def run():
        check(FakeFixture)
    return run


for _name, _check in conformance.checks():
    globals()["test_" + _name] = _bind(_check)


def _run() -> int:
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed, skipped = [], []
    for name, fn in fns:
        try:
            fn()
        except conformance.Skipped as exc:
            skipped.append(name)
            print(f"SKIP {name}  {exc}")
        except AssertionError as exc:
            failed.append((name, exc))
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
    passed = len(fns) - len(failed) - len(skipped)
    print(f"\n{passed}/{len(fns)} passed, {len(skipped)} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
