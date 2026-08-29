#!/usr/bin/env python3
"""Prove a refused search is reported as a refusal and not as an empty result.

A Zitadel search answers with a result list. A refusal answers with a code and
a message and no list at all, so reading a list out of it yields an empty one,
and empty is exactly what a search that legitimately found nothing returns.
A caller cannot tell those apart, and configure.py is a caller: told that no
project exists, it goes on to create the one that is already there and reports
the failure against creating a project when the truth is that its token is not
valid. That was measured on 2026-08-28 by revoking the bootstrap token on a
throwaway stack and running configure.py, which printed
"could not create the project: 401".

Needs no identity service. Everything here is a stub, because the behaviour
under test is what api.search does with an answer, not what the service sends.

    python3 tools/identity/tests/check_api_refusals.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import api                       # noqa: E402, after the path insert above


def _answering(status: int, body: dict):
    """Stand in for api.call, which is the only thing api.search reaches out to."""
    def call(path: str, request_body: dict, token: str, method: str = "POST"):
        return api.Answer(status, body)
    return call


def _with_stub(status: int, body: dict):
    original = api.call
    api.call = _answering(status, body)
    try:
        return api.search("/management/v1/projects/_search", "any-token"), None
    except api.Refused as refused:
        return None, str(refused)
    finally:
        api.call = original


def a_search_that_found_nothing_is_empty():
    found, refusal = _with_stub(200, {"details": {"totalResult": "0"}})
    assert refusal is None, f"a 200 was treated as a refusal: {refusal}"
    assert found == [], f"expected no results, got {found!r}"


def a_search_that_found_something_returns_it():
    found, refusal = _with_stub(200, {"result": [{"name": "Project ORO"}]})
    assert refusal is None, f"a 200 was treated as a refusal: {refusal}"
    assert found == [{"name": "Project ORO"}], f"got {found!r}"


def the_refusal_is_catchable_by_a_check_suite():
    """SystemExit would slip past `except Exception` and end a run with no summary."""
    assert issubclass(api.Refused, Exception), "Refused is not an Exception"
    assert not issubclass(api.Refused, SystemExit), (
        "Refused derives from SystemExit, so a check suite cannot catch it and one "
        "refusal would end the run with no FAIL line")


def a_revoked_token_is_a_refusal_and_not_an_empty_result():
    found, refusal = _with_stub(401, {"code": 16, "message": "Errors.Token.Invalid (AUTH-7fs1e)"})
    assert found is None, f"a 401 came back as {found!r}, which reads as nothing found"
    assert refusal is not None, "a 401 was not refused"


def the_refusal_says_what_happened_and_what_to_do():
    _, refusal = _with_stub(401, {"code": 16, "message": "Errors.Token.Invalid (AUTH-7fs1e)"})
    assert "401" in refusal, f"the status is not in the message: {refusal}"
    assert "Errors.Token.Invalid" in refusal, f"the service's own words are gone: {refusal}"
    assert "token" in refusal.lower(), f"nothing tells the reader what to look at: {refusal}"


def a_server_fault_is_refused_too():
    found, refusal = _with_stub(500, {"code": 13, "message": "An internal error occurred"})
    assert found is None, f"a 500 came back as {found!r}"
    assert "500" in refusal, f"the status is not in the message: {refusal}"


CHECKS = [
    ("a search that found nothing is empty", a_search_that_found_nothing_is_empty),
    ("a search that found something returns it", a_search_that_found_something_returns_it),
    ("the refusal is catchable by a check suite", the_refusal_is_catchable_by_a_check_suite),
    ("a revoked token is a refusal, not an empty result", a_revoked_token_is_a_refusal_and_not_an_empty_result),
    ("the refusal says what happened", the_refusal_says_what_happened_and_what_to_do),
    ("a server fault is refused too", a_server_fault_is_refused_too),
]


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
