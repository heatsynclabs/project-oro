"""The login policy, which is what the hosted sign in screens are built from.

tools/identity/configure.py applies this beside the clients and the branding,
so one idempotent step decides what a member is offered when they arrive. Its
own file rather than a section of api.py, which is calls to the identity
service and has no business holding a policy.

The Register button is the whole reason this exists. It is on by default, because
this site replaces one that has a sign up. It needs a mail server behind it: the
screens ask a new joiner for a code, and compose.development.yaml runs a catcher
for a laptop while a deployment points at the lab's own server.

Both directions are here, and a deployment can need either. An operator standing
up this stack with no mail server has to be able to close the sign up, because
the alternative is a person pressing Register and landing in a state no admin can
repair. Which one runs is a flag on configure.py and is never worked out from
whether mail was configured: deriving one setting from another is the mistake
ADR 0002 records.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import api      # noqa: E402, after the path insert above

from api import Refused      # noqa: E402, raised below

# Settings v2 reads this policy and has no setter for it: the 4.17.1 image's
# own embedded Settings Service document carries GET /v2/settings/login, and
# the only Set methods on zitadel.settings.v2.SettingsService are
# SetSecuritySettings and SetHostedLoginTranslation. The write is
# AdminService_UpdateLoginPolicy, PUT /admin/v1/policies/login, which that
# image does not mark deprecated. Both read out of the binary on 2026-08-31,
# the way HANDOFF.md section 7 records reading the access token lifetime.
#
# The instance rather than the organisation's own copy. The organisation reads
# back isDefault true, so it inherits this, and writing an organisation policy
# would leave an override shadowing every later change made here.
POLICY = "/admin/v1/policies/login"

# The update replaces the whole policy, so a field left out of the request
# comes back false, and sending allowRegister on its own would turn password
# sign in off and lock every member out of a building. These are the fields
# v1UpdateLoginPolicyRequest accepts, read from the same document, so whatever
# the lab has set is read here and handed straight back.
FIELDS = (
    "allowUsernamePassword", "allowRegister", "allowExternalIdp", "forceMfa",
    "forceMfaLocalOnly", "passwordlessType", "hidePasswordReset",
    "ignoreUnknownUsernames", "defaultRedirectUri", "passwordCheckLifetime",
    "externalLoginCheckLifetime", "mfaInitSkipLifetime",
    "secondFactorCheckLifetime", "multiFactorCheckLifetime",
    "allowDomainDiscovery", "disableLoginWithEmail", "disableLoginWithPhone",
)


def held(token: str) -> dict:
    """What the instance is offering people who arrive at the screens."""
    answer = api.get(POLICY, token)
    if answer.status != 200:
        raise Refused(f"the login policy could not be read: {answer.status} "
                      f"{answer.message()}. Nothing was changed.")
    return answer.body["policy"]


def self_registration_is_on(policy: dict) -> bool:
    """Whether the screens are still offering a Register button.

    A field holding its default is left out of the answer entirely, so once
    registration is off allowRegister is absent rather than false. Measured
    against 4.17.1 on 2026-08-31, and it is the shape
    registrations.differences already documents for developmentMode. Reading
    it as `is False` finds nothing and turns every later run into a write.
    """
    return bool(policy.get("allowRegister"))


def open_self_registration(token: str) -> None:
    """Let a person join the lab from the sign in screens.

    This members site replaces one that has a sign up on it, so a person who has
    never been here has to have a way in that is not asking an admin.

    It was turned off for one day, on the reasoning that a Register button with
    no mail server behind it is a dead end. The dead end was real and the fix was
    wrong. Measured on 2026-08-31 against 4.17.1: registering creates the account
    and the screens then ask for a code, and that screen carries a required code
    field, Next, and Resend Code, and nothing else. So the answer is a mail
    server, which compose.development.yaml now runs as a catcher and a deployment
    points at the lab's own.

    A forgotten password rides on the same thing. Both are dead without mail and
    both work with it.
    """
    _set_registration(True, token)


def close_self_registration(token: str) -> None:
    """Take the Register button off the screens.

    The other end of the same write, and it exists because a deployment with no
    mail server has nowhere to send a joiner. Measured on 2026-08-31 against
    4.17.1: registering with no mail server configured creates the account and
    lands it in USER_STATE_INITIAL, waiting for a code nothing can send. That is
    the one state no admin can repair. Every write to such an account is
    refused, and the only route out is removing it and making a new one, which
    costs the member their identity subject.

    So an operator who is not configuring mail today needs this, and until it
    existed the only way to close the sign up was to type the whole policy back
    by hand. Step 8 of docs/runbooks/deploy-beside-the-legacy-system.md is where
    that decision is taken. It is a decision rather than a default: this site
    replaces one that has a sign up, so the button is on unless somebody turns
    it off, and nothing derives the answer from whether mail was configured.
    """
    _set_registration(False, token)


def _set_registration(wanted_on: bool, token: str) -> None:
    """Write allowRegister, carrying the rest of the policy back unchanged.

    One function for both directions, because the whole hazard here is the
    fields that are not allowRegister and there is no version of that hazard
    worth writing down twice.
    """
    word = "on" if wanted_on else "off"
    policy = held(token)
    if self_registration_is_on(policy) == wanted_on:
        print(f"self registration: already {word}")
        return
    wanted = {field: policy[field] for field in FIELDS if field in policy}
    wanted["allowRegister"] = wanted_on

    answer = api.call(POLICY, wanted, token, method="PUT")
    # The read above comes from a projection the service updates after the
    # write, so a run following close behind another can read the old policy
    # and ask for a change that has already happened. The command side answers
    # that with a refusal rather than a shrug, and it is the same state as the
    # branch above. api.apply_branding reads this message the same way.
    if answer.status != 200 and "has not been changed" in answer.message():
        print(f"self registration: already {word}")
        return
    if answer.status != 200:
        raise Refused(f"self registration could not be turned {word}: "
                      f"{answer.status} {answer.message()}. The rest of the "
                      "login policy is untouched, so signing in still works "
                      "and a person who is already a member is unaffected. "
                      "Somebody who is not has to be given an account by an "
                      "admin until this runs.")
    print(f"self registration: turned {word}")
