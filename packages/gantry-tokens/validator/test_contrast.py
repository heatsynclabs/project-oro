#!/usr/bin/env python3
"""Tests for the colour maths, against ratios computed by hand.

The rest of the checker is only worth as much as this file. A contrast checker
that agrees with itself and with nothing else will happily certify an
unreadable theme, so every expected number below is derived from the WCAG 2.1
definition rather than from a previous run of this code.

    python3 packages/gantry-tokens/validator/test_contrast.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from contrast import (  # noqa: E402
    Colour, composite, contrast_ratio, parse_colour, relative_luminance,
)


def close(actual: float, expected: float, tolerance: float = 0.01) -> bool:
    return abs(actual - expected) <= tolerance


# ------------------------------------------------------------------ parsing

def test_parses_six_digit_hex():
    assert parse_colour("#f2ab1e") == Colour(242, 171, 30, 1.0)


def test_parses_three_digit_hex():
    assert parse_colour("#fff") == Colour(255, 255, 255, 1.0)


def test_parses_eight_digit_hex_as_alpha():
    parsed = parse_colour("#14110d80")
    assert parsed is not None
    assert (parsed.red, parsed.green, parsed.blue) == (20, 17, 13)
    assert close(parsed.alpha, 128 / 255, 0.002)


def test_parses_rgba_with_a_fractional_alpha():
    assert parse_colour("rgba(242, 171, 30, 0.12)") == Colour(242, 171, 30, 0.12)


def test_parses_rgb_as_fully_opaque():
    assert parse_colour("rgb(20 17 13)") == Colour(20, 17, 13, 1.0)


def test_parses_the_named_colours_the_token_file_uses():
    assert parse_colour("transparent") == Colour(0, 0, 0, 0.0)
    assert parse_colour("white") == Colour(255, 255, 255, 1.0)


def test_refuses_a_value_that_is_not_a_colour():
    assert parse_colour("2px solid") is None
    assert parse_colour("clamp(11px, 0.70rem + 0.1vw, 13px)") is None


# ---------------------------------------------------------------- luminance

def test_luminance_of_black_and_white():
    """The two fixed points of the WCAG 2.1 definition."""
    assert close(relative_luminance(Colour(0, 0, 0, 1.0)), 0.0, 1e-9)
    assert close(relative_luminance(Colour(255, 255, 255, 1.0)), 1.0, 1e-9)


def test_luminance_of_pure_red_is_the_red_coefficient():
    """At full channel value the transfer function returns 1, so the luminance
    is the coefficient itself: 0.2126 for red, 0.7152 green, 0.0722 blue."""
    assert close(relative_luminance(Colour(255, 0, 0, 1.0)), 0.2126, 1e-9)
    assert close(relative_luminance(Colour(0, 255, 0, 1.0)), 0.7152, 1e-9)
    assert close(relative_luminance(Colour(0, 0, 255, 1.0)), 0.0722, 1e-9)


def test_luminance_uses_the_linear_segment_below_the_knee():
    """Channel 10 of 255 is 0.0392, under the 0.03928 knee, so it divides by
    12.92 rather than taking the power. 0.0392157/12.92 = 0.0030352694."""
    assert close(relative_luminance(Colour(10, 10, 10, 1.0)), 0.0030352694, 1e-9)


# -------------------------------------------------------------------- ratio

def test_black_on_white_is_twenty_one():
    assert close(contrast_ratio(Colour(0, 0, 0, 1.0), Colour(255, 255, 255, 1.0)), 21.0)


def test_a_colour_against_itself_is_one():
    """The hazard ground against the dark theme's warn ink, which is the pair
    the exit criterion in docs/plan/order-of-operations.md names."""
    hazard = parse_colour("#f2ab1e")
    assert hazard is not None
    assert close(contrast_ratio(hazard, hazard), 1.0)


def test_the_ratio_does_not_depend_on_which_argument_is_lighter():
    dark, light = Colour(20, 17, 13, 1.0), Colour(236, 227, 211, 1.0)
    assert close(contrast_ratio(dark, light), contrast_ratio(light, dark), 1e-9)


def test_mid_grey_on_white_is_three_point_nine_five():
    """#808080 has luminance 0.21586, so (1.0 + 0.05) / (0.21586 + 0.05)."""
    assert close(contrast_ratio(Colour(128, 128, 128, 1.0),
                                Colour(255, 255, 255, 1.0)), 3.95)


def test_the_wcag_aa_boundary_grey_clears_four_point_five():
    """#767676 on white is the darkest grey that passes 1.4.3 at normal size."""
    grey = parse_colour("#767676")
    white = parse_colour("#ffffff")
    assert grey is not None and white is not None
    assert 4.5 <= contrast_ratio(grey, white) < 4.6


def test_pure_red_on_white_is_four():
    assert close(contrast_ratio(Colour(255, 0, 0, 1.0),
                                Colour(255, 255, 255, 1.0)), 4.00)


# ---------------------------------------------------------------- compositing

def test_half_opaque_white_over_black_is_mid_grey():
    over = composite(Colour(255, 255, 255, 0.5), Colour(0, 0, 0, 1.0))
    assert over == Colour(128, 128, 128, 1.0)


def test_a_fully_opaque_colour_ignores_its_backdrop():
    ink = Colour(242, 171, 30, 1.0)
    assert composite(ink, Colour(0, 0, 0, 1.0)) == ink


def test_a_fully_transparent_colour_becomes_its_backdrop():
    ground = Colour(21, 18, 15, 1.0)
    assert composite(Colour(255, 255, 255, 0.0), ground) == ground


def test_compositing_changes_the_ratio_it_reports():
    """The token file writes lines and dims as rgba over the ground, so a
    checker that ignored alpha would report a ratio nobody can see."""
    line = parse_colour("rgba(236, 227, 211, 0.24)")
    ground = parse_colour("#15120f")
    assert line is not None and ground is not None
    naive = contrast_ratio(line, ground)
    real = contrast_ratio(composite(line, ground), ground)
    assert real < naive
    assert close(real, 1.94, 0.02)


def _run() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failed = []
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failed.append(name)
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
