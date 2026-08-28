#!/usr/bin/env python3
"""Tests for the theme by ground contrast check.

Two of these matter more than the rest. One proves the checker fails on the
token layer as it was extracted, because a checker that has only ever been
green proves nothing. The other proves an exemption that has started passing is
itself a failure, because that is how a known failures list turns into a place
things go to be forgotten.

    python3 packages/gantry-tokens/validator/test_check_contrast.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from check_contrast import (  # noqa: E402
    KNOWN_FAILURES, TOKENS, TokenFileError, audit, load_known, measure,
)

HERE = Path(__file__).resolve().parent
UNFIXED = HERE / "fixtures" / "unfixed-grounds.css"

# One theme, two grounds, two inks. Small enough that every expected number in
# the tests below can be read straight off it.
TINY = """
:root, :root[data-theme="dark"] {
  --char: #15120f;
  --hazard: #f2ab1e;
  --ink-ok: #7fd0aa;
  --ink-warn: #f2ab1e;
}
:root, [data-ground="page"] { --g-bg: var(--char); }
[data-ground="hazard"] { --g-bg: var(--hazard); }
"""


def ratio_for(measurements, theme, ground, token) -> float:
    for measurement in measurements:
        if (measurement.theme, measurement.ground, measurement.token) == (theme, ground, token):
            return measurement.ratio
    raise AssertionError(f"no measurement for {theme} {ground} {token}")


# ------------------------------------------------------------- cross product

def test_walks_every_theme_by_ground_by_ink_combination():
    measurements = measure(TINY)
    assert len(measurements) == 1 * 2 * 2


def test_measures_an_ink_against_the_ground_it_sits_on():
    """--ink-ok is a pale green. On the near black page it is legible, and on
    the amber hazard band it is not, and one file has to report both."""
    measurements = measure(TINY)
    assert ratio_for(measurements, "dark", "page", "--ink-ok") > 4.5
    assert ratio_for(measurements, "dark", "hazard", "--ink-ok") < 4.5


# --------------------------------------------------- the defect that was real

def test_catches_the_warn_ink_on_the_hazard_ground_at_one_point_zero():
    """The pair named in the phase 1 exit criterion of
    docs/plan/order-of-operations.md. Amber ink on an amber ground."""
    assert ratio_for(measure(TINY), "dark", "hazard", "--ink-warn") == 1.0


def test_fails_on_the_token_layer_as_it_was_extracted():
    """The fixture holds the theme and ground blocks of GANTRY v2.0 exactly as
    the brand package ships them, before the ink family was moved into the
    grounds. Every status ink on the hazard ground has to be reported."""
    report = audit(measure(UNFIXED.read_text(encoding="utf-8")), {})
    failing = {(f.ground, f.token) for f in report.failures}
    assert ("hazard", "--ink-warn") in failing
    assert ("hazard", "--ink-ok") in failing
    assert ("plate", "--ink-warn") in failing
    assert report.exit_code() != 0


def test_measures_the_ground_text_family_and_not_only_the_status_inks():
    """--g-ink is what the [data-ground] rule paints as `color`, --g-ink-3 is
    what --color-text-tertiary resolves to, and --g-on-accent is what the
    upstream .g-eyebrow sets. A check that names itself every ink on every
    ground has to include them."""
    measured = {m.token for m in measure(TOKENS.read_text(encoding="utf-8"))}
    for token in ("--g-ink", "--g-ink-2", "--g-ink-3", "--g-on-accent"):
        assert token in measured, f"{token} is never measured"


def test_reports_the_tertiary_ground_ink_where_it_is_below_the_minimum():
    """Measured at 3.09 on the dark raised ground. If this ever comes back
    passing, the entry in known-failures.txt is what fails instead."""
    ratio = ratio_for(measure(TOKENS.read_text(encoding="utf-8")),
                      "dark", "raised", "--g-ink-3")
    assert ratio < 4.5


# ----------------------------------------------------------- known failures

def test_a_triaged_pair_does_not_fail_the_build():
    known = load_known("dark | hazard | --ink-warn | 1.00 | a reason\n")
    report = audit(measure(TINY), known)
    assert ("hazard", "--ink-warn") not in {(f.ground, f.token) for f in report.failures}
    assert len(report.accepted) == 1


def test_a_triaged_pair_that_has_started_passing_is_itself_a_failure():
    """A stale exemption is how a known failures list becomes a place things go
    to be forgotten."""
    known = load_known("dark | page | --ink-ok | 3.00 | a reason\n")
    report = audit(measure(TINY), known)
    assert any("--ink-ok" in line and "passes" in line for line in report.stale)
    assert report.exit_code() != 0


def test_a_triaged_pair_that_no_longer_exists_is_a_failure():
    known = load_known("dark | scaffold | --ink-ok | 2.00 | a ground that went away\n")
    report = audit(measure(TINY), known)
    assert any("scaffold" in line for line in report.stale)
    assert report.exit_code() != 0


def test_a_triaged_ratio_that_has_drifted_is_a_failure():
    """The recorded number is the record. If a pair gets worse while still
    failing, silence would hide it."""
    known = load_known("dark | hazard | --ink-warn | 2.10 | a stale number\n")
    report = audit(measure(TINY), known)
    assert any("2.1" in line for line in report.stale)


def test_an_entry_needs_a_reason():
    try:
        load_known("dark | hazard | --ink-warn | 1.00 |\n")
    except TokenFileError:
        return
    raise AssertionError("an exemption with no reason was accepted")


def test_comments_and_blank_lines_are_allowed_in_the_known_failures_file():
    known = load_known("# a heading\n\ndark | hazard | --ink-warn | 1.00 | a reason\n")
    assert len(known) == 1


# ------------------------------------------------------- refusing to be vacuous

def test_refuses_a_token_file_with_no_grounds():
    """GANTRY v1.1 in heatsynclabs/new-hsl has no [data-ground] blocks. Running
    the checker at it must be loud rather than a green run over nothing."""
    try:
        measure(':root { --ink-ok: #216b4d; --g-bg: #ffffff; }')
    except TokenFileError as error:
        assert "ground" in str(error)
        return
    raise AssertionError("a file with no grounds was measured anyway")


def test_refuses_a_token_file_with_no_ink_tokens():
    try:
        measure(':root { --char: #15120f; }\n[data-ground="page"] { --g-bg: var(--char); }')
    except TokenFileError as error:
        assert "ink" in str(error)
        return
    raise AssertionError("a file with no inks was measured anyway")


def test_refuses_a_ground_that_declares_no_background():
    css = TINY.replace('[data-ground="hazard"] { --g-bg: var(--hazard); }',
                       '[data-ground="hazard"] { --g-line: #000000; }')
    try:
        measure(css)
    except TokenFileError as error:
        assert "--g-bg" in str(error)
        return
    raise AssertionError("a ground with no background was measured anyway")


def test_refuses_an_ink_that_does_not_resolve_to_a_colour():
    css = TINY.replace("--ink-ok: #7fd0aa;", "--ink-ok: var(--nothing-at-all);")
    try:
        measure(css)
    except TokenFileError as error:
        assert "--ink-ok" in str(error)
        return
    raise AssertionError("an unresolvable ink was measured anyway")


# ------------------------------------------------------------- the real thing

def test_the_shipped_token_layer_passes_with_its_triaged_list():
    report = audit(measure(TOKENS.read_text(encoding="utf-8")),
                   load_known(KNOWN_FAILURES.read_text(encoding="utf-8")))
    assert report.failures == [], [str(f) for f in report.failures]
    assert report.stale == [], report.stale


# The two defects are structural, and neither shows up in a contrast ratio.
# validator/test_grounds.py is what holds them fixed.


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
