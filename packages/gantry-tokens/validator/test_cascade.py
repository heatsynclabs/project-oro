#!/usr/bin/env python3
"""Tests for reading themes, grounds, and var() chains out of a token file.

The fixtures here are tiny CSS documents rather than the real one, so a change
to the theme cannot quietly change what these prove.

    python3 packages/gantry-tokens/validator/test_cascade.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cascade import (  # noqa: E402
    NestedGroundError, environment, grounds, parse_blocks, parse_rules, resolve,
    themes,
)

TWO_THEMES = """
:root, :root[data-theme="dark"] { --paper: #000000; --ink-ok: #7fd0aa; }
:root[data-theme="light"] { --paper: #ffffff; --ink-ok: #216b4d; }
:root, [data-ground="page"] { --g-bg: var(--paper); }
[data-ground="hazard"] { --g-bg: #f2ab1e; --ink-ok: #143d2a; }
"""


# ------------------------------------------------------------------ discovery

def test_reads_the_themes_out_of_the_file():
    """Hardcoding the theme names would make the checker green on a file that
    had stopped declaring one of them."""
    assert themes(parse_blocks(TWO_THEMES)) == ["dark", "light"]


def test_reads_the_grounds_out_of_the_file():
    assert grounds(parse_blocks(TWO_THEMES)) == ["hazard", "page"]


def test_a_new_ground_is_picked_up_without_touching_the_checker():
    css = TWO_THEMES + '\n[data-ground="scaffold"] { --g-bg: #333333; }\n'
    assert "scaffold" in grounds(parse_blocks(css))


def test_a_file_with_no_grounds_reports_none():
    """GANTRY v1.1 in heatsynclabs/new-hsl has no [data-ground] at all. The
    checker has to be able to say so rather than checking nothing."""
    assert grounds(parse_blocks(':root { --paper: #fff; }')) == []


# ------------------------------------------------------------------- cascade

def test_a_bare_root_block_applies_under_every_theme():
    blocks = parse_blocks(':root { --tap: 44px; }\n:root[data-theme="light"] { --paper: #fff; }')
    assert environment(blocks, "light", None)["--tap"] == "44px"


def test_a_later_theme_block_beats_the_bare_root_it_shares_a_name_with():
    blocks = parse_blocks(TWO_THEMES)
    assert environment(blocks, "light", "page")["--paper"] == "#ffffff"
    assert environment(blocks, "dark", "page")["--paper"] == "#000000"


def test_a_ground_block_beats_the_theme_block_for_the_same_token():
    blocks = parse_blocks(TWO_THEMES)
    assert environment(blocks, "dark", "hazard")["--ink-ok"] == "#143d2a"


def test_a_token_the_ground_does_not_declare_is_inherited_from_the_theme():
    """This is defect 1 in the unfixed file, so the model has to reproduce it
    rather than paper over it."""
    css = TWO_THEMES.replace(" --ink-ok: #143d2a;", "")
    blocks = parse_blocks(css)
    assert environment(blocks, "dark", "hazard")["--ink-ok"] == "#7fd0aa"


def test_a_root_or_ground_block_inside_a_media_query_is_refused():
    """A theme redefined inside a media query would be invisible to the flat
    model here, and a checker that silently ignores half the file is worse than
    no checker."""
    css = '@media (min-width: 720px) { [data-ground="page"] { --g-bg: #fff; } }'
    try:
        parse_blocks(css)
    except NestedGroundError:
        return
    raise AssertionError("a nested ground block was accepted")


def test_an_ordinary_media_query_is_left_alone():
    css = TWO_THEMES + '@media (min-width: 720px) { .g-grid { gap: 8px; } }'
    assert grounds(parse_blocks(css)) == ["hazard", "page"]


def test_comments_do_not_become_declarations():
    css = ':root { /* --ink-ok: #ffffff; a note, not a token */ --paper: #000; }'
    assert "--ink-ok" not in environment(parse_blocks(css), "dark", None)


# ------------------------------------------------------ ordinary declarations

PAINT = """
[data-ground] { background-color: var(--g-bg); color: var(--g-ink); }
[data-ground][data-ground-paint="none"] { background-color: transparent; }
"""


def test_parse_rules_keeps_the_properties_parse_blocks_throws_away():
    """A rule that paints declares no custom property, so the custom property
    view of the file cannot see whether painting is there at all."""
    rules = parse_rules(PAINT)
    assert rules[0][1] == {"background-color": "var(--g-bg)",
                           "color": "var(--g-ink)"}
    assert parse_blocks(PAINT)[0][1] == {}


def test_parse_rules_reads_the_selector_the_same_way():
    rules = parse_rules(PAINT)
    assert rules[1][0] == ['[data-ground][data-ground-paint="none"]']


def test_a_commented_out_rule_declares_nothing():
    """Commenting a rule out while debugging and not putting it back is the
    ordinary way painting regresses, and a text search would not notice."""
    rules = parse_rules("/*" + PAINT + "*/\n:root { --paper: #000; }")
    assert all("background-color" not in declarations
               for _, declarations in rules)


def test_a_declaration_inside_a_value_is_not_read_as_a_declaration():
    css = ':root { --font-body: \'Instrument Sans\', system-ui, sans-serif; }'
    assert parse_rules(css)[0][1] == {
        "--font-body": "'Instrument Sans', system-ui, sans-serif"}


# ---------------------------------------------------------------- resolution

def test_resolves_a_literal():
    env = environment(parse_blocks(TWO_THEMES), "dark", "page")
    assert resolve("--paper", env) == "#000000"


def test_resolves_a_var_chain_to_the_ground_it_is_read_on():
    blocks = parse_blocks(TWO_THEMES)
    assert resolve("--g-bg", environment(blocks, "dark", "page")) == "#000000"
    assert resolve("--g-bg", environment(blocks, "light", "page")) == "#ffffff"
    assert resolve("--g-bg", environment(blocks, "dark", "hazard")) == "#f2ab1e"


def test_resolves_a_chain_several_links_long():
    css = ':root { --a: #123456; --b: var(--a); --c: var(--b); }'
    assert resolve("--c", environment(parse_blocks(css), "dark", None)) == "#123456"


def test_uses_the_fallback_when_the_named_token_is_missing():
    css = ':root { --line: var(--nothing, #abcdef); }'
    assert resolve("--line", environment(parse_blocks(css), "dark", None)) == "#abcdef"


def test_an_undefined_token_resolves_to_nothing():
    assert resolve("--absent", {}) is None


def test_a_cycle_resolves_to_nothing_rather_than_hanging():
    css = ':root { --a: var(--b); --b: var(--a); }'
    env = environment(parse_blocks(css), "dark", None)
    assert resolve("--a", env) is None


def test_a_var_inside_a_larger_value_is_substituted_in_place():
    css = ':root { --line-colour: #3a342b; --bd: 1px solid var(--line-colour); }'
    env = environment(parse_blocks(css), "dark", None)
    assert resolve("--bd", env) == "1px solid #3a342b"


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
