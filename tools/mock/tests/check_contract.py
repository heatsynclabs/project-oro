#!/usr/bin/env python3
"""Prove the mock server is serving docs/api/members-v1.yaml.

Every check here calls the mock over HTTP. None of them read its
configuration, because a configuration that looks right and a server that
answers right are different claims.

Paths carry no /v1 prefix. The document declares its server as
https://api.heatsynclabs.org/v1 and the mock mounts the paths at its own root,
so a client sets its base URL to the mock and gets the same paths underneath.

Run it with the mock already listening:

    ORO_MOCK_URL=http://127.0.0.1:4010 python3 tools/mock/tests/check_contract.py

tools/mock/tests/run.sh starts one, runs this, and takes it down again.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ORO_MOCK_URL", "http://127.0.0.1:4010")

# Any string. The mock never validates a signature, and it must not: the
# identity provider is not deployed, which is the whole reason the portal is
# being built against a mock first.
TOKEN = "not-a-real-token"

# A member id that is not in any seed file and never will be. The mock invents
# its own answer whatever this is.
SOME_MEMBER = "3f8b0c22-0000-4000-8000-000000000001"


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def content_type(self):
        return self.headers.get("Content-Type", "")

    def json(self):
        return json.loads(self.body)


def call(method, path, headers=None, body=None):
    # Both media types, because a refusal is served as application/problem+json
    # and a client that asks only for application/json gets told there is no
    # representation it can read.
    sent = {"Accept": "application/json, application/problem+json"}
    if headers:
        sent.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        sent["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=data, headers=sent, method=method)
    try:
        with urllib.request.urlopen(request) as answer:
            return Response(answer.status, answer.headers, answer.read().decode())
    except urllib.error.HTTPError as refused:
        return Response(refused.code, refused.headers, refused.read().decode())


def signed_in(method, path, body=None):
    return call(method, path, {"Authorization": "Bearer " + TOKEN}, body)


# ------------------------------------------------- it answers the real paths

def test_the_mock_answers_get_me():
    answer = signed_in("GET", "/me")
    assert answer.status == 200, f"got {answer.status}: {answer.body[:200]}"
    assert "id" in answer.json(), answer.body[:200]


def test_the_document_server_prefix_is_not_part_of_the_mock_path():
    """Pinned so that a later mock version honouring the server path fails here
    rather than quietly 404ing every call a portal makes."""
    answer = signed_in("GET", "/v1/me")
    assert answer.status == 404, f"got {answer.status}: {answer.body[:200]}"


def test_a_member_carries_the_fields_this_document_declares():
    """The point of the mock is that the portal can be finished against it, so
    the shape has to be this contract's shape and not a stub."""
    member = signed_in("GET", "/me").json()
    for field in ("listed_in_directory", "email_visible", "phone_visible",
                  "emergency_phone", "current_skills", "paid_through", "standing"):
        assert field in member, f"{field} missing from {sorted(member)}"


def test_the_directory_is_a_list_of_the_same_member_object():
    answer = signed_in("GET", "/members")
    assert answer.status == 200, f"got {answer.status}: {answer.body[:200]}"
    listed = answer.json()
    assert isinstance(listed, list) and listed, answer.body[:200]
    assert "id" in listed[0], answer.body[:200]


def test_waiver_status_answers_a_boolean_and_a_date():
    answer = signed_in("GET", "/waiver-status?member_id=" + SOME_MEMBER)
    assert answer.status == 200, f"got {answer.status}: {answer.body[:200]}"
    assert "has_valid_waiver" in answer.json(), answer.body[:200]


def test_issuing_a_card_answers_201_with_a_controller_slot():
    answer = signed_in("POST", "/admin/cards", {
        "member_id": SOME_MEMBER,
        "tag_number": "0000C4D9",
        "label": "front desk spare",
    })
    assert answer.status == 201, f"got {answer.status}: {answer.body[:200]}"
    assert "controller_slot" in answer.json(), answer.body[:200]


def test_the_public_endpoint_is_served_from_the_members_hostname_path():
    """space_api.json is declared with its own server and no /v1 prefix,
    because the address predates this project and is a contract."""
    answer = call("GET", "/space_api.json")
    assert answer.status == 200, f"got {answer.status}: {answer.body[:200]}"


# ------------------------------------------- it is serving THIS document

def test_card_eligibility_answers_this_documents_own_example():
    """The date and the tenure sentence appear in members-v1.yaml and nowhere
    else, so an answer carrying them came from this file."""
    answer = signed_in("GET", "/me/card-eligibility")
    assert answer.status == 200, f"got {answer.status}: {answer.body[:200]}"
    eligibility = answer.json()
    assert eligibility["eligible_on"] == "2026-10-14", answer.body[:300]
    rules = [requirement["rule"] for requirement in eligibility["requirements"]]
    assert "tenure" in rules, answer.body[:300]


BROKEN_CYCLE = {"$ref": None}


def test_a_reference_cycle_is_what_the_mock_leaves_null():
    """Pinned because a portal has to know which fields it must stub, and
    because the rule is easy to state wrongly. The mock stops where a reference
    closes a cycle, not where a reference crosses a schema boundary. ADR 0002
    carries the two schema reproduction."""
    member = signed_in("GET", "/me").json()
    assert member["oriented_by"] == BROKEN_CYCLE, member["oriented_by"]
    granted_by = member["roles"][0]["granted_by"]
    assert granted_by == BROKEN_CYCLE, f"granted_by came back as {granted_by}"


def test_a_reference_that_closes_no_cycle_comes_back_whole():
    """Card to Member closes nothing, so the mock renders the whole member and
    only the cycles inside it are cut. Without this the check above would still
    pass if a later version started nulling every reference."""
    card = signed_in("GET", "/me/cards").json()[0]
    revoked_by = card["revoked_by"]
    assert revoked_by.get("id"), f"revoked_by came back as {revoked_by}"
    assert revoked_by["oriented_by"] == BROKEN_CYCLE, revoked_by["oriented_by"]


def test_a_path_this_document_does_not_declare_is_not_served():
    answer = signed_in("GET", "/tool-interlocks")
    assert answer.status == 404, f"got {answer.status}: {answer.body[:200]}"


# ----------------------------------------------------- it refuses, on purpose

def test_a_request_with_no_token_is_refused_as_a_problem_detail():
    answer = call("GET", "/me")
    assert answer.status == 401, f"got {answer.status}: {answer.body[:200]}"
    kind = answer.content_type()
    assert "application/problem+json" in kind, f"content type was {kind!r}"


def test_the_self_approval_refusal_can_be_asked_for():
    """A portal has to be buildable against the failure path, and this is the
    refusal the two approver rule exists to produce."""
    answer = call("POST", "/admin/approvals/88/approve", {
        "Authorization": "Bearer " + TOKEN,
        "Prefer": "code=409, example=selfApproval",
    })
    assert answer.status == 409, f"got {answer.status}: {answer.body[:200]}"
    problem = answer.json()
    assert problem["type"].endswith("/errors/self-approval"), answer.body[:300]
    assert problem["detail"].startswith("Admin access changes need a second admin"), \
        answer.body[:300]


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
    sys.exit(_run())
