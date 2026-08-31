"""The login policy, which is what the hosted sign in screens are built from.

tools/identity/configure.py applies this beside the clients and the branding,
so one idempotent step decides what a member is offered when they arrive. Its
own file rather than a section of api.py, which is calls to the identity
service and has no business holding a policy.

The Register button is the whole reason this exists. It is on, because this site
replaces one that has a sign up. It needs a mail server behind it: the screens
ask a new joiner for a code, and compose.development.yaml runs a catcher for a
laptop while a deployment points at the lab's own server.
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
    policy = held(token)
    if self_registration_is_on(policy):
        print("self registration: already on")
        return
    wanted = {field: policy[field] for field in FIELDS if field in policy}
    wanted["allowRegister"] = True

    answer = api.call(POLICY, wanted, token, method="PUT")
    # The read above comes from a projection the service updates after the
    # write, so a run following close behind another can read the old policy
    # and ask for a change that has already happened. The command side answers
    # that with a refusal rather than a shrug, and it is the same state as the
    # branch above. api.apply_branding reads this message the same way.
    if answer.status != 200 and "has not been changed" in answer.message():
        print("self registration: already on")
        return
    if answer.status != 200:
        raise Refused(f"self registration could not be turned on: "
                      f"{answer.status} {answer.message()}. The rest of the "
                      "login policy is untouched, so signing in still works "
                      "and a person who is already a member is unaffected. "
                      "Somebody who is not has to be given an account by an "
                      "admin until this runs.")
    print("self registration: turned on")
