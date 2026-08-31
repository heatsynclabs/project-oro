#!/usr/bin/env python3
"""Build the mark and wordmark lockup the identity service uploads.

    packages/gantry-tokens/brand/build-the-lockup.py

The members portal carries the mark and the wordmark inline in its masthead,
because an inline SVG inherits currentColor and costs no second request. The
hosted sign in screens cannot inline anything: Zitadel takes a file. So the file
is built from the same two SVGs the masthead carries rather than kept beside
them, because a second copy of a logo is two logos that drift.

currentColor has no meaning in an uploaded file, so the ink is named. #1c1812 is
--bone in the light theme, read from packages/gantry-tokens/tokens.css, and it is
the colour the label policy already sends as fontColor.

Provenance, per rule 9: hsl-mark-current.svg and hsl-wordmark-current.svg,
carried unchanged from the hsl-forge brand package. apps/members/README.md under
"The mark" has the rest.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
PAGE = ROOT / "apps/members/index.html"
OUT = ROOT / "packages/gantry-tokens/brand/hsl-lockup.svg"
INK = "#1c1812"


def one_svg(page: str, css_class: str) -> str:
    found = re.search(r'<svg[^>]*class="' + css_class + r'"[^>]*>.*?</svg>',
                      page, re.S)
    if not found:
        raise SystemExit(
            f"{PAGE} has no svg with class {css_class}. The masthead is where "
            "the mark lives, so either it moved or it stopped being inline, and "
            "this file has to follow it rather than keep its own copy.")
    return found.group(0)


def parts(svg: str) -> tuple[str, list[float]]:
    inner = re.search(r">(.*)</svg>$", svg, re.S).group(1)
    box = [float(n) for n in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    return inner.replace("currentColor", INK), box


def build() -> str:
    page = PAGE.read_text()
    mark, mark_box = parts(one_svg(page, "sunmark"))
    word, word_box = parts(one_svg(page, "wordmark-svg"))

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


if __name__ == "__main__":
    built = build()
    if OUT.exists() and OUT.read_text() == built:
        print(f"{OUT.name} already matches the masthead.")
    else:
        OUT.write_text(built)
        print(f"{OUT.name} written from the masthead in {PAGE.name}.")
