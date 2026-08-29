"""Wires the real codec to the fake device instead of to a socket."""
from __future__ import annotations

from ..oac_ethernet.wire import build_http_request
from .device import FakeController


class FakeTransport:
    """Satisfies the same Transport port `SocketTransport` does.

    It hands the device the identical request bytes a socket would carry, so
    the request window, the framing, and the parsing are all exercised.
    """

    def __init__(self, device: FakeController) -> None:
        self._device = device

    def send(self, path: str) -> bytes:
        return self._device.handle(build_http_request(path))
