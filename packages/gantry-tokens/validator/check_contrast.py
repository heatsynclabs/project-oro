#!/usr/bin/env python3
"""Measure every ink token against every ground, on every theme.

    python3 packages/gantry-tokens/validator/check_contrast.py
    python3 packages/gantry-tokens/validator/check_contrast.py --tokens PATH
    python3 packages/gantry-tokens/validator/check_contrast.py --list

Exit code 0 when every pair either clears the WCAG 2.1 contrast minimum or
carries a triaged entry in `known-failures.txt`. Nonzero otherwise, including
when an entry in that file has started passing: a stale exemption is how a
known failures list becomes a place things go to be forgotten.

The themes and the grounds are read out of the token file. Nothing here knows
that GANTRY has two themes and four grounds, so adding a ground puts its inks
under the check without anyone remembering to.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cascade import environment, grounds, parse_blocks, resolve, themes  # noqa: E402
from contrast import (  # noqa: E402
    MINIMUM_RATIO, Colour, composite, contrast_ratio, parse_colour,
)

HERE = Path(__file__).resolve().parent
TOKENS = HERE.parent / "tokens.css"
KNOWN_FAILURES = HERE / "known-failures.txt"

# The families this check is about. A token whose name says it is an ink is one
# somebody will eventually set `color` to, whatever it was drawn for, so the
# prefix is read as a promise rather than as a hint.
#
#   --ink    the status inks, and the v1.1 aliases that kept the name
#   --g-ink  the ground text family, which is what [data-ground] paints as
#            `color` and what --color-text-primary and its two siblings alias
#   --g-on-  the accent used as text on the ground. Upstream sets
#            `color: var(--g-on-accent)` on .g-eyebrow, which sits on the
#            ground rather than on an accent coloured surface.
INK_PREFIXES = ("--ink", "--g-ink", "--g-on-")

# The token every ground sets to say what it paints behind its contents.
GROUND_BACKGROUND = "--g-bg"

# Ratios are compared at two decimal places, which is how they are written in
# the known failures file and how anybody quotes one.
_PLACES = 2


class TokenFileError(Exception):
    """The token file cannot be measured, so no result from it means anything."""


@dataclass(frozen=True)
class Measurement:
    theme: str
    ground: str
    token: str
    ink: Colour
    background: Colour
    ratio: float

    def __str__(self) -> str:
        return (f"{self.theme:<6} {self.ground:<7} {self.token:<14} "
                f"{self.ratio:5.2f}  {self.ink} on {self.background}")


@dataclass
class Report:
    failures: list[Measurement]
    accepted: list[Measurement]
    stale: list[str]

    def exit_code(self) -> int:
        return 1 if self.failures or self.stale else 0


def _ink_names(blocks, theme_names, ground_names) -> list[str]:
    names = set()
    for theme in theme_names:
        for ground in ground_names:
            names.update(name for name in environment(blocks, theme, ground)
                         if name.startswith(INK_PREFIXES))
    return sorted(names)


def _colour_of(token: str, values: dict[str, str], where: str) -> Colour:
    raw = resolve(token, values)
    colour = parse_colour(raw) if raw is not None else None
    if colour is None:
        raise TokenFileError(
            f"{token} on {where} resolves to {raw!r}, which is not a colour. "
            "Either give it a colour or rename it out of "
            f"{', '.join(INK_PREFIXES)}, because this check reads those "
            "prefixes as a promise that the token is something a person will "
            "set `color` to")
    return colour


def _declared_by(blocks, ground: str) -> set[str]:
    """The tokens a ground states for itself, ignoring what it inherits."""
    names: set[str] = set()
    for selectors, declarations in blocks:
        if any(selector == "[data-ground]" or f'[data-ground="{ground}"]' == selector
               for selector in selectors):
            names.update(declarations)
    return names


def _background_of(blocks, theme: str, ground: str) -> Colour:
    values = environment(blocks, theme, ground)
    if GROUND_BACKGROUND not in _declared_by(blocks, ground):
        raise TokenFileError(
            f'the ground [data-ground="{ground}"] declares no '
            f"{GROUND_BACKGROUND} of its own, so it inherits one and its inks "
            "would be measured against a surface it does not paint. Every "
            "ground names the surface it paints")
    colour = _colour_of(GROUND_BACKGROUND, values, f"{theme}/{ground}")
    if colour.alpha < 1.0:
        raise TokenFileError(
            f'the ground [data-ground="{ground}"] paints {colour} on the '
            f"{theme} theme, which is translucent. What shows through depends "
            "on where the element is nested, so the ratio underneath it is not "
            "a property of the token file. Give the ground an opaque colour")
    return colour


def measure(css: str) -> list[Measurement]:
    """Every ink token, on every ground, on every theme the file declares."""
    blocks = parse_blocks(css)
    theme_names = themes(blocks) or [""]
    ground_names = grounds(blocks)
    if not ground_names:
        raise TokenFileError(
            "the token file declares no [data-ground] blocks, so there is no "
            "cross product to walk. GANTRY v1.1 is shaped that way and is not "
            "what this checks")
    ink_names = _ink_names(blocks, theme_names, ground_names)
    if not ink_names:
        raise TokenFileError(
            "the token file declares no "
            f"{' or '.join(INK_PREFIXES)} tokens, so this check would pass "
            "having looked at nothing")

    out: list[Measurement] = []
    for theme in theme_names:
        for ground in ground_names:
            background = _background_of(blocks, theme, ground)
            values = environment(blocks, theme, ground)
            for token in ink_names:
                ink = composite(_colour_of(token, values, f"{theme}/{ground}"),
                                background)
                out.append(Measurement(
                    theme, ground, token, ink, background,
                    round(contrast_ratio(ink, background), _PLACES)))
    return out


def load_known(text: str) -> dict[tuple[str, str, str], tuple[float, str]]:
    """Read the triaged list. One accepted pair per line, with its reason."""
    known: dict[tuple[str, str, str], tuple[float, str]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [field.strip() for field in line.split("|")]
        if len(fields) != 5 or not all(fields):
            raise TokenFileError(
                f"line {number} of the known failures file is not "
                "'theme | ground | token | ratio | why it is accepted for now'. "
                "A pair with no reason is an exemption nobody can review: "
                f"{line.strip()!r}")
        theme, ground, token, ratio, reason = fields
        known[(theme, ground, token)] = (float(ratio), reason)
    return known


def _stale_lines(known, measured: dict[tuple[str, str, str], Measurement]) -> list[str]:
    out = []
    for key, (ratio, _) in sorted(known.items()):
        where = " ".join(key)
        measurement = measured.get(key)
        if measurement is None:
            out.append(f"{where} is in the known failures file but is no "
                       "longer measured. Delete the line")
        elif measurement.ratio >= MINIMUM_RATIO:
            out.append(f"{where} now passes at {measurement.ratio:.2f}. "
                       "Delete the line")
        elif round(measurement.ratio, _PLACES) != round(ratio, _PLACES):
            out.append(f"{where} is recorded at {ratio:.2f} and now measures "
                       f"{measurement.ratio:.2f}. Update the line")
    return out


def audit(measurements: list[Measurement], known) -> Report:
    measured = {(m.theme, m.ground, m.token): m for m in measurements}
    failures: list[Measurement] = []
    accepted: list[Measurement] = []
    for measurement in measurements:
        if measurement.ratio >= MINIMUM_RATIO:
            continue
        key = (measurement.theme, measurement.ground, measurement.token)
        (accepted if key in known else failures).append(measurement)
    return Report(failures, accepted, _stale_lines(known, measured))


def _print_report(report: Report, total: int, known_file: Path) -> None:
    for measurement in report.failures:
        print(f"FAIL  {measurement}", file=sys.stderr)
    for line in report.stale:
        print(f"STALE {line}", file=sys.stderr)
    print(f"{total} pairs measured against {MINIMUM_RATIO}:1. "
          f"{len(report.failures)} unaccounted for, "
          f"{len(report.accepted)} triaged in {known_file.name}, "
          f"{len(report.stale)} stale.", file=sys.stderr)
    if report.failures:
        print("A pair below the minimum gets fixed in the token file, or gets "
              "a line in the known failures file saying why it is accepted for "
              "now and what it measures today.", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tokens", type=Path, default=TOKENS)
    parser.add_argument("--known-failures", type=Path, default=KNOWN_FAILURES)
    parser.add_argument("--list", action="store_true",
                        help="print every measured pair, passing or not")
    args = parser.parse_args()

    try:
        measurements = measure(args.tokens.read_text(encoding="utf-8"))
        known = (load_known(args.known_failures.read_text(encoding="utf-8"))
                 if args.known_failures.exists() else {})
    except (TokenFileError, OSError) as error:
        print(f"contrast check: {error}", file=sys.stderr)
        return 2

    if args.list:
        for measurement in measurements:
            mark = "ok  " if measurement.ratio >= MINIMUM_RATIO else "low "
            print(f"{mark}{measurement}")

    report = audit(measurements, known)
    _print_report(report, len(measurements), args.known_failures)
    return report.exit_code()


if __name__ == "__main__":
    sys.exit(main())
