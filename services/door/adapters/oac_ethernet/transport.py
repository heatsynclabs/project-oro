"""Getting bytes to the controller and back.

Separated from the codec so the fake can be the same codec talking to an in
memory device instead of a socket. Nothing here knows what a slot is.
"""
from __future__ import annotations

import socket
from typing import Protocol, runtime_checkable

from ..base import ControllerUnreachable
from .wire import build_http_request

# The controller answers most commands in milliseconds. Arming the alarm blocks
# for about six seconds in chirpAlarm(20), and this service does not arm the
# alarm, so five seconds is the bound. It is the same five seconds the door API
# error text promises a member.
DEFAULT_TIMEOUT_SECONDS = 5.0

# One read, and deliberately smaller than the largest answer the controller
# gives. The card table is 200 lines of about 17 bytes, so a table read takes
# several passes round the loop here and against the hardware, not only in a
# test. A chunk sized above the biggest answer hides a broken loop until the
# day somebody rewrites this method.
READ_CHUNK_BYTES = 1024


@runtime_checkable
class Transport(Protocol):
    """One request, one answer, one closed connection."""

    def send(self, path: str) -> bytes: ...


class SocketTransport:
    """A plain TCP socket to the controller on the door VLAN.

    Never point this anywhere but the controller. The password travels in the
    query string, so the URL is never logged and the firewall rule that makes
    this host the only one on the segment is what protects it.
    """

    def __init__(self, host: str, port: int = 80,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds

    def send(self, path: str) -> bytes:
        request = build_http_request(path)
        try:
            return self._exchange(request)
        except OSError as exc:
            raise ControllerUnreachable(
                f"The door controller at {self._host} did not answer within "
                f"{self._timeout_seconds} seconds. The command was not "
                "completed, so the door is unchanged and cards still work. If "
                "this keeps happening, check that the controller is powered "
                "and on the door network.") from exc

    def _exchange(self, request: bytes) -> bytes:
        """The answer has no Content-Length and no Connection header. It ends
        when the controller closes the socket, so a client that stops at the
        first read gets a truncated card table."""
        connection = socket.create_connection(
            (self._host, self._port), timeout=self._timeout_seconds)
        try:
            connection.sendall(request)
            answer = bytearray()
            while True:
                chunk = connection.recv(READ_CHUNK_BYTES)
                if not chunk:
                    return bytes(answer)
                answer.extend(chunk)
        finally:
            connection.close()
