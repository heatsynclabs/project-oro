"""A controller that speaks the real wire protocol, in memory.

Why it is built this way, because the next person will ask.

A fake that has drifted from the hardware is worse than no fake: the suite is
green and the door is broken. There are two ways to build one and they fail
differently.

The first is to write a second, independent implementation of the protocol
inside the fake. That catches a bug in the codec, because two implementations
that disagree show it. What it cannot do is stay honest over time. Every
protocol fact then exists in two files, and the day somebody fixes a parsing
bug in one of them is the day the fake starts lying.

The second, taken here, is to keep exactly one implementation of the protocol
in `oac_ethernet` and give it a transport it does not choose. The real adapter
gets a socket. The fake gets an in memory simulation of the device that the
same codec talks to over the same request bytes. The fake and the real adapter
then cannot disagree about the wire, because there is only one wire.

What that costs, stated rather than hidden: a bug in the codec is invisible to
the conformance suite, since both sides share it. That cost is paid in
`tests/test_wire.py`, which checks the codec against response bodies copied
from the firmware reading rather than against anything this package produces,
and in `tests/test_device.py`, which pins the device behaviours the port hides.
The conformance suite proves the adapter is correct given the protocol; those
two files are what say the protocol is right.

The alternative was weighed rather than assumed. If the controller is ever
replaced with hardware that has a real API, this decision should be revisited:
with a specification to test against, an independent fake stops being a
liability.
"""

from .device import FakeController
from .transport import FakeTransport

__all__ = ["FakeController", "FakeTransport", "build_fake_controller"]


def build_fake_controller(password: str = "1234",
                          doors=None):
    """A door controller backed by the fake device, for anything that needs one
    without the lab attached.

    The default password is the one in the public firmware repository. The live
    value is in a secret store and is not in this repository.
    """
    from ..oac_ethernet import OacEthernetConfig, OacEthernetController

    device = FakeController(password=password)
    controller = OacEthernetController(
        FakeTransport(device),
        OacEthernetConfig(password=password,
                          doors=doors or {"front": 1, "rear": 2}),
    )
    return controller, device
