#!/usr/bin/env python3
"""Prove members from the legacy application can sign in to the new one.

This is as close as a script gets to part (b) of the phase 2 password proof.
The members here were not invented in a fixture file: they were created on a
replica of the legacy Rails application, through its own schema and its own
models, with `Devise.stretches = 10` and no pepper, which is what
config/initializers/devise.rb sets. Their hashes are what that application
stored. tools/migration/README.md says how the replica is built and run.

What this still does not do is what only people can do: prove that passwords
real members actually chose survive the move. Every password here was chosen by
whoever wrote the replica, so the awkward cases are the ones somebody thought
of. Phase 2 does not exit on this file.

    ORO_IDENTITY_URL=... ORO_IDENTITY_TOKEN=... \\
      python3 tools/identity/tests/check_legacy_import.py
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import api                       # noqa: E402, after the path insert above

ROOT = pathlib.Path(__file__).resolve().parents[3]
DUMP = ROOT / "tools" / "migration" / "fixtures" / "legacy-data.sql"
PASSWORDS = ROOT / "tools" / "migration" / "fixtures" / "legacy-passwords.json"

TOKEN = os.environ.get("ORO_IDENTITY_TOKEN", "")
RUN = os.environ.get("ORO_IDENTITY_RUN", str(os.getpid()))

# bcrypt reads at most 72 bytes. Ruby truncates and accepts anything longer, Go
# refuses, and the identity service turns that refusal into a server error.
# tools/identity/README.md carries the measurement.
BCRYPT_INPUT_LIMIT = 72

STATE: dict = {"signed_in": [], "refused": [], "over_limit": []}


def _hashes_from_the_dump() -> dict:
    """Read the stored credential out of the dump, not out of a JSON file.

    The point of this file is that the hash came from the legacy application.
    Reading it from anywhere but that application's own dump would quietly
    weaken the claim.
    """
    rows = {}
    for line in DUMP.read_text().splitlines():
        # pg_dump --column-inserts names its columns, so the fields are read by
        # name. Picking the first value that looks like an address instead would
        # work until a member had an emergency contact and no email of their own.
        found = re.match(r"INSERT INTO legacy\.users \((.*?)\) VALUES \((.*)\);$", line)
        if not found:
            continue
        names = [c.strip() for c in found.group(1).split(",")]
        # Quoted strings, NULL, booleans, numbers. The count check below is
        # what found the missing booleans, so it stays.
        fields = re.findall(r"'((?:[^']|'')*)'|(\bNULL\b|\btrue\b|\bfalse\b)|(-?[\d.]+)",
                            found.group(2))
        values = [a.replace("''", "'") if a else (b or c) for a, b, c in fields]
        if len(values) != len(names):
            raise AssertionError(
                f"{len(names)} columns and {len(values)} values on one row of "
                f"{DUMP.name}. The parser and the dump disagree")
        row = dict(zip(names, values))
        if row.get("email") and row.get("encrypted_password", "").startswith("$2a$"):
            rows[row["email"].lower()] = row["encrypted_password"]
    return rows


def _import_and_sign_in() -> None:
    hashes = _hashes_from_the_dump()
    known = json.loads(PASSWORDS.read_text())["members"]
    for member in known:
        email = member["email"].lower()
        digest = hashes.get(email)
        if digest is None:
            STATE["refused"].append(f"{email}: no hash in the dump")
            continue
        login = f"{RUN}-{email}"
        imported = api.import_member(login, digest, TOKEN)
        if imported.status != 200:
            STATE["refused"].append(f"{email}: import {imported.status} {imported.message()}")
            continue
        answer = api.sign_in(login, member["password"], TOKEN)
        record = {"email": email, "bytes": member["bytes"],
                  "status": answer.status, "user_id": imported.body.get("userId", "")}
        if answer.status == 201:
            STATE["signed_in"].append(record)
        else:
            STATE["refused"].append(f"{email}: sign in {answer.status}")
        if member["bytes"] > BCRYPT_INPUT_LIMIT:
            STATE["over_limit"].append(record)


def test_every_legacy_hash_was_accepted():
    """None of them may be refused at import. A refusal is a locked out member."""
    rejected = [r for r in STATE["refused"] if "import" in r]
    assert not rejected, "the identity service refused: " + "; ".join(rejected)


def test_the_dump_carries_hashes_the_legacy_application_wrote():
    hashes = _hashes_from_the_dump()
    assert hashes, f"no bcrypt hashes found in {DUMP}"
    for email, digest in hashes.items():
        assert digest.startswith("$2a$10$"), f"{email} is not a cost 10 hash: {digest[:7]}"


def test_every_member_within_the_bcrypt_limit_can_sign_in():
    """The claim the whole migration rests on.

    A member whose password bcrypt can read must be able to use it afterwards.
    Anything else and cutover day locks the building's members out of their own
    records.
    """
    expected = [m for m in json.loads(PASSWORDS.read_text())["members"]
                if m["bytes"] <= BCRYPT_INPUT_LIMIT]
    signed = {r["email"] for r in STATE["signed_in"]}
    missing = [m["email"] for m in expected if m["email"].lower() not in signed]
    assert not missing, (
        "these members could not sign in with the password the legacy "
        "application stored for them: " + ", ".join(missing))


def test_the_members_over_the_bcrypt_limit_are_the_only_ones_refused():
    over = {r["email"] for r in STATE["over_limit"]}
    signed = {r["email"] for r in STATE["signed_in"]}
    assert not (over & signed), (
        "a password of more than 72 bytes signed in, which would be an "
        "improvement. tools/identity/README.md is then out of date")
    unexpected = [r for r in STATE["refused"] if "sign in" in r
                  and r.split(":")[0] not in over]
    assert not unexpected, "refused for some other reason: " + "; ".join(unexpected)


def test_a_legacy_password_would_be_refused_as_a_new_one():
    """Signing in works. Changing a password to the same value does not.

    Zitadel 4.17.1 defaults its complexity policy to eight characters with an
    uppercase, a lowercase, a number and a symbol, read from cmd/defaults.yaml
    under DefaultInstance.PasswordComplexityPolicy. The legacy application asked
    for six characters and nothing else, read from devise 2.2.7's lib/devise.rb.

    So every migrated member can sign in, and most of them meet a wall the first
    time they change their password. That is a decision for the lab rather than
    a defect, and it is asserted here so it cannot be discovered by a member on
    cutover day.
    """
    victim = next((r for r in STATE["signed_in"]
                   if r["email"] == "ada@fixture.invalid"), None)
    assert victim, "the member this reads did not sign in, so it proved nothing"
    answer = api.set_password(victim["user_id"],
                              "correct horse battery staple", TOKEN)
    assert answer.status != 200, (
        "the new policy accepted a password the legacy application would have "
        "stored. If the policy was relaxed deliberately, this check should say "
        "so instead")


def test_the_replica_produced_a_password_over_the_limit():
    """Otherwise the check above proves nothing, because it had nothing to catch.

    The legacy application accepts a password of up to 128 characters, read from
    devise 2.2.7's own lib/devise.rb, so this case is not hypothetical.
    """
    assert STATE["over_limit"], (
        "no member in the fixture has a password over 72 bytes, so nothing here "
        "exercises the one case that breaks")


def _run() -> int:
    checks = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    failed = []
    for name, fn in checks:
        try:
            fn()
        except AssertionError as exc:
            failed.append(name)
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
    for row in sorted(STATE["signed_in"], key=lambda r: r["email"]):
        print(f"  signed in  {row['email']:32} {row['bytes']:3} bytes")
    for row in sorted(STATE["over_limit"], key=lambda r: r["email"]):
        print(f"  refused    {row['email']:32} {row['bytes']:3} bytes, over the bcrypt limit")
    return 1 if failed else 0


if __name__ == "__main__":
    if not TOKEN:
        print("No ORO_IDENTITY_TOKEN, so nothing was checked.", file=sys.stderr)
        sys.exit(1)
    _import_and_sign_in()
    sys.exit(_run())
