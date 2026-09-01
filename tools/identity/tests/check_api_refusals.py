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
import ssl
import sys
import urllib.error
import urllib.request

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


def a_service_that_is_not_there_is_a_refusal_and_not_a_traceback():
    """Rule 7 over the shape a laptop is nearly always in.

    ORO_IDENTITY_URL defaults to https://id.<ORO_HOSTNAME>, which on a laptop
    is https://id.localhost and resolves nowhere. Before api._send caught it,
    make bootstrap-admins ended in a urllib traceback naming neither the URL it
    tried nor the setting that fixes it.
    """
    was = api.BASE
    api.BASE = "http://localhost:1"      # nothing has ever listened here
    try:
        api.get("/admin/v1/policies/login", "any-token")
    except api.Refused as refused:
        message = str(refused)
    except Exception as raw:             # noqa: BLE001
        raise AssertionError(
            f"a service that is not there raised {type(raw).__name__} rather "
            f"than a refusal a command can print: {raw}")
    else:
        raise AssertionError("an unreachable service answered")
    finally:
        api.BASE = was

    assert "http://localhost:1" in message, (
        "the refusal does not name the URL it tried: " + message)
    assert "ORO_IDENTITY_URL" in message, (
        "the refusal does not name the setting that fixes it: " + message)
    assert "Nothing was read or changed" in message, message


def a_certificate_nothing_trusts_names_the_certificate():
    """The shape a deployment is in, and it used to be told to check a hostname.

    ORO_TLS=internal means Caddy issued the certificate from its own authority,
    so every Python command here stops on it while the curl beside them passes
    -k. Measured on 2026-08-31 against a deployment shaped stack: configure.py
    printed CERTIFICATE_VERIFY_FAILED and then advice about ORO_HOSTNAME and the
    stack being up, and both of those were already right.

    The reason object is the one urlopen raises, carrying the text that
    measurement printed, because there is no certificate here to fail against
    and this check needs nothing running.
    """
    was = api.BASE
    api.BASE = "https://id.oro.example.invalid:8443"
    verify_failed = urllib.error.URLError(ssl.SSLCertVerificationError(
        1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
           "unable to get local issuer certificate (_ssl.c:1032)"))

    def refuse(request, *rest, **named):
        raise verify_failed

    original = urllib.request.urlopen
    urllib.request.urlopen = refuse
    try:
        api.get("/admin/v1/policies/login", "any-token")
    except api.Refused as refused:
        message = str(refused)
    else:
        raise AssertionError("an untrusted certificate answered")
    finally:
        urllib.request.urlopen = original
        api.BASE = was

    assert "SSL_CERT_FILE" in message, (
        "the refusal does not name what fixes it: " + message)
    assert "deploy-beside-the-legacy-system.md" in message, (
        "the refusal does not name where the commands are: " + message)
    assert "ORO_HOSTNAME" not in message, (
        "the refusal still sends the reader to check the hostname, which is "
        "not what went wrong: " + message)


CHECKS = [
    ("a search that found nothing is empty", a_search_that_found_nothing_is_empty),
    ("a search that found something returns it", a_search_that_found_something_returns_it),
    ("the refusal is catchable by a check suite", the_refusal_is_catchable_by_a_check_suite),
    ("a revoked token is a refusal, not an empty result", a_revoked_token_is_a_refusal_and_not_an_empty_result),
    ("the refusal says what happened", the_refusal_says_what_happened_and_what_to_do),
    ("a server fault is refused too", a_server_fault_is_refused_too),
    ("a service that is not there is a refusal", a_service_that_is_not_there_is_a_refusal_and_not_a_traceback),
    ("a certificate nothing trusts names the certificate", a_certificate_nothing_trusts_names_the_certificate),
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
