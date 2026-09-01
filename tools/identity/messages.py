#!/usr/bin/env python3
"""What the identity service says in the message a new member gets.

The first thing anybody hears from this system is an email, and until this file
existed it was the vendor's: "This user was created in Zitadel. Use the username
... to login. Please click the button below to finish the initialization
process." Read off a running 4.17.1 instance on 2026-08-31 at
GET /management/v1/text/message/init/en, with `isDefault` true beside it.

A person who has just pressed Register on a HeatSync Labs page and then receives
that has been handed off to a company they have never heard of, at the one
moment they are being asked to trust the thing. branding.py fixes the colours
and the mark on the screens and cannot reach this, because the label policy
carries a logo and a palette and no words.

Its own file rather than a section of branding.py for the reason login_policy.py
is its own file: a palette and a sentence somebody reads are different subjects,
and the next person looking for the words should not have to read past three
asset uploads to find them.

Only the initialization message is written here. The others, a forgotten
password and a changed address among them, are left on the vendor's text because
nobody has drafted replacements, and rule 10 says a half written set is worse
than an honest one. Every one of them is the same shape when somebody does:
another entry in MESSAGES.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import api      # noqa: E402, after the path insert above

from api import Refused      # noqa: E402, raised below

# The organisation's copy rather than the instance default, which is the level
# branding.py already writes at. Both exist and both were read on 2026-08-31:
# /admin/v1/text/default/message/init/en carries the instance default and
# /management/v1/text/message/init/en carries the organisation's, and the
# organisation's is the one a member's message is built from. The organisation
# one is also the one that names the vendor: the instance default says "This
# user was created" and the organisation's says "created in Zitadel".
#
# The language is part of the path. English only, because the legacy members
# site is English only and a translation nobody can proofread is worse than
# none.
INIT = "/management/v1/text/message/init/en"

# The placeholders are Zitadel's, read from the example values in the image's
# own embedded ManagementServiceSetCustomInitMessageTextBody on 2026-08-31.
# {{.DisplayName}} is the greeting's, {{.PreferredLoginName}} is what the person
# signs in as, and {{.Code}} is what the Activate User screen asks for.
#
# No lab address and no founding date in here. Rule 11: numbers nobody checked
# do not ship, and nobody has checked either against a current source.
INIT_TEXT = {
    "title": "HeatSync Labs",
    "preHeader": "Finish setting up your account",
    "subject": "Finish setting up your HeatSync Labs account",
    "greeting": "Hello {{.DisplayName}},",
    "text": "Somebody asked to set up a HeatSync Labs members account for this "
            "address. Use the button below to choose a password and finish. "
            "Your sign in name is {{.PreferredLoginName}} and your code is "
            "{{.Code}}. If this was not you, ignore this message and nothing "
            "happens.",
    "buttonText": "Finish setting up",
}


def held(token: str) -> dict:
    """The initialization message as this organisation would send it now."""
    answer = api.get(INIT, token)
    if answer.status != 200:
        raise Refused(f"the message text could not be read: {answer.status} "
                      f"{answer.message()}. Nothing was changed, so the "
                      "message a new member gets is whatever it was.")
    return answer.body["customText"]


def is_ours(text: dict) -> bool:
    """Whether this organisation is sending the lab's words or the vendor's.

    Read off the subject rather than off `isDefault`, because `isDefault` says
    where the text came from and this asks what it says. A hand edited text
    that happens to match ours is ours, which is the answer that stops a second
    run rewriting it.
    """
    return all(text.get(field) == wanted
               for field, wanted in INIT_TEXT.items())


def apply_message_text(token: str) -> None:
    """Replace the vendor's initialization message with the lab's.

    Idempotent, and it reads before it writes for the same reason every other
    step here does: a configuration step people are afraid to run twice stops
    being run.
    """
    if is_ours(held(token)):
        print("message text: already the lab's words")
        return

    answer = api.call(INIT, INIT_TEXT, token, method="PUT")
    # The read above comes from a projection updated after the write, so a run
    # close behind another reads the old text and asks for a change that has
    # already happened. login_policy.open_self_registration reads the same
    # message the same way.
    if answer.status != 200 and "not been changed" in answer.message():
        print("message text: already the lab's words")
        return
    if answer.status != 200:
        raise Refused(f"the message text could not be set: {answer.status} "
                      f"{answer.message()}. Nothing else was changed. The "
                      "first message a new member gets still names the vendor "
                      "rather than the lab, which is confusing rather than "
                      "broken, so this is not a reason to stop the rest.")
    print("message text: the lab's words on the message a new member gets")
