#!/usr/bin/env python3
"""The lab's own face on the identity service: the colours, the marks, the words.

Split out of check_configuration.py, which reached the 300 line ceiling in
rule 6. That file is what configure.py registered and one whole sign in through
it. This one is the part a member sees rather than the part they use, and every
check here was written because that part had been somebody else's.

    ORO_IDENTITY_URL=... ORO_IDENTITY_TOKEN=... \\
      python3 tools/identity/tests/check_branding.py

tools/identity/tests/run.sh starts a stack, configures it, and runs this.
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import api                       # noqa: E402, after the path insert above
import branding                  # noqa: E402
import flow                      # noqa: E402
import messages                  # noqa: E402

TOKEN = os.environ.get("ORO_IDENTITY_TOKEN", "")


def test_the_branding_reaches_the_login_screen():
    """Set is not the same as activated, and activated is not the same as served.

    So this reads the stylesheet the screens actually load and looks for the
    accent colour out of packages/gantry-tokens/tokens.css in it.
    """
    organisation = api.call("/v2/organizations/_search", {}, TOKEN).body["result"][0]["id"]
    status, css = flow.fetch_page(
        f"/ui/login/resources/dynamic?orgId={organisation}"
        "&default-policy=false&filename=policy/label/css/variables.css")
    assert status == 200, f"the branding stylesheet answered {status}"
    red, green, blue = (int(branding.POLICY["primaryColor"][i:i + 2], 16)
                        for i in (1, 3, 5))
    assert f"rgb({red}, {green}, {blue})" in css, (
        f"the login screens do not carry {branding.POLICY['primaryColor']}. A label "
        "policy that was set and never activated reads as applied and changes "
        "nothing")


def test_the_dark_slots_carry_a_mark_that_can_be_seen_on_a_dark_ground():
    """The light lockup used to go into all four slots.

    Its ink is #1c1812 and the dark ground the policy sends is #15120f, which
    the checker in packages/gantry-tokens/validator measures at 1.06 to 1. The
    dark file is the same mark in #ece3d3, 14.66 on that ground. It was latent
    because themeMode is pinned to light and nothing renders the dark slots, so
    only a check that reads what the service serves would have found it.

    The asset is fetched rather than the file on disk compared, because the step
    that could go wrong is the upload choosing a slot.
    """
    answer = api.get("/management/v1/policies/label", TOKEN)
    assert answer.status == 200, answer.message()
    policy = answer.body["policy"]
    for field, ink in (("logoUrl", "#1c1812"), ("logoUrlDark", "#ece3d3")):
        where = policy.get(field) or ""
        assert where, f"the label policy carries no {field}: {sorted(policy)}"
        # The service builds that URL from the instance domain, which is not the
        # name this suite reaches it by, so only the path is taken from it.
        status, served = flow.fetch_page("/" + where.split("/", 3)[3])
        assert status == 200, f"{field} answered {status}"
        assert ink in served, (
            f"the mark in {field} is not drawn in {ink}, so it is the wrong "
            "file for that slot. build-the-lockup.py writes one per ink and "
            "branding.UPLOADS says which goes where")


def test_the_first_message_a_new_member_gets_is_the_labs_and_not_the_vendors():
    """The first thing anybody hears from this system, and it was somebody else.

    Until 2026-08-31 a person who pressed Register was sent "This user was
    created in Zitadel. Use the username ... to login", read off a running
    instance at this same path. That is a handoff to a company they have never
    heard of, at the moment they are being asked to trust the thing.

    Asserted on the words rather than on `isDefault`, which says where the text
    came from and not what it says.
    """
    text = messages.held(TOKEN)
    said = " ".join(str(value) for value in text.values())
    assert "Zitadel" not in said, (
        "the message a new member gets still names the vendor: " + said[:300])
    assert "HeatSync Labs" in text.get("subject", ""), (
        f"the subject line does not name the lab: {text.get('subject')!r}")
    assert "{{.Code}}" in text.get("text", ""), (
        "the message carries no code, and the Activate User screen it leads to "
        f"asks for one: {text.get('text')!r}")


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
    if not TOKEN:
        print("No ORO_IDENTITY_TOKEN, so nothing was checked.", file=sys.stderr)
        sys.exit(1)
    sys.exit(_run())
