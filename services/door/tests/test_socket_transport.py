#!/usr/bin/env python3
"""The socket transport, against a local server rather than the controller.

The controller is on a VLAN at the lab and nothing here has ever spoken to it.
What this file does check is the framing rule that catches every naive client:
the answer has no `Content-Length` and no `Connection` header, and it ends when
the peer closes the socket.

    python3 services/door/tests/test_socket_transport.py
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from door.adapters.base import ControllerUnreachable  # noqa: E402
from door.adapters.oac_ethernet.transport import (  # noqa: E402
    READ_CHUNK_BYTES,
    SocketTransport,
)

HEADER = (b"HTTP/1.1 200 OK\r\nCache-Control: no-store\r\n"
          b"Content-Type: text/html\r\n\r\n")
BODY = HEADER + b"authok\r\n"

# The answer to `?a`, which is the largest thing the controller ever says and
# the one a truncating client turns into an empty card table. 200 slot lines,
# and no Content-Length anywhere in it.
CARD_TABLE = (HEADER + b"authok\r\n<pre>\r\nUserNum: Usermask: TagNum:\r\n"
              + b"".join(("%d\t255\tFFFFFFFF\r\n" % slot).encode("ascii")
                         for slot in range(200))
              + b"</pre>\r\n")

# Long enough that the client's first read has certainly returned before the
# rest of the answer is written. Without a pause both pieces land in one recv
# on loopback, and then a client that reads once still passes.
PIECE_DELAY_SECONDS = 0.25


def _serve(answer, hang: bool = False, pause_seconds: float = 0.0):
    """A one shot server that answers the way the controller does."""
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    received = []

    def run():
        connection, _ = listener.accept()
        received.append(connection.recv(200))
        if not hang:
            for piece in answer:
                connection.sendall(piece)
                time.sleep(pause_seconds)
            connection.close()
        else:
            threading.Event().wait(2.0)
            connection.close()
        listener.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return listener.getsockname()[1], received, thread


def test_the_answer_is_read_until_the_peer_closes():
    """There is no Content-Length. A client that stops at the first read gets
    a truncated card table and then plans to clear every slot it did not see.

    The fixture makes that failure certain rather than likely. The card table is
    larger than one read chunk, so a single read truncates it whatever the
    timing does, and the second piece is written only after the client's first
    read has already returned.
    """
    assert len(CARD_TABLE) > READ_CHUNK_BYTES, len(CARD_TABLE)
    split = len(HEADER) + 40
    port, _, thread = _serve([CARD_TABLE[:split], CARD_TABLE[split:]],
                             pause_seconds=PIECE_DELAY_SECONDS)
    answer = SocketTransport("127.0.0.1", port, timeout_seconds=2.0).send("?a")
    thread.join(2.0)
    assert answer == CARD_TABLE


def test_the_request_reaches_the_controller_as_a_get():
    port, received, thread = _serve([BODY])
    SocketTransport("127.0.0.1", port, timeout_seconds=2.0).send("?9")
    thread.join(2.0)
    assert received[0].startswith(b"GET /?9 ")


def test_a_controller_that_does_not_answer_is_reported_rather_than_hung():
    """The legacy app used bare `open()` with no timeout, so a dead controller
    held a request for 60 seconds and then raised a 500 at an admin."""
    port, _, thread = _serve([], hang=True)
    try:
        SocketTransport("127.0.0.1", port, timeout_seconds=0.2).send("?9")
        raised = False
    except ControllerUnreachable:
        raised = True
    thread.join(3.0)
    assert raised


def test_a_closed_port_is_reported_as_unreachable():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    try:
        SocketTransport("127.0.0.1", port, timeout_seconds=0.5).send("?9")
        raised = False
    except ControllerUnreachable:
        raised = True
    assert raised


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
