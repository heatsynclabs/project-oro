"""Reaching the members database from the bootstrap command.

There is no API service. services/api does not exist yet, so this opens psql on
the database and writes the rows itself. That is a layer this repository will
not keep: when the API service arrives, seating an admin becomes a call to it
and this file goes away.

Which role it connects as, and why that role rather than the application role.
member_roles has FORCE ROW LEVEL SECURITY, and its INSERT policy is
is_admin(current_member_id()). On the first day nobody is signed in, so
current_member_id() raises before the policy has anything to decide, and with no
admin in the table it would decide against you anyway. The application role has
no way through that, on purpose. The role that owns the schema does, because it
is the superuser the migrations ran as and row level security does not apply to
a superuser. tools/bootstrap/tests/run.sh proves both halves.

The database publishes no port. compose.yaml says so and means it, so the way in
is the psql inside the container, which is the route make psql takes. ORO_PSQL
replaces that command whole, and the suite uses it to point this at a throwaway
compose project instead of the stack somebody is running.
"""
from __future__ import annotations

import os
import pathlib
import shlex
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEAT_SQL = pathlib.Path(__file__).resolve().parent / "seat_one_admin.sql"

DEFAULT_PSQL = ("docker compose -f " + shlex.quote(str(ROOT / "compose.yaml"))
                + " exec -T db psql -U postgres -d oro")


class Refused(Exception):
    """The database answered, and the answer was no.

    Carries the database's own words, because they are the authority on why.
    Nothing in this command restates the rule it was refused by: a second copy
    of a rule goes stale in silence, and the copy people read is the wrong one.
    """

    def __init__(self, said: str):
        super().__init__(said)
        self.said = said


def psql(sql: str, variables: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run SQL and hand back everything psql said, including its warnings.

    Values go in as psql variables and are read as :'name', which quotes them as
    SQL literals. Nothing is pasted into the statement text.
    """
    command = shlex.split(os.environ.get("ORO_PSQL") or DEFAULT_PSQL)
    command += ["-tAq", "-v", "ON_ERROR_STOP=1"]
    for name, value in (variables or {}).items():
        command += ["-v", f"{name}={value}"]
    return subprocess.run(command, input=sql, capture_output=True, text=True,
                          check=False)


def ask(sql: str, variables: dict[str, str] | None = None) -> str:
    """One value out of the database, or a refusal carrying what it said."""
    answer = psql(sql, variables)
    if answer.returncode != 0:
        raise Refused(answer.stderr.strip() or
                      "psql exited " + str(answer.returncode) + " and said nothing")
    return answer.stdout.strip()


def schema_is_missing() -> str:
    """Why this database cannot be seated into, or an empty string when it can.

    The stack that compose.yaml starts has an empty database, which make up says
    plainly, so this is the first thing a person hits rather than a rare one.
    """
    try:
        present = ask("SELECT count(*) FROM pg_tables "
                      "WHERE schemaname = 'public' AND tablename = 'member_roles'")
    except Refused as refused:
        return ("The database did not answer, so nobody was seated. It said:\n"
                f"{refused.said}\n"
                "This command reaches the database the way make psql does. If "
                "the stack is not up, start it with make up.")
    if present != "1":
        return ("This database has no members schema, so nobody was seated. "
                "Apply db/migrations to it first, oldest file first. The stack "
                "that make up starts has an empty database on purpose, and "
                "nothing in this repository has applied the schema to it yet.")
    return ""


def member_row_state(subject: str, email: str) -> str:
    """What the members table holds for this person, read before anything is written.

    Three answers rather than two, because the lab has paying members who never
    made an account. link_or_create_member claims a row like that by email
    instead of writing a second one, and a report that called that "created"
    would be describing something that did not happen.
    """
    return ask("""SELECT CASE
        WHEN EXISTS (SELECT 1 FROM members WHERE identity_subject = :'subject')
          THEN 'already there'
        WHEN EXISTS (SELECT 1 FROM members WHERE email = :'email')
          THEN 'claimed, and it was a member row already'
        ELSE 'created' END""", {"subject": subject, "email": email})


def seat(subject: str, email: str, name: str) -> tuple[str, bool, str]:
    """Give this person a member row and the admin role, in one transaction.

    Returns the member id, whether the admin role was granted by this call
    rather than already held, and everything psql wrote to its error stream. The
    last of those carries the warning the database raises on a bootstrap grant,
    which names the seat it took and is the only record that it happened.

    Half of this is worse than none: a member row written for somebody the
    database then refuses to make an admin is a row nobody asked for, so the
    whole of it rolls back together.

    The identity account has to exist before this runs. A member row that
    already holds a role is not claimable by link_or_create_member, which is
    deliberate and is the ordering constraint in data-model.md section 6.1.
    """
    answer = psql(SEAT_SQL.read_text(),
                  {"subject": subject, "email": email, "name": name})
    if answer.returncode != 0:
        raise Refused(answer.stderr.strip())
    member_id, _, granted = answer.stdout.strip().partition(" ")
    return member_id, granted == "1", answer.stderr


def warnings(said: str) -> list[str]:
    """The database's own warning lines, which are the record of each seat taken."""
    return [line for line in said.splitlines() if line.startswith("WARNING:")]


def seat_state() -> str:
    """What the database says about the escape, in the database's own numbers."""
    used = ask("SELECT bootstrap_admin_grants_used() || ' of ' "
               "|| bootstrap_admin_quota()")
    armed = ask("SELECT count(*) FROM two_approver_armed") == "1"
    closed = ("The two approver rule is armed. Granting admin now needs a "
              "second admin to approve it, and revoking one does not open this "
              "again.")
    open_still = ("The two approver rule is not armed yet, so one admin can "
                  "still grant admin with nobody approving it. Seat the rest.")
    return (f"{used} bootstrap admin grants are used.\n"
            + (closed if armed else open_still))
