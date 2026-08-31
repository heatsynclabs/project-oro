#!/usr/bin/env python3
"""Point the identity service at a mail server, and turn it on.

Three things a member does end in a code that arrives by mail: registering,
asking for a forgotten password, and changing their address. Without a server
every one of them is a screen asking for a code that can never come. Measured on
2026-08-31 against 4.17.1: registering creates the account, the screens then show
Activate User, and that screen carries a required code field, Next, and Resend
Code, and no way past.

On a laptop the server is the catcher compose.development.yaml runs, which holds
mail rather than delivering it. That is the only thing this file can configure:
it writes a provider with no username, no password and TLS off. A deployment
relay is set up by hand once, per step 7 of
docs/runbooks/deploy-beside-the-legacy-system.md, and point_at refuses to touch
an instance that is already sending through a host it was not asked for.

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


def sending(providers: list) -> dict | None:
    """The one provider mail actually leaves through, if there is one.

    Activating a provider deactivates whichever one was active, which the
    identity service does not warn about and which is the whole reason the
    refusal below exists.
    """
    for provider in providers:
        if provider.get("state") == "SMTP_CONFIG_ACTIVE":
            return provider
    return None


def point_at(host: str, token: str) -> None:
    """Make `host` the server this instance sends through, and activate it.

    Only ever the catcher. What this can build is a provider with no username,
    no password and TLS off, which is a mail catcher on a compose network and
    nothing that would be accepted by a real relay. A lab relay is configured by
    hand, once, per step 7 of docs/runbooks/deploy-beside-the-legacy-system.md.

    So this refuses rather than writes when the instance is already sending
    through a host it was not asked for. Activating deactivates the one that was
    active, measured on 2026-08-31 against 4.17.1, so the shipped default of
    ORO_MAIL_HOST=mail:1025 reaching a deployment would otherwise take the lab
    relay offline, point mail at a host that does not exist there, and print
    "mail: activated" on the way out.

    Idempotent. A second run against the host already sending reports it rather
    than stacking a second provider beside the first, because a provider list
    with two entries in it is a question nobody wants at 2am.
    """
    providers = held(token)
    active = sending(providers)
    if active is not None and active.get("host") != host:
        raise Refused(
            f"this instance is already sending through {active.get('host')}, "
            f"and was asked to send through {host} instead. Nothing was "
            "changed. Activating a provider deactivates the one that was "
            "active, and what this step can build carries no username, no "
            "password and no TLS, so it would replace a working relay with "
            "one that cannot send. Set ORO_MAIL_HOST to the host already "
            "there, or leave --mail-host off and keep the relay somebody "
            "configured by hand.")
    if active is not None:
        print(f"mail: already sending through {host}")
        return

    already = matching(providers, host)
    if already is None:
        already = write_the_catcher(host, token)
        print(f"mail: sending through {host}")
    else:
        print(f"mail: set for {host} and not sending, which is the state a "
              "provider is created in")
    activate(already["id"], token)


def write_the_catcher(host: str, token: str) -> dict:
    """Register the provider, which is not yet sending. activate does that."""
    answer = api.call(PROVIDERS, {
        "senderAddress": SENDER,
        "senderName": SENDER_NAME,
        "host": host,
        "user": "",
        "password": "",
        # The catcher takes plain SMTP on the compose network and nothing
        # leaves the machine. Nothing sending over the internet would accept
        # this, which is why point_at refuses rather than taking a flag: a
        # relay is set up by hand and this stays away from it.
        "tls": False,
    }, token)
    if answer.status != 200:
        raise Refused(f"the mail server could not be set: {answer.status} "
                      f"{answer.message()}. Registering and a forgotten "
                      "password both end in a code that cannot be sent "
                      "until it is.")
    return {"id": answer.body["id"]}


def activate(provider_id: str, token: str) -> None:
    """The half that was missed, and it cost a day.

    A provider is created SMTP_CONFIG_INACTIVE. The first one written here was
    left that way, a registration sent nothing, and the catcher held nothing.
    Activated, the same registration put an Initialize User message in it.
    """
    turned_on = api.call(f"{PROVIDERS}/{provider_id}/_activate", {}, token)
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
