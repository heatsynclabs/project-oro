#!/usr/bin/env python3
"""Point the identity service at a mail server, and turn it on.

Three things a member does end in a code that arrives by mail: registering,
asking for a forgotten password, and changing their address. Without a server
every one of them is a screen asking for a code that can never come. Measured on
2026-08-31 against 4.17.1: registering creates the account, the screens then show
Activate User, and that screen carries a required code field, Next, and Resend
Code, and no way past.

On a laptop the server is the catcher compose.development.yaml runs, which holds
mail rather than delivering it. On a deployment it is whatever the lab uses, and
docs/runbooks/deploy-beside-the-legacy-system.md is where that gets decided.

Configuring is not enough on its own, and that is the half worth knowing. A
provider is created inactive: the first one written here was
SMTP_CONFIG_INACTIVE, a registration sent nothing, and the mail catcher held
nothing. Activated, the same registration put an Initialize User message in it.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import api      # noqa: E402, after the path insert above

from api import Refused      # noqa: E402, raised below

PROVIDERS = "/admin/v1/smtp"

# What the lab is, in the from line of every message the identity service sends.
# Not a mailbox anybody reads: a reply to a verification code has nowhere to go.
SENDER = "no-reply@heatsynclabs.org"
SENDER_NAME = "HeatSync Labs"


def held(token: str) -> list:
    """Every mail provider this instance has, which is normally none or one."""
    answer = api.call(PROVIDERS + "/_search", {}, token)
    if answer.status != 200:
        raise Refused(f"the mail providers could not be read: {answer.status} "
                      f"{answer.message()}. Nothing was changed.")
    return answer.body.get("result") or []


def matching(providers: list, host: str) -> dict | None:
    for provider in providers:
        if provider.get("host") == host:
            return provider
    return None


def point_at(host: str, token: str) -> None:
    """Make `host` the server this instance sends through, and activate it.

    Idempotent. A second run with the same host reports it already set rather
    than stacking a second provider beside the first, because a provider list
    with two entries in it is a question nobody wants at 2am.
    """
    providers = held(token)
    already = matching(providers, host)
    if already is None:
        answer = api.call(PROVIDERS, {
            "senderAddress": SENDER,
            "senderName": SENDER_NAME,
            "host": host,
            "user": "",
            "password": "",
            # The catcher takes plain SMTP on the compose network and nothing
            # leaves the machine. A deployment sending over the internet wants
            # this on, and the runbook step says so where the host is chosen.
            "tls": False,
        }, token)
        if answer.status != 200:
            raise Refused(f"the mail server could not be set: {answer.status} "
                          f"{answer.message()}. Registering and a forgotten "
                          "password both end in a code that cannot be sent "
                          "until it is.")
        already = {"id": answer.body["id"], "state": "SMTP_CONFIG_INACTIVE"}
        print(f"mail: sending through {host}")
    else:
        print(f"mail: already sending through {host}")

    if already.get("state") == "SMTP_CONFIG_ACTIVE":
        return
    turned_on = api.call(f"{PROVIDERS}/{already['id']}/_activate", {}, token)
    if turned_on.status != 200 and "not been changed" not in turned_on.message():
        raise Refused(f"the mail server was set and could not be activated: "
                      f"{turned_on.status} {turned_on.message()}. A provider "
                      "that is set and not activated sends nothing, and the "
                      "screens still ask for a code.")
    print("mail: activated")


def say_there_is_none() -> None:
    """What a run with no mail server has to tell the person who ran it."""
    print("mail: no server given, so nothing can send a code. Registering, a "
          "forgotten password and a changed address all stop at a screen "
          "asking for one. Pass --mail-host to fix that.")
