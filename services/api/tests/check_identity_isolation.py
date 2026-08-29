#!/usr/bin/env python3
"""Who the service thinks you are, and how long that lasts.

The check this file exists for is the last one. Everything above it is the
setting that makes the last one readable.

db/migrations/004_security.sql spends four lines of hint text on the
difference between SET and SET LOCAL, because a plain SET survives the
transaction and a pooled connection is handed to the next request. The suite
runs the service with a pool of exactly one connection, so every request here
lands on the same connection and a leak has nowhere to hide.
"""
import os
import subprocess
import sys

from harness import IDA, STRANGER_KEY, WREN, fetch, mint, run

SERVICE_CONTAINER = os.environ["ORO_API_TEST_CONTAINER"]


def test_an_anonymous_caller_is_refused_everywhere():
    for path in ("/me", "/members", "/members/" + WREN):
        refused = fetch(path)
        assert refused.status == 401, f"{path} answered {refused.status}"
        assert refused.headers["Content-Type"].startswith(
            "application/problem+json"), path
        problem = refused.json()
        assert problem["title"] == "Sign in first", problem
        assert problem["type"].endswith("/unauthenticated"), problem


def test_the_database_is_what_refuses_an_anonymous_caller():
    """Not a check in the service, which is where it would be easiest to put.

    There is no `if there is no token then refuse` anywhere in app/. A caller
    with no usable token reaches the database with no identity set and
    current_member_id() raises. The service logs that refusal in the database's
    own words, and this reads the log back.
    """
    fetch("/me")
    printed = subprocess.run(["docker", "logs", SERVICE_CONTAINER],
                             capture_output=True, text=True, check=False)
    log = printed.stdout + printed.stderr
    wanted = "refused by the database: No identity set on this transaction"
    assert wanted in log, log[-2000:]


def test_a_token_signed_by_somebody_else_is_refused():
    forged = mint("sub-c-wren", key_path=STRANGER_KEY)
    refused = fetch("/me", forged)
    assert refused.status == 401, refused.body
    assert refused.json()["title"] == "Sign in first", refused.body


def test_a_token_minted_for_another_audience_is_refused():
    refused = fetch("/me", mint("sub-c-wren", audience="somebody-elses-api"))
    assert refused.status == 401, refused.body


def test_a_token_from_another_issuer_is_refused():
    refused = fetch("/me", mint("sub-c-wren", issuer="http://not.the.lab"))
    assert refused.status == 401, refused.body


def test_a_verified_token_with_no_member_row_says_so():
    refused = fetch("/me", mint("sub-c-nobody-at-all"))
    assert refused.status == 401, refused.body
    problem = refused.json()
    assert problem["type"].endswith("/no-member-record"), problem
    assert "link your record" in problem["detail"], problem


def test_an_identity_does_not_survive_on_a_pooled_connection():
    """Three requests, one connection, three different callers.

    With `SET LOCAL` the setting dies with the transaction and each request
    starts from nothing. With a plain `SET` the first request's subject is
    still on the connection when the second arrives, so the anonymous call in
    the middle comes back 200 carrying Wren's record, and this goes red.
    """
    first = fetch("/me", mint("sub-c-wren"))
    assert first.status == 200, first.body
    assert first.json()["id"] == WREN, first.body

    between = fetch("/me")
    assert between.status == 401, (
        "an anonymous request on the same connection was answered "
        f"{between.status}: {between.body}")

    second = fetch("/me", mint("sub-c-ida"))
    assert second.status == 200, second.body
    assert second.json()["id"] == IDA, (
        "the second caller was handed the first caller's record: "
        + second.body)


sys.exit(run(dict(globals()), "identity isolation"))
