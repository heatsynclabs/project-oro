#!/usr/bin/env python3
"""Regression tests for defects found in the prose gate.

voice-check: reference
Fixtures here are deliberately bad copy, so the gate must not lint this file.

Each test names the bug it locks down. A fix without a test is a fix that comes
back.

    python3 tools/voice-check/test_regressions.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks import lint  # noqa: E402
from extract import prose_of  # noqa: E402

MD = Path("sample.md")
TS = Path("sample.ts")
PY = Path("sample.py")
SQL = Path("sample.sql")
COMMIT = Path("COMMIT_EDITMSG")


def findings(text, path=MD, commit=False):
    return lint(text, path, commit)


def rules_of(text, path=MD, commit=False):
    return {f.rule for f in findings(text, path, commit)}


def errors(text, path=MD, commit=False):
    return {f.rule for f in findings(text, path, commit) if f.level == "error"}


# ---------------------------------------------------------------------------
# Bug 1: dash-dodge matched across a newline, so a sentence followed by a
# markdown bullet read as a substituted em dash.
# ---------------------------------------------------------------------------

def test_sentence_followed_by_a_bullet_is_not_a_dash_dodge():
    text = "The options were discussed\n\n- Storybook for the interactive parts\n"
    assert "dash-dodge" not in errors(text)


def test_bullet_list_of_several_items_is_not_a_dash_dodge():
    text = "\n".join(["Candidates considered", "", "- Caddy for the proxy",
                      "- Traefik for the proxy", "- nginx with acme"])
    assert "dash-dodge" not in errors(text)


def test_a_real_spaced_hyphen_on_one_line_is_still_caught():
    assert "dash-dodge" in errors("The reconcile loop runs - every fifteen minutes.")


# ---------------------------------------------------------------------------
# Bug 2: the emoji ranges swept in arrows and dingbats, so a mapping arrow and
# a checklist tick were errors.
# ---------------------------------------------------------------------------

def test_rightwards_arrow_is_not_an_emoji():
    assert "emoji" not in errors("The layering is apps → packages → services.")


def test_check_and_cross_marks_are_not_emoji():
    assert "emoji" not in errors("| bcrypt import | ✓ |\n| pepper | ✗ |")


def test_a_real_emoji_is_still_caught():
    assert "emoji" in errors("Door status: \U0001F513 unlocked")


def test_the_robot_emoji_is_still_caught_as_attribution():
    assert "attribution" in errors("\U0001F916 Generated with Claude Code",
                                   COMMIT, commit=True)


# ---------------------------------------------------------------------------
# Bug 3: findings from stripped prose had no line number, so they could not be
# located and the documented voice-ok escape hatch did not work on them.
# ---------------------------------------------------------------------------

def test_every_finding_carries_a_line_number():
    text = ("# A heading\n\n"
            "Some ordinary prose that is fine.\n\n"
            "```\ncode block\n```\n\n"
            "This portal is seamless and full of innovation.\n")
    found = [f for f in findings(text) if f.level == "error"]
    assert found, "expected at least one error"
    assert all(f.line is not None for f in found), \
        [f"{f.rule}: {f.message}" for f in found if f.line is None]


def test_the_line_number_points_at_the_offending_line():
    text = "line one is fine\nline two is fine\nthis portal is seamless\n"
    found = [f for f in findings(text) if f.rule == "banned-word"]
    assert found and found[0].line == 3, found


def test_voice_ok_suppresses_a_finding_in_stripped_prose():
    text = ("# A heading\n\n"
            "```\ncode\n```\n\n"
            "This portal is seamless.  <!-- voice-ok: quoting a vendor page -->\n")
    assert "banned-word" not in errors(text)


def test_masking_preserves_length_and_line_count():
    raw = "# Heading\n\n```\ncode here\n```\n\nReal prose lives here.\n"
    masked = prose_of(raw, ".md")
    assert len(masked) == len(raw)
    assert masked.count("\n") == raw.count("\n")


# ---------------------------------------------------------------------------
# Bug 4: a comment claimed BANNED_SOFT was matched only outside code spans.
# There was no such path. The list is now one list and the comment is gone.
# ---------------------------------------------------------------------------

def test_leverage_is_banned_in_prose():
    assert "banned-word" in errors("We should leverage the existing API.")


def test_leverage_is_not_banned_as_an_identifier():
    assert "banned-word" not in errors("const leverageRatio = 1;\n", TS)


# ---------------------------------------------------------------------------
# Every occurrence, not only the first.
# ---------------------------------------------------------------------------

def test_reports_every_occurrence_of_a_banned_word():
    text = ("The portal is seamless.\n"
            "The API is seamless.\n"
            "The door is seamless.\n")
    hits = [f for f in findings(text) if f.rule == "banned-word"]
    assert len(hits) == 3, [f.line for f in hits]
    assert sorted(f.line for f in hits) == [1, 2, 3]


# ---------------------------------------------------------------------------
# Prose extraction should catch sentences, not identifiers, paths, or SQL.
# ---------------------------------------------------------------------------

def test_a_long_import_path_is_not_prose():
    code = "import { thing } from '../../../packages/ui/src/components/thing';\n"
    assert errors(code, TS) == set()


def test_a_long_sql_fragment_is_not_prose():
    sql = "SELECT controller_slot, tag_number FROM cards WHERE active ORDER BY 1;\n"
    assert errors(sql, SQL) == set()


def test_a_sentence_in_a_sql_comment_is_still_prose():
    sql = "-- This seamless approach synchronises the card table.\nSELECT 1;\n"
    assert "banned-word" in errors(sql, SQL)


def test_a_ui_sentence_in_typescript_is_still_prose():
    code = 'const msg = "Unleash your creativity at the lab today";\n'
    assert "banned-word" in errors(code, TS)


# ---------------------------------------------------------------------------
# The quote block, for somebody else's words.
# ---------------------------------------------------------------------------

def test_quote_block_exempts_somebody_elses_words():
    text = ("Our own prose is clean here.\n\n"
            "<!-- voice-check: quote -->\n"
            "A reviewer said the auth layer is battle tested and world class.\n"
            "<!-- /voice-check: quote -->\n\n"
            "And our prose continues.\n")
    assert errors(text) == set()


def test_quote_block_does_not_exempt_the_rest_of_the_file():
    text = ("<!-- voice-check: quote -->\nsomeone said seamless\n"
            "<!-- /voice-check: quote -->\n\n"
            "But this portal is also seamless.\n")
    assert "banned-word" in errors(text)


def test_quote_block_still_checks_attribution():
    """A quote block narrows the voice rules. It does not license a trailer."""
    text = ("<!-- voice-check: quote -->\n"
            "Co-Authored-By: Claude <noreply@anthropic.test>\n"
            "<!-- /voice-check: quote -->\n")
    assert "attribution" in errors(text)


def test_unclosed_quote_block_runs_to_end_of_file():
    text = "Clean prose.\n\n<!-- voice-check: quote -->\nseamless innovation\n"
    assert errors(text) == set()


# ---------------------------------------------------------------------------
# The gate obeys the rules it enforces.
# ---------------------------------------------------------------------------

def test_no_source_file_exceeds_the_line_ceiling():
    """Rule 6. The gate that enforces a 300 line ceiling was 499 lines."""
    here = Path(__file__).resolve().parent
    over = {f.name: sum(1 for _ in f.open())
            for f in here.glob("*.py")
            if sum(1 for _ in f.open()) > 300}
    assert not over, over


def test_the_repository_docs_pass_the_gate():
    root = Path(__file__).resolve().parents[2]
    for doc in [root / "CLAUDE.md", root / "ATTRIBUTIONS.md"]:
        if not doc.exists():
            continue
        bad = [f for f in lint(doc.read_text(encoding="utf-8"), doc)
               if f.level == "error"]
        assert not bad, [f.render(doc.name) for f in bad]


def _run() -> int:
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in fns:
        try:
            fn()
        except AssertionError as exc:
            failed.append(name)
            print(f"FAIL {name}\n     {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}\n     {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - len(failed)}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
