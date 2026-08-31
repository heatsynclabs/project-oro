#!/usr/bin/env python3
"""Prove the mail step will not take a working mail server offline.

tools/identity/mail.py can only ever write a provider with no username, no
password and TLS off, which is a catcher on a compose network. A deployment
relay is configured by hand. The two meet on the day somebody runs
make identity-configure on a deployment with the shipped ORO_MAIL_HOST still in
.env, and before this file existed that deactivated the relay, activated a
provider pointing at a host that does not exist there, and printed
"mail: activated" on the way out. Every code stopped arriving and nothing said
so.

    ORO_IDENTITY_URL=... ORO_IDENTITY_TOKEN=... \\
      python3 tools/identity/tests/check_mail.py

tools/identity/tests/run.sh starts a stack and runs this. Nothing is sent: a
provider is configuration, and writing one opens no socket, so this needs no
mail server running. Every check reads the provider list back from the service
rather than trusting what a call returned, and this file removes every provider
it made so the rest of the suite sees the instance it would have seen.
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import api       # noqa: E402, after the path insert above
import mail      # noqa: E402

TOKEN = os.environ.get("ORO_IDENTITY_TOKEN", "")

# The value .env.example ships and compose.development.yaml runs a catcher for.
THE_CATCHER = "mail:1025"

# A host with no address anywhere, per RFC 2606, so a check that somehow got as
# far as sending could not reach something real.
A_HAND_CONFIGURED_RELAY = "relay.example.invalid:587"

MADE_BY_THIS_FILE: list = []


def _sending() -> dict | None:
    return mail.sending(mail.held(TOKEN))


def _point_at(host: str) -> None:
    mail.point_at(host, TOKEN)
    for provider in mail.held(TOKEN):
        if provider["id"] not in MADE_BY_THIS_FILE:
            MADE_BY_THIS_FILE.append(provider["id"])


def test_the_catcher_is_set_and_activated_in_one_step():
    """A provider is created inactive, which is the half that cost a day.

    The first one written here was SMTP_CONFIG_INACTIVE, a registration sent
    nothing, and the catcher held nothing. Configuring is not enough.
    """
    assert _sending() is None, (
        "something is already sending on this instance, so what this file "
        "would prove is not what it set out to prove")
    _point_at(THE_CATCHER)
    active = _sending()
    assert active is not None, "the provider was written and never activated"
    assert active["host"] == THE_CATCHER, f"the active provider is {active['host']}"


def test_a_second_run_against_the_same_host_changes_nothing():
    before = _sending()
    _point_at(THE_CATCHER)
    after = _sending()
    assert after["id"] == before["id"], (
        f"the active provider changed from {before['id']} to {after['id']} on a "
        "run asked for the host that was already sending")
    assert len(mail.held(TOKEN)) == 1, (
        f"a second run stacked another provider beside the first: {mail.held(TOKEN)}")


def test_a_different_host_is_refused_while_another_is_sending():
    """The whole point. The relay stays active and the refusal says what to do."""
    relay = _plant_a_relay()
    try:
        mail.point_at(THE_CATCHER, TOKEN)
    except api.Refused as refused:
        message = str(refused)
    else:
        raise AssertionError(
            "point_at was asked for a host other than the one sending and did "
            "it, which deactivates the relay and sends nothing from then on")

    assert A_HAND_CONFIGURED_RELAY in message, message
    assert "Nothing was changed" in message, message
    assert "ORO_MAIL_HOST" in message, (
        "the refusal has to name the setting somebody has to change: " + message)

    still = _sending()
    assert still["id"] == relay["id"], (
        f"the refusal still left {still['host']} sending instead of the relay")


def test_the_relay_is_reported_rather_than_rewritten_when_it_is_the_host_asked_for():
    """A deployment that did set ORO_MAIL_HOST to its relay gets a no-op.

    Not a rewrite. What this step writes carries no username, so rewriting the
    relay in place would strip the credentials it authenticates with and the
    host would go on looking correct in every list.
    """
    before = _sending()
    assert before["host"] == A_HAND_CONFIGURED_RELAY, "the check above did not run"
    mail.point_at(A_HAND_CONFIGURED_RELAY, TOKEN)
    after = _sending()
    assert after["id"] == before["id"], "the relay was replaced by a rewritten copy"
    assert after.get("user") == "members", (
        "the relay's credentials were overwritten with the empty ones this "
        f"step writes: {after}")


def _plant_a_relay() -> dict:
    """An active provider this step did not write, which is the deployment case."""
    made = api.call(mail.PROVIDERS, {
        "senderAddress": "members@example.invalid",
        "senderName": "A Relay Somebody Configured",
        "host": A_HAND_CONFIGURED_RELAY,
        "user": "members",
        # Invented, for a host RFC 2606 reserves so that it cannot exist. Rule
        # 13: nothing here resembles a credential anybody holds.
        "password": "throwaway-nothing-authenticates-with-this",
        "tls": True,
    }, TOKEN)
    assert made.status == 200, f"planting a relay was refused: {made.status} {made.message()}"
    MADE_BY_THIS_FILE.append(made.body["id"])
    turned_on = api.call(f"{mail.PROVIDERS}/{made.body['id']}/_activate", {}, TOKEN)
    assert turned_on.status == 200, f"activating the planted relay was refused: {turned_on.status}"
    return made.body


def _leave_the_instance_as_it_was_found() -> None:
    for planted in MADE_BY_THIS_FILE:
        api.call(f"{mail.PROVIDERS}/{planted}", {}, TOKEN, method="DELETE")


# In this order, because each check moves the instance into the state the next
# one reads. Sorted names would ask for the refusal before a relay exists.
ORDER = ("test_the_catcher_is_set_and_activated_in_one_step",
         "test_a_second_run_against_the_same_host_changes_nothing",
         "test_a_different_host_is_refused_while_another_is_sending",
         "test_the_relay_is_reported_rather_than_rewritten_when_it_is_"
         "the_host_asked_for")


def _run() -> int:
    tests = [globals()[name] for name in ORDER]
    failures = 0
    try:
        for test in tests:
            try:
                test()
                print(f"PASS {test.__name__}")
            except Exception as broken:
                failures += 1
                print(f"FAIL {test.__name__}: {broken}")
    finally:
        _leave_the_instance_as_it_was_found()
    print(f"\n{len(tests) - failures}/{len(tests)} checks")
    return 1 if failures else 0


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("No ORO_IDENTITY_TOKEN. tools/identity/tests/run.sh sets one.")
    sys.exit(_run())
