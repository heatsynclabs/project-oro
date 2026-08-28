#!/usr/bin/env python3
"""Prove the identity service can hold the passwords the lab already has.

Phase 2 of docs/plan/order-of-operations.md splits the password proof in two,
because the obvious criterion cannot be executed: signing in as twenty real
members needs their passwords, and the whole point of a hash is that nobody has
them. This file is part (a), the synthetic half, and it is the half that can be
automated. Part (b) needs the production hashes and ten volunteers, and no
script can stand in for it.

What is proved here: a hash written by bcrypt-ruby at cost 10 with no pepper,
which is what the legacy application writes, is accepted by this identity
service, and the member it belongs to can sign in with the password they
already use. The awkward cases are the point. An ordinary password proves
almost nothing.

Run it against a stack that is already up:

    ORO_IDENTITY_URL=http://localhost:8180 ORO_IDENTITY_TOKEN=... \\
      python3 tools/identity/tests/check_identity.py

tools/identity/tests/run.sh brings up its own stack, reads the token out of it,
runs this, and takes it down.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import identity_api

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "legacy-hashes.json"
TOKEN = os.environ.get("ORO_IDENTITY_TOKEN", "")

# Filled by _import_every_case before any check runs. Maps a fixture name to
# the login the member was imported under, so every check reads a member whose
# hash is known and whose password is known.
# Every run makes its own logins, because the module docstring tells a reader
# to point this at a stack that is already up and doing that twice with fixed
# names fails on accounts this suite created itself.
RUN = os.environ.get("ORO_IDENTITY_RUN", str(os.getpid()))

LOGINS: dict[str, str] = {}
CASES: dict[str, dict] = {}
# Every hash the service would not take, by fixture name. Empty is the answer
# the migration needs; anything in it is a member who cannot sign in.
REFUSED: list[str] = []


def _load() -> dict:
    return json.loads(FIXTURES.read_text())


def _import_every_case() -> None:
    """Import all of them first, and report which the service refused.

    Phase 2 asks for every hash the import refuses to be listed rather than
    counted, because a refusal is a member who cannot sign in and somebody has
    to decide what happens to them.
    """
    for case in _load()["cases"]:
        login = f"{case['name'].replace('_', '-')}-{RUN}@fixture.invalid"
        answer = identity_api.import_member(login, case["hash"], TOKEN)
        if answer.status != 200:
            REFUSED.append(f"{case['name']}: {answer.status} {answer.message()}")
            continue
        LOGINS[case["name"]] = login
        CASES[case["name"]] = case


def _signs_in(name: str, password: str | None = None):
    case = CASES[name]
    return identity_api.sign_in(LOGINS[name],
                                case["password"] if password is None else password,
                                TOKEN)


# --------------------------------------------------------------------------
# The fixture itself. If these fail, the rest is measuring the wrong thing.

def test_every_fixture_hash_is_in_the_legacy_format():
    for case in _load()["cases"]:
        parts = case["hash"].split("$")
        assert parts[1] == "2a", f"{case['name']} is not a 2a hash: {case['hash'][:7]}"
        assert parts[2] == "10", f"{case['name']} is not cost 10: {case['hash'][:7]}"
        assert len(parts[3]) == 53, f"{case['name']} has the wrong salt and digest length"


def test_the_fixture_covers_every_case_a_check_below_reads():
    """All of them, not only the four phase 2 names.

    A case removed from the fixture would otherwise turn the check that reads
    it into a KeyError with nothing saying which file to look in.
    """
    names = {case["name"] for case in _load()["cases"]}
    for wanted in ("ordinary", "minimum", "non_ascii", "trailing_space",
                   "bytes_71", "bytes_72", "bytes_73", "japanese_27"):
        assert wanted in names, (
            f"the fixture has no {wanted} case, and a check below reads it. "
            "Regenerate it with tools/identity/tests/generate_hashes.sh")


def test_no_hash_was_refused_by_the_import():
    assert REFUSED == [], "the import refused: " + "; ".join(REFUSED)


# --------------------------------------------------------------------------
# The passwords that work, which is most of them.

def test_an_ordinary_password_signs_in():
    assert _signs_in("ordinary").status == 201


def test_the_shortest_accepted_password_signs_in():
    assert _signs_in("minimum").status == 201


def test_a_password_with_non_ascii_characters_signs_in():
    answer = _signs_in("non_ascii")
    assert answer.status == 201, answer.message()


def test_a_trailing_space_signs_in():
    assert _signs_in("trailing_space").status == 201


def test_seventy_one_bytes_signs_in():
    assert _signs_in("bytes_71").status == 201


def test_seventy_two_bytes_signs_in():
    assert _signs_in("bytes_72").status == 201


# --------------------------------------------------------------------------
# The refusals. A verifier that accepts everything proves nothing.

def test_the_wrong_password_is_refused():
    answer = _signs_in("ordinary", "not the password")
    assert answer.status == 400, answer.status
    assert "Password is invalid" in answer.message(), answer.message()


def test_one_members_password_does_not_open_another_members_account():
    """The refusal a wrong password check cannot make.

    Presenting a string that belongs to nobody proves only that the verifier
    refuses nonsense. An import that paired the right login with the wrong hash
    would pass every other check on this page.
    """
    answer = _signs_in("ordinary", CASES["minimum"]["password"])
    assert answer.status == 400, (
        "a second member's password opened this account, so the import is not "
        "keeping hashes with the members they belong to")


def test_a_trailing_space_is_part_of_the_password():
    answer = _signs_in("trailing_space", "trailing space")
    assert answer.status == 400, \
        "a password stripped of its trailing space opened the account"


# --------------------------------------------------------------------------
# The finding. See tools/identity/README.md, and HANDOFF.md section 7.

def test_seventy_three_bytes_cannot_sign_in():
    answer = _signs_in("bytes_73")
    assert answer.status not in (200, 201), (
        "a password of 73 bytes signed in. That would be an improvement, and "
        "tools/identity/README.md and HANDOFF.md section 7 are then out of date")


def test_a_short_looking_japanese_passphrase_cannot_sign_in():
    answer = _signs_in("japanese_27")
    assert answer.status not in (200, 201), (
        "81 bytes in 27 characters signed in. See the note on the check above")


def test_the_refusal_over_seventy_two_bytes_is_not_a_credential_failure():
    """It comes back as a server error, and that is the part that costs.

    A member reading "wrong password" tries again or resets it. A member
    reading that something went wrong reports an outage, and whoever picks that
    up has no reason to suspect the password's length.

    The status code is deliberately not asserted. What a person experiences is
    the shape of the failure, and pinning 500 would turn red on exactly the
    improvement the README asks somebody to go and get.
    """
    answer = _signs_in("bytes_73")
    said = answer.message()
    assert said, (
        "the refusal carried no message at all, so this check read nothing. "
        "Answer.message() reads the 'message' key and the response had none")
    assert "Password is invalid" not in said, (
        "this now reads as a wrong password, which is the improvement "
        "tools/identity/README.md asks for. Update that file and this check")


# --------------------------------------------------------------------------
# The token the API layer will have to verify on every request.

def test_an_access_token_lasts_ten_minutes():
    """Ten minutes, per docs/plan/api-design.md section 2.

    The trap this guards: the variable that reads as though it sets this,
    ZITADEL_OIDC_DEFAULTACCESSTOKENLIFETIME, does not. It is the fallback for
    an instance with no setting of its own, and setup gives this instance one.
    Setting only that variable and measuring a real token gave 43200 seconds.
    """
    answer = identity_api.machine_token(f"token-lifetime-probe-{RUN}", TOKEN)
    assert answer.status == 200, answer.message()
    seconds = identity_api.lifetime_of(answer.body["access_token"])
    assert seconds == 600, (
        f"an access token lasts {seconds} seconds, not 600. Roles are read per "
        "request rather than from a claim, and a long token spends that")


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
    return 1 if failed else 0


if __name__ == "__main__":
    if not TOKEN:
        print("No ORO_IDENTITY_TOKEN, so nothing was checked. "
              "tools/identity/tests/run.sh reads one out of a stack it starts.",
              file=sys.stderr)
        sys.exit(1)
    _import_every_case()
    sys.exit(_run())
