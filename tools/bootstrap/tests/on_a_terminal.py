#!/usr/bin/env python3
"""Run a command with a real terminal attached, and keep what it wrote there.

tools/bootstrap/seat_admins.py writes each handover password to /dev/tty and
everything else to stdout, so that redirecting the report into a file cannot
capture a password. A check suite is not a terminal, so without this there is
no way to read the passwords back and prove the three people can sign in.

    on_a_terminal.py TRANSCRIPT REPORT COMMAND [ARGUMENT ...]

The command runs with stdout redirected into REPORT and a pseudo terminal as
its controlling terminal, so /dev/tty inside it is the pseudo terminal and
everything written there lands in TRANSCRIPT. Exit code is the command's.

pty.spawn rather than a plain pipe, because /dev/tty resolves to the
controlling terminal rather than to whatever stdout happens to be, and only
os.forkpty, which pty.spawn uses, gives the child one.
"""
from __future__ import annotations

import os
import pathlib
import pty
import shlex
import sys


def main() -> int:
    if len(sys.argv) < 4:
        raise SystemExit(
            "on_a_terminal.py TRANSCRIPT REPORT COMMAND [ARGUMENT ...]")
    transcript, report = sys.argv[1], sys.argv[2]
    command = sys.argv[3:]

    seen: list[bytes] = []

    def keep(descriptor: int) -> bytes:
        chunk = os.read(descriptor, 1024)
        seen.append(chunk)
        return chunk

    redirected = f"exec {shlex.join(command)} > {shlex.quote(report)}"
    status = pty.spawn(["sh", "-c", redirected], keep)
    pathlib.Path(transcript).write_bytes(b"".join(seen))
    return os.waitstatus_to_exitcode(status)


if __name__ == "__main__":
    sys.exit(main())
