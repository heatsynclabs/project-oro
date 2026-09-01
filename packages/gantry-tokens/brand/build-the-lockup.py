#!/usr/bin/env python3
"""Build the mark and wordmark lockup the identity service uploads.

    packages/gantry-tokens/brand/build-the-lockup.py

The members portal carries the mark and the wordmark inline in its masthead,
because an inline SVG inherits currentColor and costs no second request. The
hosted sign in screens cannot inline anything: Zitadel takes a file. So the file
is built from the same two SVGs the masthead carries rather than kept beside
them, because a second copy of a logo is two logos that drift.

currentColor has no meaning in an uploaded file, so the ink is named, and there
are two files because the label policy has a light slot and a dark one. Both
inks are --bone, read from packages/gantry-tokens/tokens.css, and they are the
two colours the label policy already sends as fontColor and fontColorDark.

The dark file arrived on 2026-08-31, and until it did branding.py uploaded the
light one into both slots. Measured with the checker in
packages/gantry-tokens/validator: #1c1812 on #15120f is 1.06 to 1, and #ece3d3
on the same ground is 14.66. It was latent rather than visible because the label
policy pins themeMode to light, so nothing was rendering the dark slots.

Provenance, per rule 9: hsl-mark-current.svg and hsl-wordmark-current.svg,
carried unchanged from the hsl-forge brand package. apps/members/README.md under
"The mark" has the rest.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
PAGE = ROOT / "apps/members/index.html"
HERE = ROOT / "packages/gantry-tokens/brand"

# One entry per label policy slot that takes a file. The name is what
# tools/identity/branding.py uploads and the ink is what currentColor becomes.
LOCKUPS = (
    ("hsl-lockup.svg", "#1c1812"),        # --bone, light theme
    ("hsl-lockup-dark.svg", "#ece3d3"),   # --bone, dark theme
)


def one_svg(page: str, css_class: str) -> str:
    found = re.search(r'<svg[^>]*class="' + css_class + r'"[^>]*>.*?</svg>',
                      page, re.S)
    if not found:
        raise SystemExit(
            f"{PAGE} has no svg with class {css_class}. The masthead is where "
            "the mark lives, so either it moved or it stopped being inline, and "
            "this file has to follow it rather than keep its own copy.")
    return found.group(0)


def parts(svg: str, ink: str) -> tuple[str, list[float]]:
    inner = re.search(r">(.*)</svg>$", svg, re.S).group(1)
    box = [float(n) for n in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    return inner.replace("currentColor", ink), box


def build(ink: str) -> str:
    page = PAGE.read_text()
    mark, mark_box = parts(one_svg(page, "sunmark"), ink)
    word, word_box = parts(one_svg(page, "wordmark-svg"), ink)

    # The masthead puts the mark left of the wordmark on one baseline. The
    # wordmark is set to a little under two thirds of the mark's height, which is
    # the proportion the masthead renders at, and the gap is a fifth of the mark.
    height = mark_box[3]
    scale = height * 0.62 / word_box[3]
    gap = height * 0.18
    width = mark_box[2] + gap + word_box[2] * scale
    top = (height - word_box[3] * scale) / 2
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %g %g" '
        'width="%g" height="%g" role="img" aria-label="HeatSync Labs">\n'
        '<g>%s</g>\n<g transform="translate(%g %g) scale(%g)">%s</g>\n</svg>\n'
    ) % (width, height, width, height, mark, mark_box[2] + gap, top, scale, word)


def main(argv: list[str]) -> int:
    """Write the lockup, or with --check report whether it is already right.

    Rewriting on mismatch is what a person wants and it is wrong for a gate: a
    checker that fixes the thing it is checking always passes. So the two are
    one flag apart, and packages/gantry-tokens/tests/run.sh runs the --check
    side. Until it did, this file existed so that a second copy of the logo
    could not drift from the masthead and nothing ran it: no target, no job, no
    suite.
    """
    checking = "--check" in argv
    adrift = []
    for name, ink in LOCKUPS:
        out = HERE / name
        built = build(ink)
        if out.exists() and out.read_text() == built:
            print(f"{name} matches the masthead.")
            continue
        if checking:
            adrift.append(name)
            continue
        out.write_text(built)
        print(f"{name} written from the masthead in {PAGE.name}.")
    if adrift:
        print(f"{', '.join(adrift)} does not match the masthead in "
              f"{PAGE.name}, and nothing was written. The hosted sign in "
              "screens carry those files and the portal carries the masthead, "
              "so they are two logos now. Run "
              "packages/gantry-tokens/brand/build-the-lockup.py with no "
              "arguments and commit what it writes.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
