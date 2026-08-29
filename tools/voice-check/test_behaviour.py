#!/usr/bin/env python3
"""Tests for the rhythm, structure, and path handling of the prose gate.

voice-check: reference
This file's fixtures are deliberately bad copy, so the gate must not lint it.

Every rule gets two tests: copy that must fail, and copy that must pass. A rule
with only a failing test is how a linter ends up rejecting legitimate writing.

    python3 -m pytest tools/voice-check/ -q
    python3 tools/voice-check/test_voice_check.py     (no pytest needed)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from voice_check import lint  # noqa: E402

MD = Path("sample.md")
TS = Path("sample.ts")
PY = Path("sample.py")
COMMIT = Path("COMMIT_EDITMSG")
SH = Path("script.sh")


def rules(text: str, path: Path = MD, commit: bool = False) -> set[str]:
    return {f.rule for f in lint(text, path, commit)}


def errors(text: str, path: Path = MD, commit: bool = False) -> set[str]:
    return {f.rule for f in lint(text, path, commit) if f.level == "error"}


# --------------------------------------------------------------------- rhythm

def test_warns_on_uniform_sentence_length():
    line = "The door controller opens the front entrance every single time. "
    assert "rhythm" in rules(line * 10)


def test_warns_on_repeated_triads():
    text = ("The portal shows profile, cards, and payments. "
            "Admins manage members, roles, and approvals. "
            "The door reports status, alarms, and logs. "
            "The stack uses Postgres, Caddy, and Docker.")
    assert "triad" in rules(text)


def test_warns_on_summary_closing():
    text = "The door service reconciles the card table.\n\n" + \
           "In summary, the system keeps the controller and the database agreed " \
           "with each other over time, which is the point of the whole exercise."
    assert "closing" in rules(text)


def test_does_not_flag_a_definition_list_as_emphasis():
    """Bold at the start of a line is a term being defined, not emphasis."""
    text = "\n\n".join(f"**term {i}**\n: The definition of term {i} goes here "
                        f"and runs on for a while." for i in range(8))
    assert "emphasis" not in rules(text)


def test_does_not_flag_bold_labels_in_a_bullet_list():
    """`- **Licence:** MIT` is a labelled list item, not mid sentence emphasis."""
    text = "\n".join(f"- **Field {i}:** the value for field {i} goes here."
                      for i in range(9))
    assert "emphasis" not in rules(text)


def test_warns_on_bold_mid_sentence():
    text = " ".join(f"The door is **very {w}** when the controller answers."
                    for w in ("open", "closed", "locked", "unlocked", "armed"))
    assert "emphasis" in rules(text)


def test_warns_on_filler_transitions():
    text = ("Moreover the door stays open. The card table syncs on a timer. "
            "Moreover the alarm reports its state to the service every minute.")
    assert "transition" in rules(text)


def test_rhythm_warnings_are_not_errors():
    line = "The door controller opens the front entrance every single time. "
    assert errors(line * 10) == set()


# ------------------------------------------------------------------ structure

def test_rejects_img_without_alt():
    assert "a11y" in errors('<img src="/door.png">', Path("page.html"))


def test_rejects_html_without_lang():
    assert "a11y" in errors("<html><head></head><body></body></html>", Path("page.html"))


def test_accepts_an_accessible_image():
    html = ('<html lang="en"><head><meta name="viewport" content="width=device-width">'
            '</head><body><img src="/door.png" alt="The front door"></body></html>')
    assert errors(html, Path("page.html")) == set()


# ------------------------------------------------------------------ reference

def test_reference_pragma_exempts_the_ban_list_itself():
    text = "voice-check: reference\n\nBanned words: unleash, seamless, innovation."
    assert errors(text) == set()


def test_reference_pragma_only_counts_in_the_first_40_lines():
    text = "\n" * 45 + "voice-check: reference\n\nThe portal is seamless."
    assert "banned-word" in errors(text)


# ----------------------------------------------------------------- self check

def test_the_repository_rules_file_passes_its_own_gate():
    """CLAUDE.md documents the bans, so it carries the reference pragma. It must
    still be free of attribution trailers and accessibility defects."""
    root = Path(__file__).resolve().parents[2]
    claude = root / "CLAUDE.md"
    if not claude.exists():
        return
    found = lint(claude.read_text(encoding="utf-8"), claude)
    assert [f for f in found if f.level == "error"] == []


# ------------------------------------------------------------ path expansion

def test_expand_walks_a_directory():
    """A directory that silently checks nothing is how a misconfigured CI path
    passes without looking at anything."""
    from voice_check import expand
    root = Path(__file__).resolve().parents[2] / "docs"
    if not root.exists():
        return
    found = expand(root)
    assert found, "expanding docs/ found no files"
    assert all(f.is_file() for f in found)


def test_expand_skips_vendor_directories():
    from voice_check import expand, SKIP_DIRS
    assert "node_modules" in SKIP_DIRS and ".git" in SKIP_DIRS


def test_expand_passes_a_named_file_through_whatever_its_suffix():
    from voice_check import expand
    me = Path(__file__).resolve()
    assert expand(me) == [me]


def test_expand_reports_a_missing_path():
    from voice_check import expand
    assert expand(Path("/nonexistent/path/xyz")) == []


# ------------------------------------------------------------------ shell

def test_lints_a_comment_in_a_shell_script():
    assert "banned-word" in errors("#!/bin/sh\n# a seamless way to do it\n", SH)


def test_leaves_shell_code_alone():
    assert "banned-word" not in errors('#!/bin/sh\ngrep -c "seamless" "$f"\n', SH)


def test_shell_scripts_are_reached_by_a_directory_walk():
    from voice_check import CHECKED_SUFFIXES
    assert ".sh" in CHECKED_SUFFIXES


def _run() -> int:
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in fns:
        try:
            fn()
        except AssertionError as exc:
            failed.append((name, exc))
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - len(failed)}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
