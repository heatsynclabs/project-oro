"""The password a new admin is handed, and the one place it is ever written.

A handover password is read out loud or typed into a chat window by whoever
runs the command, and it stops being a credential the moment the person signs
in, because the identity service makes them choose their own before it lets
them past. Until then it opens an account that can administer this system, so
it is treated as a secret while it lives.

It is written to /dev/tty and nowhere else. The report goes to stdout, which is
what a person redirects into a file to keep, and rule 13 of CLAUDE.md is that a
secret does not go into a file. Writing to the terminal directly means
`seat_admins.py ... > seated.txt` keeps the report and captures no password.

That is also why this refuses to run with no terminal attached. A run that
seated three admins and printed their passwords nowhere would leave three
accounts nobody can sign in to and no way to recover them short of resetting
each one by hand.
"""
from __future__ import annotations

import secrets

# No O, no 0, no I, no l and no 1. This gets read out over a phone, and a
# character somebody has to ask about twice is a character that ends up wrong.
UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
LOWER = "abcdefghijkmnopqrstuvwxyz"
DIGITS = "23456789"
# Speakable, and each one has a name people agree on.
SYMBOLS = "!#%+=?"

# Four from each set. The identity service ships a policy asking for eight
# characters with an upper case letter, a lower case letter, a number and a
# symbol, so one of each is the floor rather than the target.
FROM_EACH_SET = 4


class NoTerminal(Exception):
    """There is nowhere to hand a password over, so nothing should be created."""


def new_password() -> str:
    letters = []
    for alphabet in (UPPER, LOWER, DIGITS, SYMBOLS):
        letters += [secrets.choice(alphabet) for _ in range(FROM_EACH_SET)]
    secrets.SystemRandom().shuffle(letters)
    return "".join(letters)


class Terminal:
    """Where a handover password is written, and the only place one is.

    The explanation is written once, and only when there is a first password to
    explain. A run that seats nobody new says nothing about passwords, because
    it handed none over.
    """

    def __init__(self, where):
        self.where = where
        self.explained = False

    def __enter__(self) -> "Terminal":
        return self

    def __exit__(self, *closing) -> None:
        self.where.close()

    def hand_over(self, email: str, password: str) -> None:
        if not self.explained:
            self.where.write(
                "\nThese passwords are on this terminal and in no file. Give "
                "each one to the\nperson it belongs to, and to nobody else. The "
                "identity service makes them\nchoose their own the first time "
                "they sign in.\n\n")
            self.explained = True
        self.where.write(f"  {email}  first sign in password: {password}\n")
        self.where.flush()


def terminal() -> Terminal:
    """The terminal this command was run from, whatever stdout was pointed at.

    /dev/tty is the controlling terminal rather than a stream somebody can
    redirect, which is the whole point. It is opened before anything is created,
    so a run with nowhere to print a password refuses before it makes an
    account.
    """
    try:
        return Terminal(open("/dev/tty", "w"))   # noqa: SIM115, Terminal closes it
    except OSError as why:
        raise NoTerminal(
            "There is no terminal to hand the passwords over on, so nobody was "
            f"seated. The system said: {why}. Run this from a terminal. Each "
            "new admin gets a password that is printed there and nowhere else, "
            "and a run that printed them into a pipe would leave you with "
            "accounts you cannot sign in to.") from why
