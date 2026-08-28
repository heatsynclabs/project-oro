#!/usr/bin/env python3
"""Tests for the prose gate.

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


def rules(text: str, path: Path = MD, commit: bool = False) -> set[str]:
    return {f.rule for f in lint(text, path, commit)}


def errors(text: str, path: Path = MD, commit: bool = False) -> set[str]:
    return {f.rule for f in lint(text, path, commit) if f.level == "error"}


# ---------------------------------------------------------------- attribution

def test_rejects_claude_coauthor_trailer():
    msg = "Add the door reconcile loop\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
    assert "attribution" in errors(msg, COMMIT, commit=True)


def test_rejects_generated_with_trailer():
    assert "attribution" in errors("Generated with Claude Code\n", COMMIT, commit=True)


def test_rejects_session_trailer():
    assert "attribution" in errors("Claude-Session: https://example.test/x", COMMIT, commit=True)


def test_rejects_other_ai_tools():
    for msg in ("Co-authored-by: GitHub Copilot <c@example.test>",
                "Assisted-By: GPT-4",
                "AI-Generated: yes"):
        assert "attribution" in errors(msg, COMMIT, commit=True), msg


def test_reference_file_may_quote_the_banned_trailers():
    """The ban list has to name what it bans. Safe, because a commit message
    cannot claim the pragma: --commit-msg ignores it."""
    text = "voice-check: reference\n\nCo-Authored-By: Claude\n"
    assert "attribution" not in errors(text)


def test_commit_mode_ignores_the_reference_pragma():
    text = "voice-check: reference\n\nCo-Authored-By: Claude\n"
    assert "attribution" in errors(text, COMMIT, commit=True)


def test_accepts_a_human_coauthor():
    msg = "Add the door reconcile loop\n\nCo-authored-by: A Human <human@example.test>\n"
    assert errors(msg, COMMIT, commit=True) == set()


# ----------------------------------------------------------------------- dash

def test_rejects_em_dash():
    assert "dash" in errors("The door is open, mostly — it depends on the card.")


def test_rejects_en_dash():
    assert "dash" in errors("Open hours run 6–10 on Tuesday nights at the lab.")


def test_rejects_double_hyphen_standing_in_for_em_dash():
    assert "dash-dodge" in errors("The controller answers -- when it feels like it.")


def test_rejects_spaced_hyphen_in_prose():
    assert "dash-dodge" in errors("The reconcile loop runs - every fifteen minutes.")


def test_allows_command_line_flags():
    text = "Run `docker compose up --build` to start the stack.\n\nUse --strict in CI."
    assert "dash-dodge" not in errors(text)


def test_allows_hyphenated_words_and_yaml_markers():
    assert errors("A well-maintained, self-hosted service.\n\n---\ntitle: x\n---\n") == set()


def test_dash_suppressed_by_line_pragma():
    text = "The controller answers -- eventually.  <!-- voice-ok: quoting a log line -->"
    assert "dash-dodge" not in errors(text)


# ---------------------------------------------------------------------- emoji

def test_rejects_emoji():
    assert "emoji" in errors("Door status: 🔓 unlocked")


def test_rejects_robot_emoji_as_attribution():
    assert "attribution" in errors("🤖 Generated with Claude Code", COMMIT, commit=True)


def test_allows_plain_text_status():
    assert errors("Door status: unlocked") == set()


# --------------------------------------------------------------- banned words

def test_rejects_marketing_vocabulary():
    for word in ("unleash", "seamless", "cutting-edge", "innovation",
                 "thrilled to announce", "world-class"):
        assert "banned-word" in errors(f"The new portal is {word} for members."), word


def test_rejects_militarised_language():
    assert "militarised" in errors("The auth layer is battle tested in production.")


def test_allows_ordinary_technical_prose():
    text = ("The door service reconciles the card table every fifteen minutes. "
            "When the controller does not answer, it retries twice and logs the failure.")
    assert errors(text) == set()


def test_ignores_identifiers_in_code():
    """A variable named innovationScore is code, not prose, and must not trip."""
    code = "const innovationScore = 1;\nconst seamlessTransition = true;\n"
    assert errors(code, TS) == set()


def test_still_catches_banned_words_in_code_comments():
    code = "// This unleashes the full power of the door controller.\nconst x = 1;\n"
    assert "banned-word" in errors(code, TS)


def test_still_catches_banned_words_in_ui_strings():
    code = 'const label = "Unleash your creativity at the lab";\n'
    assert "banned-word" in errors(code, TS)


def test_catches_prose_in_python_docstrings():
    code = '"""Seamlessly synchronise the card table with the controller."""\n'
    assert "banned-word" in errors(code, PY)


# --------------------------------------------------------------- construction

def test_rejects_not_just_x_its_y():
    assert "construction" in errors("It is not just a members site, it is a whole platform.")


def test_rejects_rhetorical_opener():
    assert "construction" in errors("Ever wanted to learn welding? Come to the lab.")


def test_rejects_learning_journey():
    assert "construction" in errors("Track your journey from beginner to certified.")


def test_allows_a_literal_journey():
    assert "construction" not in errors("The drive is a two hour journey by road.")


# --------------------------------------------------------------------- safety

def test_rejects_softened_certification_requirement():
    assert "safety" in errors("We recommend you get certified before using the laser.")


def test_accepts_a_flat_requirement():
    assert errors("Certification is required before you use the laser.") == set()


# ------------------------------------------------------------------ exclusion

def test_rejects_exclusion_by_implication():
    assert "exclusion" in errors("The advanced bench is for serious makers.")


def test_accepts_the_flat_welcome():
    text = "Everyone is welcome. You do not need experience to come to open hours."
    assert errors(text) == set()


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
