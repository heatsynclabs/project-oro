#!/usr/bin/env python3
"""Prove make_a_sign_in.py refuses what it cannot do and writes what it can.

Needs no identity service and no database. Every call is a stub, because what
is under test is what the command does with an answer rather than what the
service sends. tools/identity/tests/check_making_a_sign_in.py is the other half
and runs the same command against a real one.

    python3 tools/identity/tests/check_sign_ins.py

The refusals matter most. An account in USER_STATE_INITIAL has to be left
alone: the only way out of that state removes the member's subject with it.
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[2] / "bootstrap"))

import api                # noqa: E402, after the path inserts above
import database           # noqa: E402
import handover           # noqa: E402
import make_a_sign_in     # noqa: E402
import sign_ins           # noqa: E402

TOKEN = "not-a-real-token"
ADDRESS = "ada@example.invalid"

ACTIVE_AND_WHOLE = {
    "userId": "1", "state": sign_ins.ACTIVE, "preferredLoginName": ADDRESS,
    "human": {"profile": {"displayName": "Ada Byron"},
              "email": {"email": ADDRESS, "isVerified": True},
              "passwordChanged": "2026-08-31T00:00:00Z"}}
STUCK_ACCOUNT = dict(ACTIVE_AND_WHOLE, state=sign_ins.STUCK)


def without_a(field: str) -> dict:
    """The same account with one thing missing, which is what repair puts back."""
    human = dict(ACTIVE_AND_WHOLE["human"])
    if field == "password":
        human.pop("passwordChanged")
    else:
        human["email"] = {"email": ADDRESS}
    return dict(ACTIVE_AND_WHOLE, human=human)


class Terminal:
    """Stands in for /dev/tty, and keeps what was written to it."""

    def __init__(self):
        self.handed_over = []

    def hand_over(self, login: str, password: str) -> None:
        self.handed_over.append((login, password))


class Service:
    """Stands in for the identity service, and keeps every call it was given.

    A search answers with the accounts it was made with. Everything else
    answers 200, because no caller here reads a field out of one.
    """

    def __init__(self, accounts=(), search_status=200, member_row=""):
        self.accounts = list(accounts)
        self.search_status = search_status
        self.member_row = member_row
        # What the UPDATE that repoints the row says it changed. The row id by
        # default, and an empty string to stand for a row that is not there.
        self.moved_row = member_row.split(" ", 1)[0]
        self.calls = []

    def ask(self, sql, variables=None):
        """The members database, on the same list, because the order matters.

        Reading the row after the account is gone reads nothing, and two
        separate lists cannot show that happening.
        """
        self.calls.append((sql.split()[0], "the members database", variables))
        if sql.lstrip().startswith("SELECT"):
            return self.member_row
        return self.moved_row

    def call(self, path, body, token, method="POST"):
        self.calls.append((method, path, body))
        if path == "/v2/users":
            return api.Answer(self.search_status, {"result": self.accounts})
        return api.Answer(200, {"userId": "2"})

    def set_password(self, user_id, password, token):
        self.calls.append(("POST", f"/v2/users/{user_id}/password", {}))
        return api.Answer(200, {})

    def wrote(self) -> list:
        return [(method, path) for method, path, _ in self.calls
                if path != "/v2/users"]


@contextlib.contextmanager
def standing_in(service: Service):
    """Put the stubs in place, and take them out again whatever happens."""
    kept = (api.call, api.set_password, database.ask, database.schema_is_missing)
    (api.call, api.set_password, database.ask, database.schema_is_missing) = (
        service.call, service.set_password, service.ask, lambda: "")
    try:
        yield
    finally:
        (api.call, api.set_password, database.ask,
         database.schema_is_missing) = kept


def run(service: Service, do) -> tuple[str, str]:
    """Run one thing against the stubs and hand back what it printed and said."""
    printed = io.StringIO()
    with standing_in(service), contextlib.redirect_stdout(printed):
        try:
            do()
        except (SystemExit, api.Refused) as refused:
            return printed.getvalue(), str(refused)
    return printed.getvalue(), ""


def a_person_written_wrong_is_refused():
    service = Service()
    _, said = run(service, lambda: sign_ins.person_from("Ada Byron"))
    assert "is not an address" in said, f"the refusal reads {said!r}"
    assert service.calls == [], f"it called the service anyway: {service.calls}"
    _, said = run(service, lambda: sign_ins.person_from("<ada@example.invalid>"))
    assert "needs a name" in said, f"the refusal reads {said!r}"


def a_new_sign_in_is_active_at_once():
    service = Service()
    terminal = Terminal()
    run(service, lambda: make_a_sign_in.make_one(
        sign_ins.Person("Ada Byron", ADDRESS), TOKEN, terminal))
    written = [body for method, path, body in service.calls
               if path == "/v2/users/human"]
    assert len(written) == 1, f"it made {len(written)} accounts"
    assert written[0]["email"].get("isVerified") is True, (
        "the address is not verified, so the member is stopped at a screen "
        "asking for a code no mail server will send")
    assert written[0].get("password", {}).get("password"), (
        "no password was set, so the member is stopped at Set Password, which "
        "also asks for a code")
    assert terminal.handed_over == [(ADDRESS, written[0]["password"]["password"])], (
        f"the password was not handed over: {terminal.handed_over}")


def the_password_is_never_printed():
    service = Service()
    terminal = Terminal()
    printed, _ = run(service, lambda: make_a_sign_in.make_one(
        sign_ins.Person("Ada Byron", ADDRESS), TOKEN, terminal))
    assert terminal.handed_over[0][1] not in printed, (
        "the password is in the report, which is the stream a person redirects "
        "into a file")


def a_second_run_writes_nothing():
    service = Service(accounts=[ACTIVE_AND_WHOLE])
    printed, _ = run(service, lambda: make_a_sign_in.make_one(
        sign_ins.Person("Ada Byron", ADDRESS), TOKEN, Terminal()))
    assert service.wrote() == [], f"it wrote {service.wrote()}"
    assert "already there" in printed, f"it said {printed!r}"


def a_stuck_account_is_refused_and_nothing_is_written():
    service = Service(accounts=[STUCK_ACCOUNT])
    printed, said = run(service, lambda: make_a_sign_in.repair_one(
        ADDRESS, TOKEN, Terminal(), False))
    assert service.wrote() == [], (
        f"it wrote {service.wrote()} to an account it cannot repair")
    assert "removed" not in printed, f"it removed something: {printed!r}"
    # What the refusal has to carry: the state, the price of going on, and the
    # thing to type. A refusal missing any of the three sends somebody guessing.
    for wanted in (sign_ins.STUCK, "subject", "member row",
                   "--remove-and-recreate"):
        assert wanted in said, f"the refusal never says {wanted!r}: {said!r}"


def an_unverified_address_is_repaired_through_the_v1_path():
    service = Service(accounts=[without_a("verified address")])
    run(service, lambda: make_a_sign_in.repair_one(
        ADDRESS, TOKEN, Terminal(), False))
    paths = [(method, path) for method, path, _ in service.calls]
    assert ("PUT", "/management/v1/users/1/email") in paths, (
        f"it did not verify the address the way that works: {paths}. The v2 "
        'path refuses one that is not changing with "Email not changed".')


def an_account_with_no_password_is_given_one():
    service = Service(accounts=[without_a("password")])
    terminal = Terminal()
    run(service, lambda: make_a_sign_in.repair_one(
        ADDRESS, TOKEN, terminal, False))
    assert ("POST", "/v2/users/1/password") in service.wrote(), (
        f"no password was set: {service.wrote()}")
    assert terminal.handed_over, "the password was not handed over on the terminal"


def an_account_that_is_already_right_is_left_alone():
    service = Service(accounts=[ACTIVE_AND_WHOLE])
    printed, _ = run(service, lambda: make_a_sign_in.repair_one(
        ADDRESS, TOKEN, Terminal(), False))
    assert service.wrote() == [], f"it wrote {service.wrote()}"
    assert "Nothing changed" in printed, f"it said {printed!r}"


def a_search_that_is_not_one_account_is_refused():
    """A 401 and two accounts both read as an answer, and neither is one."""
    for service, wanted in ((Service(search_status=401), "401"),
                            (Service(accounts=[ACTIVE_AND_WHOLE] * 2), "2 accounts")):
        _, said = run(service, lambda s=service: make_a_sign_in.make_one(
            sign_ins.Person("Ada Byron", ADDRESS), TOKEN, Terminal()))
        assert wanted in said, f"the refusal reads {said!r}"
        assert service.wrote() == [], (
            f"it wrote {service.wrote()} after an answer it should refuse")


def the_member_row_is_read_before_anything_is_removed():
    service = Service(accounts=[STUCK_ACCOUNT], member_row="an-id Ada Byron")
    printed, said = run(service, lambda: make_a_sign_in.repair_one(
        ADDRESS, TOKEN, Terminal(), True))
    assert said == "", f"it refused: {said!r}"
    order = [path for _, path, _ in service.calls]
    assert order.index("the members database") < order.index("/v2/users/1"), (
        f"it read the member row after removing the account it hangs off, "
        f"which reads nothing: {order}")
    assert order.index("/v2/users/1") < order.index("/v2/users/human"), (
        f"it made the replacement before removing the old one: {order}")
    assert "an-id Ada Byron" in printed, (
        f"it never said which member row was joined: {printed!r}")
    assert "pointed at the new sign in" in printed, (
        f"it left the member row on the subject it removed: {printed!r}")


def a_repoint_that_changed_no_row_is_refused():
    """An UPDATE matching nothing does not raise, so the count is the check."""
    service = Service(accounts=[STUCK_ACCOUNT], member_row="an-id Ada Byron")
    service.moved_row = ""
    _, said = run(service, lambda: make_a_sign_in.repair_one(
        ADDRESS, TOKEN, Terminal(), True))
    assert "by hand" in said, f"it reported a move that did not happen: {said!r}"


def the_two_borrowed_modules_import_nothing_of_ours():
    """What makes importing tools/bootstrap from tools/identity safe.

    identity_accounts.py there already imports api.py here, so an arrow the
    other way is only not a cycle while the far end reaches for nothing of
    ours. The day one does, this goes red and the shared code moves.
    """
    for module in (database, handover):
        source = pathlib.Path(module.__file__).read_text()
        assert "sys.path" not in source, (
            f"{module.__file__} puts a directory of ours on the path, so it "
            "imports something of ours and this import is now a cycle")


# Named by the function, because a label beside one is a label that can go stale.
CHECKS = [(check.__name__.replace("_", " "), check) for check in (
    a_person_written_wrong_is_refused,
    a_new_sign_in_is_active_at_once,
    the_password_is_never_printed,
    a_second_run_writes_nothing,
    a_stuck_account_is_refused_and_nothing_is_written,
    an_unverified_address_is_repaired_through_the_v1_path,
    an_account_with_no_password_is_given_one,
    an_account_that_is_already_right_is_left_alone,
    a_search_that_is_not_one_account_is_refused,
    the_member_row_is_read_before_anything_is_removed,
    a_repoint_that_changed_no_row_is_refused,
    the_two_borrowed_modules_import_nothing_of_ours,
)]


def _run() -> int:
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
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
