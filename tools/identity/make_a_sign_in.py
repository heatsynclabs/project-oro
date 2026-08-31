#!/usr/bin/env python3
"""Make somebody a sign in, or repair one that is stuck.

    tools/identity/make_a_sign_in.py "Ada Byron <ada@example.org>"
    tools/identity/make_a_sign_in.py --repair ada@example.org

Self registration is off and this stack configures no mail server, so both of
the ways a person would otherwise get in on their own are gone. An admin does
it instead, standing next to them, and this is that command.

What it makes: an account carrying a password the person has to change, with
the address recorded as verified because the operator is looking at the person
rather than at a mailbox. That pair leaves the account in USER_STATE_ACTIVE,
which is the only state the hosted screens let anybody past.

The password is written to /dev/tty and to nothing else, so redirecting the
report into a file keeps the report and captures no password. Rule 13, and the
same reasoning as tools/bootstrap/seat_admins.py, whose terminal this borrows.

What --repair puts right and what it will not. An account in USER_STATE_ACTIVE
that holds no password, or whose address was never verified, is fixed here with
no mail sent. An account in USER_STATE_INITIAL cannot be repaired at all: every
write to it is refused with "User is not yet initialized", and the one thing
that clears the state is a code the identity service will not send while it has
no SMTP configuration. tools/identity/README.md carries every measurement.

So --repair refuses that account and says what it found. Removing it and making
a new one is the only route, it costs the member their subject, and it is a
second flag to type rather than something a command hands you for running it.

Safe to run again. A second run of either form finds the work already done,
writes nothing, and says so.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
# tools/bootstrap holds the terminal a handover password is written to and the
# way in to the members database. Imported rather than copied: two password
# generators drifting apart is two password shapes for one lab, and two ways
# into one database is two of them to fix when the API service takes over. The
# arrow between these directories already points the other way, from
# tools/bootstrap/identity_accounts.py to api.py here, so this only stays safe
# while neither of those two modules imports anything of ours.
# tests/check_sign_ins.py asserts exactly that.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bootstrap"))

import api         # noqa: E402, after the path inserts above
import database    # noqa: E402, tools/bootstrap/database.py
import handover    # noqa: E402, tools/bootstrap/handover.py
import sign_ins    # noqa: E402


def make_one(person: sign_ins.Person, token: str, terminal) -> int:
    print(f"\n{person}")
    account = sign_ins.account_named(person.address, token)
    if account:
        print("  sign in            already there, " + sign_ins.describe(account))
        print("\nNothing changed. To put a sign in right rather than make one, "
              f"run\n  tools/identity/make_a_sign_in.py --repair {person.address}")
        return 0
    sign_ins.create(person, token, terminal)
    print("  sign in            made, and active")
    print("\nThey sign in with the address above and the password on this "
          "terminal. The\nidentity service makes them choose their own before "
          "it lets them any further.")
    return 0


def repair_active(account: dict, token: str, terminal) -> bool:
    """Put an active account right. Returns whether anything was written."""
    changed = False
    if not sign_ins.address_is_verified(account):
        sign_ins.verify_the_address(account, token)
        print("  address            marked verified")
        changed = True
    if not sign_ins.holds_a_password(account):
        sign_ins.set_a_password(account, token, terminal)
        print("  password           set")
        changed = True
    return changed


def refuse_the_stuck_one(account: dict) -> None:
    """Say what was found, what it costs to go on, and what to type.

    Nothing here restates a rule this command owns. The refusal is a
    measurement of the identity service, and it names the file that holds the
    measurement so the day it changes there is one place to correct.
    """
    login = account["preferredLoginName"]
    raise SystemExit(
        f"\n{login} is stuck in {sign_ins.STUCK}, and nothing was changed.\n\n"
        'Every write to an account in that state is refused with "User is not '
        'yet\ninitialized". Setting a password, verifying the address and '
        "changing it are all\nrefused, measured against Zitadel 4.17.1 on "
        "2026-08-31. The one thing that clears\nthe state is a code the "
        "identity service sends by mail, and it has no SMTP\nconfiguration, so "
        "it sends nothing and answers the caller 200 either way.\n\n"
        "The only route left is to remove this account and make a new one. "
        "That gives\nthem a new subject, so their member row has to be pointed "
        "at it, and everything\nthe identity service holds against the old "
        "subject goes with it: their sessions,\ntheir second factor if they "
        "set one, and the record that the account existed.\n\n"
        "If that is what you want:\n"
        f"  tools/identity/make_a_sign_in.py --repair {login} "
        "--remove-and-recreate")


def member_row_for(subject: str) -> str:
    """The member row joined to this subject, or an empty string when none is.

    db/migrations/008_system_paths.sql makes members.identity_subject the join,
    and link_or_create_member matches on it before it matches on anything else.
    A row left pointing at a subject that no longer exists cannot be claimed by
    the replacement account: the function falls through to the email branch and
    refuses with "That email already belongs to another account." Measured
    against this schema on 2026-08-31.
    """
    return database.ask("SELECT id || ' ' || name FROM members "
                        "WHERE identity_subject = :'subject'",
                        {"subject": subject})


def remove_and_recreate(account: dict, token: str, terminal) -> int:
    """Take the stuck account away and put a working one in its place.

    The member row is read before anything is removed, because a row that
    cannot be read afterwards is a member locked out of their own history. If
    the database will not answer, this refuses with the identity service
    untouched.
    """
    login = account["preferredLoginName"]
    complaint = database.schema_is_missing()
    if complaint:
        raise SystemExit(complaint + "\n\nNothing on the identity service was "
                         "touched. A member row that cannot be read now "
                         "cannot\nbe pointed at the new sign in afterwards.")
    joined = member_row_for(account["userId"])
    print("  member row         " + (joined or "none joined to this subject"))
    person = sign_ins.person_from(f"{sign_ins.display_name(account)} <{login}>")
    sign_ins.remove(account, token)
    print("  old sign in        removed")
    try:
        subject = sign_ins.create(person, token, terminal)
    except api.Refused as refused:
        raise SystemExit(
            f"{refused}\n\nThe old account for {login} is already gone, so "
            "this person now has no sign in\nat all. Make them one:\n"
            f'  tools/identity/make_a_sign_in.py "{person}"') from refused
    print("  new sign in        made, and active")
    return repoint(joined, subject, login)


def repoint(joined: str, subject: str, login: str) -> int:
    if not joined:
        print("\nNo member row was joined to the old sign in, so there was "
              "nothing to point at\nthe new one. Their row is written the "
              "first time they sign in.")
        return 0
    member_id = joined.split(" ", 1)[0]
    # RETURNING, because an UPDATE that matches no row does not raise. Without
    # it a row deleted between the read above and this write would leave the
    # member on a subject that no longer exists and this command saying it had
    # been moved. HANDOFF.md section 7 has the same trap in the database suite.
    moved = database.ask("UPDATE members SET identity_subject = :'subject' "
                         "WHERE id = :'member'::uuid RETURNING id",
                         {"subject": subject, "member": member_id})
    if moved != member_id:
        raise SystemExit(
            f"The new sign in for {login} was made, and the member row "
            f"{member_id} was not\npointed at it: the update changed "
            f"{moved!r} rather than that row. Point it at\n{subject} by hand "
            "with make psql, or that member cannot claim their own row.")
    print("  member row         pointed at the new sign in")
    print(f"\n{login} keeps their member row, their roles and their door "
          "history. What is\ngone is the old subject and everything the "
          "identity service held against it.")
    return 0


def repair_one(login: str, token: str, terminal, remove_it: bool) -> int:
    print(f"\n{login}")
    account = sign_ins.account_named(login, token)
    if not account:
        raise SystemExit(
            f"The identity service holds no account for {login}, so there is "
            "nothing to\nrepair. To make one:\n"
            f'  tools/identity/make_a_sign_in.py "Their Name <{login}>"')
    if account.get("state") == sign_ins.STUCK:
        if not remove_it:
            refuse_the_stuck_one(account)
        return remove_and_recreate(account, token, terminal)
    if remove_it:
        raise SystemExit(
            f"\n{login} is {sign_ins.describe(account)}, so removing it would "
            "take away an account\nthat works. Nothing was changed. Run this "
            "again without --remove-and-recreate.")
    if repair_active(account, token, terminal):
        print("\nThey can sign in now.")
        return 0
    print("  sign in            " + sign_ins.describe(account))
    print("\nNothing changed.")
    return 0


def one_thing_to_do(arguments) -> None:
    if bool(arguments.person) == bool(arguments.repair):
        raise SystemExit(
            "Name one person to make a sign in for, or --repair one address. "
            "Not both, and\nnot neither.\n"
            '  tools/identity/make_a_sign_in.py "Ada Byron <ada@example.org>"\n'
            "  tools/identity/make_a_sign_in.py --repair ada@example.org")
    if not arguments.token:
        raise SystemExit("No token, so nothing was done. Pass --token, or set "
                         "ORO_IDENTITY_TOKEN. tools/identity/README.md says "
                         "how to read one out of the\nidentity container.")


def a_terminal():
    """Where the password goes, opened before anything is created.

    handover.NoTerminal says its piece in the words of the command that first
    needed it, which seats admins. Reworded here rather than quoted, so a
    reader at 2am is told about the thing they ran.
    """
    try:
        return handover.terminal()
    except handover.NoTerminal as why:
        raise SystemExit(
            "There is no terminal to hand the password over on, so nothing was "
            "done. Run\nthis from a terminal. The password is printed there "
            "and in no file, and a run\nthat printed it into a pipe would "
            "leave somebody an account they cannot sign\ninto.") from why


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("person", nargs="?", metavar='"NAME <ADDRESS>"',
                        help="the person to make a sign in for")
    parser.add_argument("--repair", metavar="ADDRESS",
                        help="put an existing sign in right instead")
    parser.add_argument("--remove-and-recreate", action="store_true",
                        help="with --repair, take a stuck account away and "
                             "make a new one in its place")
    parser.add_argument("--token", default=api.token_from_environment(),
                        help="a token that can administer the identity service")
    arguments = parser.parse_args()
    one_thing_to_do(arguments)
    with a_terminal() as terminal:
        if arguments.repair:
            return repair_one(arguments.repair, arguments.token, terminal,
                              arguments.remove_and_recreate)
        return make_one(sign_ins.person_from(arguments.person),
                        arguments.token, terminal)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (api.Refused, database.Refused) as refused:
        raise SystemExit(str(refused)) from refused
