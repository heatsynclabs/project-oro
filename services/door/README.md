# Door service

## What it is

The part of Project ORO that speaks to the Arduino running
[Open_Access_Control_Ethernet](https://github.com/heatsynclabs/Open_Access_Control_Ethernet),
the controller that holds the card table and opens the building.

What exists today is the controller port, one adapter, a fake controller, and
the conformance suite both must pass. There is no HTTP API, no reconcile loop,
and nothing has ever spoken to the real controller. Those are phase 5, and
`docs/plan/order-of-operations.md` says why the port was built in phase 1
instead: three rewrites over eight years stalled at the door, so the riskiest
unknown gets retired early even though it ships late.

```
domain/     Slots, tag numbers, permission masks, the reconcile diff. Pure
adapters/
  base.py         The port every controller must satisfy
  oac_ethernet/   The current Arduino: firmware numbers, slot range, codec,
                  socket, lock
  fake/           The same codec, talking to a simulated device in memory
tests/            The conformance suite, and the tests that make it worth running
```

Everything specific to this hardware is inside `oac_ethernet/`. The domain layer
never sees a URL, and the port is written in terms of slots and doors rather
than query strings, so replacing the controller is one component and not a
project.

`adapters/fake/__init__.py` carries the reasoning for the shape of the fake,
which is the decision this package turns on.

### The parts that are not obvious

- **The privilege bit is one global boolean for the whole device.** While it is
  set, anything on the door VLAN is privileged. So every privileged command
  carries a trailing logout parameter, which makes login and logout atomic
  inside one request, and everything serialises through one lock.
- **Slot 200 is refused here rather than by the firmware.** The firmware's own
  bounds check lets it through, and its five bytes land on the persisted alarm
  state. Usable slots are 10 to 199, and the base address is 24. That range is
  EEPROM geometry, so it lives in `oac_ethernet/slot_range.py` and is derived
  from `firmware.py`. The domain has no ceiling of its own and the layers above
  read one from `capabilities()`.
- **A write is believed only after the slot is read back.** The controller
  prints its current value before it checks whether the write succeeded.
- **So is a door action.** Every answer is HTTP 200 with the refusal as a string
  in the body, so an unlock the controller refused looks exactly like one that
  worked until the body is read. A member standing at the door is told what
  actually happened.
- **Tag numbers are uppercase with no leading zeros, on both sides.** A diff
  that always differs rewrites every slot on every pass while reporting
  success, and the firmware never calls `EEPROM.update`, so that wears the card
  table out.

## How to run it

There is no service to start yet. To drive the fake controller by hand:

```python
import sys; sys.path.insert(0, "services")
from door.adapters.fake import build_fake_controller

controller, device = build_fake_controller()
controller.write_slot(10, "0000abcd", 1)
controller.read_card_table()      # (SlotEntry(slot=10, tag='ABCD', mask=1),)
device.privileged                 # False, after every completed operation
```

`build_fake_controller` hands back the controller and the device behind it. The
device is there so a caller can look at what the hardware would be holding:
`eeprom`, `eeprom_writes`, `privileged`, and `door_locked`.

## How to test it

```sh
services/door/tests/run.sh
```

Six files, no arguments, about two seconds. Each one also runs on its own.

| File | What it holds |
|---|---|
| `test_domain.py` | Tag normalisation, permission masks, and the diff |
| `test_wire.py` | The codec against response bodies read from the firmware |
| `test_device.py` | The fake against the firmware behaviour it stands in for |
| `test_device_privileged_mode.py` | The global privilege bit and the login lockout |
| `test_socket_transport.py` | Framing, against a local socket rather than the lab |
| `test_conformance_fake.py` | The conformance suite, bound to the fake |

`conformance.py` holds the fixture contract and the shared tools. The checks
themselves are in `checks_device.py` and `checks_card_table.py`, and none of
the three holds an adapter. Phase 5 binds the same checks to `oac_ethernet`
against the hardware by writing one more fixture: the controller, plus eight
answers the port cannot give on its own. They are listed at the top of
`conformance.py`, and all eight are answerable against the real controller. A
check only the fake can pass would prove nothing.

The suite was checked against deliberate breaks of the implementation: raising
the slot ceiling to include 200, believing a write without reading it back,
believing a door action without reading it back, removing the serialising lock,
dropping the uppercase rule on tag numbers, making the reconcile diff rewrite
every slot, and replacing the socket read loop with a single read. Each one
turned a check red, and the read loop break was caught on five runs out of
five rather than intermittently.

## What it depends on

Python 3.8 or newer, standard library only. No third party packages, so a
volunteer can run this with nothing installed, and there is no lockfile to
resolve at 2am. If that ever changes it needs an ADR in `docs/decisions/`.
