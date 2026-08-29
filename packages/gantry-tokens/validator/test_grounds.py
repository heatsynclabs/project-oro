#!/usr/bin/env python3
"""Tests that the two measured defects stay fixed in the shipped token layer.

Neither defect is visible in a contrast ratio, so nothing in
`test_check_contrast.py` would notice either one coming back. Defect 1 could be
hidden by darkening a theme until the numbers pass while the grounds still
declare no inks of their own. Defect 2 changes no ratio at all: a ground that
paints nothing measures exactly the same as one that paints.

Both are read out of the parsed stylesheet rather than searched for in its
text, so a rule commented out during debugging fails the same way a deleted one
does.

    python3 packages/gantry-tokens/validator/test_grounds.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cascade import grounds, parse_blocks, parse_rules, themes  # noqa: E402
from check_contrast import TOKENS  # noqa: E402

# The two rules defect 2 added.
GROUND = "[data-ground]"
NO_PAINT = '[data-ground][data-ground-paint="none"]'


def _properties_on(css: str, selector: str) -> dict[str, str]:
    """Every ordinary property a rule with exactly this selector declares."""
    found: dict[str, str] = {}
    for selectors, declarations in parse_rules(css):
        if selector in selectors:
            found.update({name: value for name, value in declarations.items()
                          if not name.startswith("--")})
    return found


def _comment_out(css: str, selector: str) -> str:
    """The file with one rule commented out, the way a person leaves it."""
    opening = "\n" + selector + " {"
    if opening not in css:
        raise AssertionError(f"there is no {selector} rule to comment out, so "
                             "this test cannot prove anything about one")
    start = css.index(opening) + 1
    end = css.index("}", start) + 1
    return css[:start] + "/* " + css[start:end] + " */" + css[end:]


# ------------------------------------- defect 1, the inks live in the grounds

def test_every_ground_declares_its_own_status_inks():
    """Measuring alone would let somebody satisfy the numbers by darkening a
    theme and leaving the mechanism broken."""
    blocks = parse_blocks(TOKENS.read_text(encoding="utf-8"))
    assert set(grounds(blocks)) == {"page", "raised", "plate", "hazard"}
    assert set(themes(blocks)) == {"dark", "light"}
    for ground in grounds(blocks):
        declared = {name
                    for selectors, declarations in blocks
                    for name in declarations
                    if f'[data-ground="{ground}"]' in selectors
                    and name.startswith("--ink-")}
        assert "--ink-warn" in declared, f"{ground} carries no --ink-warn"


def test_no_block_declares_a_status_ink_without_naming_a_ground():
    """The other half of the same rule, because that is the shape the defect
    had: the family declared in the theme blocks and nowhere else."""
    for selectors, declarations in parse_blocks(TOKENS.read_text(encoding="utf-8")):
        inks = [name for name in declarations if name.startswith("--ink-")]
        if inks:
            assert any("[data-ground" in selector for selector in selectors), \
                f"{inks} declared by {selectors} with no ground"


# ------------------------------------------------ defect 2, a ground paints

def test_a_bare_grounded_element_is_painted():
    """A ground that remaps variables and paints nothing reads as though the
    mechanism is broken."""
    painted = _properties_on(TOKENS.read_text(encoding="utf-8"), GROUND)
    assert painted.get("background-color") == "var(--g-bg)"
    assert painted.get("color") == "var(--g-ink)"


def test_a_commented_out_paint_rule_does_not_count_as_painting():
    """Commenting the rule out while debugging and not restoring it is the
    ordinary way this regresses, and a substring search would still find it."""
    disabled = _comment_out(TOKENS.read_text(encoding="utf-8"), GROUND)
    assert _properties_on(disabled, GROUND) == {}


def test_the_paint_can_be_turned_off_without_losing_the_remap():
    """The opt out: an inline badge that wants its ground's inks and wants the
    surface behind it to show through."""
    opted_out = _properties_on(TOKENS.read_text(encoding="utf-8"), NO_PAINT)
    assert opted_out.get("background-color") == "transparent"
    assert opted_out.get("color") == "inherit"


def test_turning_the_paint_off_does_not_turn_the_remap_off():
    """The opt out rule may set colours and nothing else. A custom property in
    it would undo the remap it exists to keep."""
    for selectors, declarations in parse_rules(TOKENS.read_text(encoding="utf-8")):
        if NO_PAINT in selectors:
            remapped = [name for name in declarations if name.startswith("--")]
            assert remapped == [], f"the opt out rule remaps {remapped}"


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
