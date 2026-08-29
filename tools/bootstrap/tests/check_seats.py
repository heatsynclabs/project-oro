#!/usr/bin/env python3
"""What seating the first admins left behind, read back from both systems.

Every check here reads the running identity service and the running database.
Nothing is stubbed, because the thing being proved is that two systems agree
about who may administer this one.

    ORO_PSQL=... ORO_IDENTITY_URL=... ORO_IDENTITY_TOKEN=... \\
      ORO_BOOTSTRAP_PEOPLE=... ORO_BOOTSTRAP_TRANSCRIPT=... check_seats.py

tools/bootstrap/tests/run.sh sets all five and brings up the stack they point
at.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "identity"))

import api          # noqa: E402, after the path inserts above
import database     # noqa: E402

TOKEN = os.environ.get("ORO_IDENTITY_TOKEN", "")
PEOPLE = [line for line in os.environ.get("ORO_BOOTSTRAP_PEOPLE", "").splitlines()
          if line.strip()]
TRANSCRIPT = pathlib.Path(os.environ.get("ORO_BOOTSTRAP_TRANSCRIPT", "/dev/null"))

# The line the command writes to the terminal for each person it created. It is
# read here rather than guessed at, so a change to the wording fails this suite
# instead of quietly leaving the sign in checks unable to sign anybody in.
HANDOVER = re.compile(r"^\s*(\S+@\S+)\s+first sign in password:\s+(\S+)\s*$",
                      re.MULTILINE)


def emails() -> list[str]:
    return [person.split("<")[1].rstrip(">").strip() for person in PEOPLE]


def passwords() -> dict[str, str]:
    return dict(HANDOVER.findall(TRANSCRIPT.read_text(errors="replace")))


def refusal(sql: str, variables: dict[str, str] | None = None) -> str:
    """Run this and hand back what the database refused it with.

    Wrapped in a transaction nothing commits, so a check that measures a refusal
    leaves no row behind on the day the refusal stops happening.
    """
    answer = database.psql("BEGIN;\n" + sql + "\nROLLBACK;", variables)
    assert answer.returncode != 0, "this was not refused at all:\n" + sql
    return answer.stderr


def account(email: str) -> dict:
    found = api.call("/v2/users", {"queries": [
        {"loginNameQuery": {"loginName": email}}]}, TOKEN)
    assert found.status == 200, f"{email}: the search was refused: {found.message()}"
    result = found.body.get("result") or []
    assert len(result) == 1, f"{email}: the identity service holds {len(result)} of these"
    return result[0]


def test_the_command_printed_a_password_for_every_person():
    assert sorted(passwords()) == sorted(emails()), (
        f"the terminal carried passwords for {sorted(passwords())}, and the "
        f"three people were {sorted(emails())}")


def test_each_person_has_a_member_row_carrying_their_identity_subject():
    for email in emails():
        subject = database.ask(
            "SELECT coalesce(max(identity_subject), 'no row') FROM members "
            "WHERE email = :'email'", {"email": email})
        assert subject == account(email)["userId"], (
            f"{email}: the member row carries {subject!r} and the identity "
            f"service calls them {account(email)['userId']!r}, so nothing will "
            "recognise them when they sign in")


def test_each_person_holds_a_live_admin_role():
    for email in emails():
        held = database.ask(
            "SELECT count(*) FROM member_roles r JOIN members m ON m.id = r.member_id "
            "WHERE m.email = :'email' AND r.role_id = 'admin' AND r.revoked_at IS NULL",
            {"email": email})
        assert held == "1", f"{email} holds {held} live admin roles, wanted 1"


def test_every_seat_was_taken_with_no_approval_behind_it():
    """The escape is a grant with a null approval, and that is what counts it.

    A row carrying an approval would mean somebody built an approval to satisfy
    the rule, which nobody could have done: there were no admins to approve it.
    """
    approved = database.ask(
        "SELECT count(*) FROM member_roles WHERE role_id = 'admin' "
        "AND approval_id IS NOT NULL")
    assert approved == "0", f"{approved} bootstrap grants carry an approval"


def test_each_person_can_sign_in_to_the_identity_service():
    for email, password in passwords().items():
        answer = api.sign_in(email, password, TOKEN)
        assert answer.status == 201, (
            f"{email} could not sign in with the password the command printed: "
            f"{answer.status} {answer.message()}")


def test_a_password_belonging_to_nobody_does_not_sign_in():
    """The refusal without which the check above proves only that something answers."""
    email = emails()[0]
    answer = api.sign_in(email, "not the password", TOKEN)
    assert answer.status == 400, answer.status
    assert "Password is invalid" in answer.message(), answer.message()


def test_the_handover_password_has_to_be_changed_at_the_first_sign_in():
    for email in emails():
        human = account(email)["human"]
        assert human.get("passwordChangeRequired") is True, (
            f"{email} can keep the password an operator typed at them. That "
            "password was read out loud and it is written in a terminal "
            "somewhere, so it is a handover rather than a credential")


def test_a_member_row_that_already_exists_is_reported_as_claimed():
    """The lab has paying members who never made an account, and one of them
    could be the person being seated. link_or_create_member claims that row by
    address rather than writing a second one, and the report has to say so.
    """
    state = database.member_row_state("a-subject-nobody-has", emails()[0])
    assert state.startswith("claimed"), (
        f"a member row for {emails()[0]} is already there, and this reads "
        f"{state!r}")


def test_the_two_approver_rule_is_armed():
    armed = database.ask("SELECT count(*) FROM two_approver_armed")
    assert armed == "1", (
        "two_approver_armed is empty, so the bootstrap escape is still open "
        "and one admin can still grant admin with nobody approving it")


def test_the_quota_is_spent():
    used = database.ask("SELECT bootstrap_admin_grants_used()")
    quota = database.ask("SELECT bootstrap_admin_quota()")
    assert used == quota, f"{used} of {quota} bootstrap grants used"


def test_the_application_role_cannot_grant_a_role_with_nobody_signed_in():
    """Why the command connects as the owner rather than as the application role.

    This is the state the very first run is in: no member is signed in, because
    no member can sign in yet. The application role has no way through it.
    """
    refused = refusal("""
        SET LOCAL ROLE oro_api;
        INSERT INTO member_roles (member_id, role_id)
        SELECT id, 'board' FROM members LIMIT 1;""")
    assert "No identity set on this transaction" in refused, refused


def test_the_application_role_cannot_grant_admin_even_as_an_admin():
    """The escape is closed from the seat the API will occupy, not only from ours."""
    subject = database.ask(
        "SELECT identity_subject FROM members WHERE email = :'email'",
        {"email": emails()[0]})
    refused = refusal("""
        SET LOCAL ROLE oro_api;
        SET LOCAL oro.identity_subject = :'subject';
        SELECT link_or_create_member('a-subject-belonging-to-nobody',
                                     'nobody@example.invalid', 'Nobody Yet') AS id \\gset
        INSERT INTO member_roles (member_id, role_id) VALUES (:'id', 'admin');""",
        {"subject": subject})
    assert "needs an approval from a second admin" in refused, refused


def _run() -> int:
    checks = [(name, function) for name, function in sorted(globals().items())
              if name.startswith("test_") and callable(function)]
    failed = []
    for name, function in checks:
        try:
            function()
        except AssertionError as unmet:
            failed.append(name)
            print(f"FAIL {name}  {unmet}")
        except Exception as broke:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}  {type(broke).__name__}: {broke}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    if not TOKEN or not PEOPLE:
        print("No ORO_IDENTITY_TOKEN or no ORO_BOOTSTRAP_PEOPLE, so nothing "
              "was checked. tools/bootstrap/tests/run.sh sets both.",
              file=sys.stderr)
        sys.exit(1)
    sys.exit(_run())
