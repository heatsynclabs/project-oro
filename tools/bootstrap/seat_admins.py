#!/usr/bin/env python3
"""Seat the lab's first admins, so that somebody can administer this system.

    tools/bootstrap/seat_admins.py \\
      --admin "Ada Byron <ada@example.org>" \\
      --admin "Grace Hopper <grace@example.org>" \\
      --admin "Katherine Johnson <katherine@example.org>"

A fresh database holds no members and the identity service holds one
administrator, and there is no path from there to a person who can administer
the lab. This is that path, and it is the only one.

Three people, because db/migrations/013_bootstrap_three_admins.sql allows three
grants of a role that can grant roles with no approval behind them, and no more,
ever. Two is the smallest number the two approver rule can bind at and leaves
the lab with no spare. The third is the spare. The fourth is refused by the
database, and this command has no opinion about that: it prints what the
database said.

Each person needs three things, and this does all three or none of them:

  an account on the identity service, holding a password they must change
  a row in members, carrying the subject that account will arrive with
  a row in member_roles granting admin

Each is named on the command line rather than read from a file, so that nobody's
address is committed to this repository by somebody who was in a hurry. Rule 13.

It talks to the identity service and to Postgres itself, because services/api
does not exist yet. When it does, this becomes a call to it.

What a failure leaves behind: the identity account is made first, because the
member row cannot be written until the subject that account will arrive with is
known. So a database refusal leaves an account that holds no role and can do
nothing here, and the report says which one. The database side is one
transaction and rolls back whole.

Safe to run again. It reports what is already seated and writes nothing.
"""
from __future__ import annotations

import argparse
import collections
import email.utils
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "identity"))

import api                  # noqa: E402, tools/identity/api.py, after the inserts
import database             # noqa: E402
import handover             # noqa: E402
import identity_accounts    # noqa: E402

Person = collections.namedtuple("Person", "name email")
Outcome = collections.namedtuple("Outcome", "seated changed")


def person_from(written: str) -> Person:
    """One --admin argument, written the way an address is written in a mail app."""
    name, address = email.utils.parseaddr(written)
    if "@" not in address:
        raise SystemExit(
            f"{written!r} is not an address, so nobody was seated. Write each "
            'admin as --admin "Ada Byron <ada@example.org>".')
    if not name.strip():
        raise SystemExit(
            f"{written!r} needs a name as well as an address, so nobody was "
            "seated. The name goes on the member row and it is what everybody "
            'else sees. Write it as --admin "Ada Byron <ada@example.org>".')
    return Person(name.strip(), address)


def account_for(person: Person, token: str, terminal) -> tuple[str, bool]:
    """This person's identity account, made now or found from an earlier run."""
    subject = identity_accounts.find(person.email, token)
    if subject:
        print("  identity account   already there")
        return subject, False
    password = handover.new_password()
    subject = identity_accounts.create(person.email, person.name, password, token)
    terminal.hand_over(person.email, password)
    print("  identity account   created")
    return subject, True


def seat_one(person: Person, token: str, terminal) -> Outcome:
    print(f"\n{person.name} <{person.email}>")
    subject, account_is_new = account_for(person, token, terminal)
    member_row = database.member_row_state(subject, person.email)
    try:
        _, granted, said = database.seat(subject, person.email, person.name)
    except database.Refused as refused:
        report_the_refusal(person, refused, account_is_new)
        return Outcome(seated=False, changed=account_is_new)
    for warning in database.warnings(said):
        print(warning, file=sys.stderr)
    print("  member row         " + member_row)
    print("  admin role         " + ("granted" if granted else "already held"))
    return Outcome(seated=True,
                   changed=account_is_new or granted or member_row != "already there")


def report_the_refusal(person: Person, refused: database.Refused,
                       account_is_new: bool) -> None:
    """Print what the database said, and what the run left behind.

    The database's own words, unedited. Nothing here restates the rule, so this
    still reads correctly on the day somebody changes it.
    """
    print(f"\nThe database refused to make {person.name} an admin:\n",
          file=sys.stderr)
    for line in refused.said.splitlines():
        print("  " + line, file=sys.stderr)
    print("\n" + database.seat_state(), file=sys.stderr)
    print("\nNothing was written to the members database for this person. The "
          "member row and\nthe role are one transaction and both rolled back.",
          file=sys.stderr)
    if account_is_new:
        print(f"\nThe account for {person.email} on the identity service was "
              "made before the\ndatabase was asked, and it is still there. It "
              "holds no role and can do nothing\nhere. Leave it, or remove it "
              "through the identity service.", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--admin", action="append", required=True,
                        metavar='"NAME <ADDRESS>"',
                        help="a person to seat, named once per admin")
    parser.add_argument("--token", default=api.token_from_environment(),
                        help="a token that can administer the identity service")
    arguments = parser.parse_args()
    people = [person_from(written) for written in arguments.admin]
    if not arguments.token:
        raise SystemExit("No token, so nobody was seated. Pass --token, or set "
                         "ORO_IDENTITY_TOKEN. make bootstrap-admins reads one "
                         "out of the identity container.")
    complaint = database.schema_is_missing()
    if complaint:
        raise SystemExit(complaint)

    try:
        terminal = handover.terminal()
    except handover.NoTerminal as why:
        raise SystemExit(str(why)) from why

    changed = False
    with terminal:
        for person in people:
            outcome = seat_one(person, arguments.token, terminal)
            changed = changed or outcome.changed
            if not outcome.seated:
                return 1
    print("\n" + database.seat_state())
    if not changed:
        print("Nothing changed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except api.Refused as refused:
        raise SystemExit(str(refused)) from refused
