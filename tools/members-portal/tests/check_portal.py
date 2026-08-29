#!/usr/bin/env python3
"""Prove the members portal, through Caddy, without a browser.

Most checks here call the running development stack over plain HTTP, which is
the only scheme it serves. ADR 0003 says why. The rest read two files that have
to agree with each other, or run the command the page tells a reader to run
when nothing answers.

What this cannot do is execute the page's JavaScript, so it never sees the
rendered document. It asserts the two things either side of that: the copy and
the structure a reader is served, and that every field the page binds is a
field the contract actually serves at the endpoint that page reads. A field
name the mock does not carry is the failure this catches, and it is the one
that renders a member an empty profile.

Run it against a stack that is already up:

    ORO_PORTAL_URL=http://localhost:8080 python3 tools/members-portal/tests/check_portal.py

tools/members-portal/tests/run.sh brings up its own stack and runs this.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402
import page  # noqa: E402
from harness import (MISSING, PORTAL, ROOT, fetch,  # noqa: E402
                     resolve, signed_in)

HTML = fetch("/").body
VIEWS = page.carrying(HTML, "data-source")

# Every command the page tells a reader to run, taken out of the copy rather
# than listed again here. A sentence that names a target nobody kept is the
# defect these are checked against.
NAMED_TARGETS = sorted(set(re.findall(r"<code>make ([a-z-]+)</code>", HTML)))


# --------------------------------------------------- the page a reader is sent

def test_the_portal_is_served_at_the_root():
    answer = fetch("/")
    assert answer.status == 200, f"got {answer.status}"
    assert "text/html" in answer.headers.get("Content-Type", ""), \
        answer.headers.get("Content-Type")


def test_the_page_declares_a_language_and_a_viewport():
    assert re.search(r"<html[^>]+lang=", HTML), "no lang on the html element"
    assert '<meta name="viewport"' in HTML, "no viewport meta tag"


def test_the_page_says_it_is_reading_from_the_contract_mock():
    """Rule 7. A volunteer at 2am must not have to work out whether the record
    in front of them is a real person."""
    notice = [element for element in page.elements(HTML)
              if element.get("role") == "note"]
    assert notice, "no element with role=note, so nothing says what this is"
    assert "contract mock" in HTML, "the page never says it reads from the mock"
    assert "No real member data" in HTML, "the page never says the data is invented"
    assert "no sign in" in HTML, "the page never says there is nobody signed in"


def test_the_page_offers_nothing_that_looks_like_it_saves():
    """Read only, and provably so. A form that appears to save and does not is
    worse than no form."""
    for tag in ("form", "input", "textarea", "select"):
        assert not page.named(HTML, tag), f"the page carries a {tag} element"


def test_a_skip_link_reaches_the_main_landmark():
    links = [element.get("href") for element in page.named(HTML, "a")]
    assert "#main" in links, "no skip link pointing at #main"
    assert any(element.get("id") == "main" for element in page.elements(HTML)), \
        "nothing on the page carries id=main"


def test_every_image_carries_an_alt_and_every_icon_is_an_svg():
    for image in page.named(HTML, "img"):
        assert "alt" in image.attrs, f"img with no alt: {image}"
    for svg in page.named(HTML, "svg"):
        described = svg.get("aria-hidden") == "true" or "role" in svg.attrs
        assert described, f"an svg that is neither hidden nor given a role: {svg}"


def test_the_headings_run_in_order():
    """One h1, and no level skipped on the way down. A screen reader user moves
    through a page by its headings, so a gap in them is a gap in the page."""
    levels = [int(element.name[1]) for element in page.elements(HTML)
              if re.fullmatch(r"h[1-6]", element.name)]
    assert levels.count(1) == 1, f"{levels.count(1)} h1 elements, expected one"
    assert levels[0] == 1, f"the first heading is an h{levels[0]}"
    for before, after in zip(levels, levels[1:]):
        assert after <= before + 1, f"an h{before} is followed by an h{after}"


def test_a_reader_with_no_javascript_is_told_so():
    assert page.named(HTML, "noscript"), "no noscript element"


def test_the_error_copy_a_reader_sees_is_in_the_page():
    """The renderer clones these, so the sentences ship with the document and
    this check can read them. An error names what happened, what the system did,
    and what to do next."""
    for identifier in ("api-unreachable", "api-problem"):
        assert f'id="{identifier}"' in HTML, f"no template with id {identifier}"
    assert "did not answer" in HTML, "nothing tells a reader the API was silent"
    assert "make development" in HTML, "nothing tells a reader how to start the mock"


def test_every_command_the_error_copy_names_is_a_target_that_exists():
    """A sentence that sends a volunteer to a command nobody kept wastes the
    one minute they have, at the hour they have least of it."""
    assert NAMED_TARGETS, "the page names no command, so it tells a reader nothing to run"
    makefile = (ROOT / "Makefile").read_text()
    for target in NAMED_TARGETS:
        assert re.search(rf"^{target}:", makefile, re.M), \
            f"the page sends a reader to make {target}, which the Makefile does not define"


def test_the_logs_target_the_page_names_reaches_the_mock():
    """The page sends a reader to make logs to find out why nothing answered,
    and the mock is the thing that did not answer. Compose omits a service it
    was not told about, so a target that reads only compose.yaml prints caddy
    and db and leaves out the one the reader came for.

    This asserts what the reader is shown, not how. The mechanism has already
    changed once, from a profile wildcard to the override file, and what the
    reader needs did not change with it."""
    assert "logs" in NAMED_TARGETS, "the page sends nobody to the logs"
    printed = harness.compose_logs()
    assert "mock" in printed, \
        f"the logs of project {harness.PROJECT} carry nothing from the mock. " \
        "Set ORO_PORTAL_PROJECT if the stack under test runs as another name"


# ------------------------------------------------------- the assets it links

def test_every_stylesheet_and_script_the_page_links_is_served():
    linked = [element.get("href") for element in page.named(HTML, "link")
              if element.get("rel") == "stylesheet"]
    linked += [element.get("src") for element in page.named(HTML, "script")
               if element.get("src")]
    assert len(linked) >= 4, f"only {len(linked)} assets linked: {linked}"
    for asset in linked:
        answer = fetch(asset)
        assert answer.status == 200, f"{asset} answered {answer.status}"


def test_the_theme_is_served_from_the_package_that_owns_it():
    """One copy of the token layer. The portal used to ship a byte identical
    second copy with a check to catch the two drifting, which is a defect and a
    detector for it where one file would do. Caddy binds the package directory
    and the development routes serve it at /theme."""
    served = fetch("/theme/tokens.css")
    assert served.status == 200, f"the theme answered {served.status}"
    package = ROOT / "packages" / "gantry-tokens" / "tokens.css"
    assert served.body == package.read_text(), \
        "what is served at /theme/tokens.css is not packages/gantry-tokens/tokens.css"
    assert not (PORTAL / "theme").exists(), \
        "apps/members/theme is back. The theme is served from the package now, " \
        "so a copy here is a second copy that will drift"


def test_a_deployment_binds_no_path_that_might_not_be_there():
    """A volume takes no profile, so every bind on the caddy service is part of
    the deployment too. A bind whose source is missing is worse than an unused
    one: Docker creates a directory in its place, in the working tree, and the
    stack comes up healthy serving nothing where a stylesheet was."""
    sources = harness.caddy_bind_sources()
    assert sources, "compose.yaml binds no path into caddy, so this read nothing"
    for source in sources:
        assert (ROOT / source).exists(), \
            f"caddy binds {source}, which is not there, so Docker creates a " \
            "directory at that path the next time the stack starts"


def test_the_page_paints_itself_with_ground_tokens():
    styles = fetch("/members.css").body
    for token in ("--g-bg", "--g-ink", "--g-line"):
        assert token in styles, f"{token} is never used, so the ground is ignored"
    assert "data-ground" in HTML, "no element sits on a named ground"


# --------------------------------------------- the contract underneath it all

def test_the_mock_answers_on_the_origin_the_page_calls():
    assert signed_in("/v1/me").status == 200, "the portal origin does not serve /v1/me"


def test_the_token_the_portal_sends_is_the_one_the_mock_accepts():
    assert fetch("/v1/me").status == 401, "the mock accepted a call with no token"
    assert signed_in("/v1/me").status == 200, "the mock refused the portal's token"


def test_every_view_reads_an_endpoint_this_contract_serves():
    assert len(VIEWS) == 6, f"{len(VIEWS)} views, expected 6: " \
        f"{[view.get('data-source') for view in VIEWS]}"
    for view in VIEWS:
        answer = signed_in("/v1" + view.get("data-source"))
        assert answer.status == 200, \
            f"{view.get('data-source')} answered {answer.status}"


def fields_of(view):
    """Every bound field sitting under one view section."""
    wanted = view.get("data-source")
    out = []
    for field in page.carrying(HTML, "data-field"):
        holder = field.enclosing("data-source")
        if holder is not None and holder.get("data-source") == wanted:
            out.append(field)
    return out


def container_for(field, base):
    """The record a field resolves against: the view's own, or an item out of a
    list nested inside it."""
    nested = field.enclosing("data-item-for")
    if nested is None:
        return base
    items = resolve(base, nested.get("data-item-for"))
    if items is MISSING or not isinstance(items, list) or not items:
        return MISSING
    return items[0]


def test_every_field_the_page_shows_is_a_field_the_contract_serves():
    """The check the portal exists to make. A field name the API does not carry
    renders as nothing, and a member reads that as having no cards."""
    assert VIEWS, "no view section on the page, so this checked nothing"
    for view in VIEWS:
        source = view.get("data-source")
        data = signed_in("/v1" + source).json()
        base = data[0] if isinstance(data, list) else data
        bound = fields_of(view)
        assert bound, f"{source} is read by a view that shows no field"
        for field in bound:
            record = container_for(field, base)
            nested = field.enclosing("data-item-for")
            assert record is not MISSING, \
                f"{source} carries no list at {nested.get('data-item-for')}"
            got = resolve(record, field.get("data-field"))
            assert got is not MISSING, \
                f"{source} does not carry {field.get('data-field')}"


def test_card_eligibility_shows_its_requirements_rather_than_a_boolean():
    """api-design.md section 3.1 puts this endpoint in the contract to end a
    recurring support conversation. A bare yes or no does not end it."""
    view = [v for v in VIEWS if v.get("data-source") == "/me/card-eligibility"][0]
    bound = {field.get("data-field") for field in fields_of(view)}
    for expected in ("rule", "met", "detail", "process"):
        assert expected in bound, f"the eligibility view never shows {expected}"


def test_the_directory_says_what_gates_it():
    """The legacy application gated the directory on orientation, which locked
    paying members out for a volunteer's inaction. Saying so on the page is what
    stops it being reintroduced as a feature."""
    assert "orientation" in HTML, "nothing says orientation does not gate the directory"


def test_a_tag_number_is_shown_masked():
    view = [v for v in VIEWS if v.get("data-source") == "/me/cards"][0]
    tag = [field for field in fields_of(view)
           if field.get("data-field") == "tag_number"]
    assert tag, "the cards view never shows a tag number"
    assert tag[0].get("data-format") == "last4", \
        "the tag number is shown unmasked, so a full card number is on screen"
    assert "last4" in fetch("/render.js").body, "the renderer defines no last4 format"


if __name__ == "__main__":
    sys.exit(harness.run(globals()))
