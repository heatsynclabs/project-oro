#!/usr/bin/env python3
"""Run make_a_sign_in.py against a real identity service and a real database.

The other half of tools/identity/tests/check_sign_ins.py, which stubs
everything and needs nothing running. What is proved here is the part a stub
cannot prove: that Zitadel refuses what this command says it refuses, and that
a person handed a password by this command can sign in with it.

    ORO_IDENTITY_URL=... ORO_IDENTITY_TOKEN=... ORO_PSQL=... \\
      python3 tools/identity/tests/check_making_a_sign_in.py

tools/identity/tests/run.sh brings up its own stack, applies the schema, reads
the token out of the container and runs this.

The command writes its password to /dev/tty and nowhere else, so a check suite
cannot read it out of a pipe. tools/bootstrap/tests/on_a_terminal.py runs it
with a pseudo terminal attached and keeps both streams apart, which is how the
report can be checked for a password that must not be in it.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(ROOT / "tools" / "bootstrap"))

import api                # noqa: E402, after the path inserts above
import database           # noqa: E402
import sign_ins           # noqa: E402

TOKEN = os.environ.get("ORO_IDENTITY_TOKEN", "")
COMMAND = ROOT / "tools" / "identity" / "make_a_sign_in.py"
ON_A_TERMINAL = ROOT / "tools" / "bootstrap" / "tests" / "on_a_terminal.py"

# Every run makes its own logins, because this can be pointed at a stack that
# is already up and doing that twice with fixed names fails on accounts the
# suite made itself. Invented, and .invalid cannot be registered by anybody.
RUN = os.environ.get("ORO_IDENTITY_RUN", str(os.getpid()))
WHOLE = f"Wren Kestrel <wren-{RUN}@example.invalid>"
STUCK = f"stuck-{RUN}@example.invalid"
UNVERIFIED = f"unverified-{RUN}@example.invalid"


class Ran:
    """One run of the command, with its two streams kept apart.

    report is stdout, which is what a person redirects into a file, and it is
    checked on its own so that a password appearing in it fails. Refusals go to
    the error stream, which on_a_terminal.py leaves on the pseudo terminal
    beside the handover password, so everything is where a refusal is looked
    for.
    """

    def __init__(self, report: str, terminal: str, status: int):
        self.report = report
        self.terminal = terminal
        self.everything = report + terminal
        self.status = status

    def password(self) -> str:
        """The handover password, read off the terminal the way a person does."""
        for line in self.terminal.splitlines():
            if "first sign in password:" in line:
                return line.rsplit(":", 1)[1].strip()
        raise AssertionError(
            f"no password was handed over on the terminal:\n{self.terminal}")


def command(*arguments: str) -> Ran:
    work = pathlib.Path(tempfile.mkdtemp())
    report, terminal = work / "report", work / "terminal"
    done = subprocess.run(
        ["python3", str(ON_A_TERMINAL), str(terminal), str(report),
         str(COMMAND), *arguments],
        capture_output=True, text=True, check=False)
    return Ran(report.read_text(),
               terminal.read_text(errors="replace") + done.stderr,
               done.returncode)


def account(login: str) -> dict:
    return sign_ins.account_named(login, TOKEN)


# The service answers a search out of a read model it updates after the write,
# so an account made a moment ago can be missing from one and an account just
# replaced can still read as the one that was removed. Same shape as the
# machine secret wait in api.py, and measured here as a suite that failed once
# on a busy machine and never on an idle one. Seconds, one try a second.
VISIBLE_TRIES = 30


def visible(login: str, unlike: str = "") -> dict:
    """Wait for the search to show this account, and not the one it replaced."""
    for _ in range(VISIBLE_TRIES):
        held = account(login)
        if held and held["userId"] != unlike:
            return held
        time.sleep(1)
    raise AssertionError(
        f"the identity service still lists no account for {login} after "
        f"{VISIBLE_TRIES} seconds, or lists the one that was replaced")


def signs_in(login: str, password: str) -> int:
    """A session, which is the check the password screen makes, without a browser."""
    return api.call("/v2/sessions", {"checks": {
        "user": {"loginName": login},
        "password": {"password": password}}}, TOKEN).status


def a_sign_in_is_made_and_signs_in():
    ran = command(WHOLE)
    assert ran.status == 0, f"the command exited {ran.status}:\n{ran.everything}"
    held = visible(WHOLE.split("<")[1].rstrip(">"))
    assert held.get("state") == sign_ins.ACTIVE, f"it is {held.get('state')}"
    assert sign_ins.address_is_verified(held), "the address is not verified"
    assert sign_ins.holds_a_password(held), "it holds no password"
    assert signs_in(held["preferredLoginName"], ran.password()) == 201, (
        "the password the command handed over does not sign in")


def the_password_is_on_the_terminal_and_not_in_the_report():
    ran = command(f"Ida Bramble <ida-{RUN}@example.invalid>")
    assert ran.password(), "nothing was handed over"
    assert ran.password() not in ran.report, (
        "the password is in the report, which is the stream a person redirects "
        f"into a file:\n{ran.report}")


def a_second_run_makes_no_second_account():
    ran = command(WHOLE)
    assert ran.status == 0, f"the command exited {ran.status}:\n{ran.everything}"
    assert "already there" in ran.report, f"it said:\n{ran.everything}"
    assert "Nothing changed" in ran.report, f"it said:\n{ran.everything}"


def a_stuck_account(login: str) -> dict:
    """One made the way self registration makes one, which is the v1 path.

    A human with no password lands in USER_STATE_INITIAL. The v2 path this
    repository uses everywhere else does not: it lands active whatever it is
    given. Both measured on 2026-08-31.
    """
    made = api.call("/management/v1/users/human", {
        "userName": login, "profile": {"firstName": "Stuck", "lastName": "Member"},
        "email": {"email": login, "isEmailVerified": True}}, TOKEN)
    assert made.status == 200, f"the fixture account was refused: {made.body}"
    held = visible(login)
    assert held.get("state") == sign_ins.STUCK, (
        f"the fixture is {held.get('state')} rather than {sign_ins.STUCK}, so "
        "nothing below is testing what it says it is")
    return held


def the_identity_service_refuses_every_repair_of_a_stuck_account():
    held = a_stuck_account(f"refusals-{RUN}@example.invalid")
    user_id = held["userId"]
    setting = api.set_password(user_id, "Not-Going-To-Work-1!", TOKEN)
    assert setting.status == 400 and "not yet initialized" in setting.message(), (
        f"setting a password answered {setting.status} {setting.message()}. "
        "If this now works, the command's refusal is out of date and so is "
        "tools/identity/README.md.")
    verifying = api.call(sign_ins.VERIFY_ADDRESS.format(user_id=user_id),
                         {"email": held["human"]["email"]["email"],
                          "isEmailVerified": True}, TOKEN, method="PUT")
    assert verifying.status == 400, (
        f"verifying the address answered {verifying.status} "
        f"{verifying.message()} rather than refusing")


def the_command_refuses_a_stuck_account_and_leaves_it_there():
    a_stuck_account(STUCK)
    ran = command("--repair", STUCK)
    assert ran.status != 0, "it did not refuse"
    assert sign_ins.STUCK in ran.everything, (
        f"it never named the state:\n{ran.everything}")
    assert "--remove-and-recreate" in ran.everything, (
        f"it never said what to type next:\n{ran.everything}")
    assert account(STUCK), "it removed the account anyway"


def a_member_row_for(subject: str, login: str) -> str:
    """A row written the way a first sign in writes one, and its id."""
    return database.ask(
        "SELECT link_or_create_member(:'subject', :'email', 'Stuck Member')",
        {"subject": subject, "email": login})


def removing_and_recreating_replaces_the_account_and_keeps_the_member():
    old = account(STUCK)
    member_id = a_member_row_for(old["userId"], STUCK)
    ran = command("--repair", STUCK, "--remove-and-recreate")
    assert ran.status == 0, f"the command exited {ran.status}:\n{ran.everything}"
    new = visible(STUCK, unlike=old["userId"])
    assert new["userId"] != old["userId"], "the subject did not change"
    assert new.get("state") == sign_ins.ACTIVE, f"it is {new.get('state')}"
    assert signs_in(STUCK, ran.password()) == 201, (
        "the replacement account does not sign in")
    still = database.ask("SELECT id::text FROM members "
                         "WHERE identity_subject = :'subject'",
                         {"subject": new["userId"]})
    assert still == member_id, (
        f"the member row is {still!r} rather than {member_id!r}, so the row "
        "was left pointing at a subject that no longer exists")


def an_unverified_address_is_put_right_and_the_v2_path_refuses_it():
    made = api.call("/v2/users/human", {
        "username": UNVERIFIED,
        "profile": {"givenName": "Unverified", "familyName": "Member"},
        "email": {"email": UNVERIFIED},
        "password": {"password": "Handover-Fixture-1!", "changeRequired": True},
    }, TOKEN)
    assert made.status == 200, f"the fixture account was refused: {made.body}"
    refused = api.call(f"/v2/users/{made.body['userId']}/email",
                       {"email": UNVERIFIED, "isVerified": True}, TOKEN)
    assert refused.status == 400 and "not changed" in refused.message(), (
        f"the v2 path answered {refused.status} {refused.message()}. If it "
        "verifies an address that is not changing now, sign_ins.VERIFY_ADDRESS "
        "should move back to it.")
    ran = command("--repair", UNVERIFIED)
    assert ran.status == 0, f"the command exited {ran.status}:\n{ran.everything}"
    assert sign_ins.address_is_verified(visible(UNVERIFIED)), (
        f"the address is still unverified:\n{ran.everything}")


def a_working_account_is_not_removed():
    login = WHOLE.split("<")[1].rstrip(">")
    ran = command("--repair", login, "--remove-and-recreate")
    assert ran.status != 0, "it removed an account that works"
    assert account(login), "the account is gone"
    assert "without --remove-and-recreate" in ran.everything, (
        f"it never said what to do instead:\n{ran.everything}")


CHECKS = [
    ("a sign in is made and signs in", a_sign_in_is_made_and_signs_in),
    ("the password is on the terminal and not in the report",
     the_password_is_on_the_terminal_and_not_in_the_report),
    ("a second run makes no second account", a_second_run_makes_no_second_account),
    ("the identity service refuses every repair of a stuck account",
     the_identity_service_refuses_every_repair_of_a_stuck_account),
    ("the command refuses a stuck account and leaves it there",
     the_command_refuses_a_stuck_account_and_leaves_it_there),
    ("removing and recreating replaces the account and keeps the member",
     removing_and_recreating_replaces_the_account_and_keeps_the_member),
    ("an unverified address is put right and the v2 path refuses it",
     an_unverified_address_is_put_right_and_the_v2_path_refuses_it),
    ("a working account is not removed", a_working_account_is_not_removed),
]


def _run() -> int:
    if not TOKEN:
        print("No ORO_IDENTITY_TOKEN, so nothing was checked.")
        return 1
    failed = []
    for name, check in CHECKS:
        try:
            check()
        except AssertionError as exc:
            failed.append(name)
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {name}")
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
