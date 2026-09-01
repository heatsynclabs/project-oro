#!/usr/bin/env python3
"""Plant one broken citation at a time and require the checker to report it.

    python3 tools/citations/test_citations.py

Needs python3 and nothing else. A gate that has only ever been run against the
one document it guards proves nothing about what it would catch, and this one
was written after a first draft would have renumbered a correct citation into
the wrong file.
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import check_citations as citations  # noqa: E402

CONTRACT = """openapi: 3.1.1
info:
  title: A contract
  description: |
    Prose.
paths:
  /me:
    get:
      summary: Read yourself
  /me/cards:
    get:
      summary: Your cards
components:
  schemas:
    Member:
      type: object
      properties:
        oriented_by:
          type: string
    ProblemDetail:
      type: object
      properties:
        detail:
          type: string
      examples:
        - detail: A sentence.
"""


def run(notes_text: str, fix: bool = False) -> tuple[int, str, str]:
    """The checker over a throwaway pair of files, with its output captured."""
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        notes = root / "contract-review-notes.md"
        contract = root / "members-v1.yaml"
        notes.write_text(notes_text)
        contract.write_text(CONTRACT)
        was = (citations.NOTES, citations.CONTRACT)
        citations.NOTES, citations.CONTRACT = notes, contract
        said = io.StringIO()
        try:
            with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
                code = citations.report(fix)
            return code, said.getvalue(), notes.read_text()
        finally:
            citations.NOTES, citations.CONTRACT = was


def test_a_citation_that_lands_is_quiet():
    code, said, _ = run("`Member` (line 15) is a schema.\n")
    assert code == 0, said
    assert "1 citation(s) land, 0 adrift" in said, said


def test_a_citation_that_is_adrift_is_reported():
    code, said, _ = run("`Member` (line 99) is a schema.\n")
    assert code == 1, said
    assert "`Member` says line 99 and is at 15" in said, said


def test_a_wrapped_citation_is_read():
    """`Tier.sort_order`\\n(line N) is in the real document and a line by line
    read walks past it, which is how the first draft of this checker missed one.
    """
    code, said, _ = run("The thing named `Member`\n(line 99) is a schema.\n")
    assert code == 1, said
    assert "`Member` says line 99 and is at 15" in said, said


def test_a_property_is_found_inside_its_own_schema():
    code, said, _ = run("`Member.oriented_by` (line 18) is a property.\n")
    assert code == 0, said


def test_a_property_name_that_repeats_takes_the_outermost():
    """ProblemDetail has `detail` as a property and again inside its example."""
    code, said, _ = run("`ProblemDetail.detail` (line 23) is a property.\n")
    assert code == 0, said


def test_a_method_and_a_path_finds_the_method_under_that_path():
    code, said, _ = run("`GET /me/cards` (line 11) is an operation.\n")
    assert code == 0, said


def test_an_anchor_naming_nothing_is_refused():
    code, said, _ = run("`Nonexistent` (line 3) is not in the contract.\n")
    assert code == 1, said
    assert "no line" in said, said
    assert "0 adrift, 1 unresolved" in said, said


def test_a_citation_naming_another_file_is_left_alone():
    """The convention in the notes, and the defect the first draft would have
    caused: a bare (line 170) three sentences after a SQL file was named.
    """
    code, said, _ = run("`Member` (`012_close_remaining.sql` line 170) is a "
                        "function argument.\n")
    assert code == 0, said
    assert "0 citation(s) land" in said, said


def test_a_frozen_block_is_not_read():
    code, said, _ = run(
        "`Member` (line 15) is a schema.\n"
        f"{citations.FROZEN_OPEN}\n"
        "`Member` (line 99) was where it used to be.\n"
        f"{citations.FROZEN_CLOSE}\n")
    assert code == 0, said
    assert "1 citation(s) land, 0 adrift" in said, said
    assert "3 line(s) frozen" in said, said


def test_the_references_nothing_anchors_are_counted_out_loud():
    """A gate covering part of a file and not saying which part reads as
    covering all of it."""
    code, said, _ = run("`Member` (line 15) is a schema, and line 42 says more.\n")
    assert code == 0, said
    assert "1 line reference(s) carry no backticked anchor" in said, said


def test_fix_rewrites_the_number_and_nothing_else():
    code, said, after = run("A note about `Member` (line 99) and a full stop.\n",
                            fix=True)
    assert code == 0, said
    assert after == "A note about `Member` (line 15) and a full stop.\n", repr(after)


def test_fix_leaves_a_frozen_number_alone():
    text = ("`Member` (line 99) is adrift.\n"
            f"{citations.FROZEN_OPEN}\n"
            "`Member` (line 77) is the record.\n"
            f"{citations.FROZEN_CLOSE}\n")
    code, said, after = run(text, fix=True)
    assert code == 0, said
    assert "(line 15) is adrift" in after, after
    assert "(line 77) is the record" in after, after


def _run() -> int:
    checks = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    failed = []
    for name, fn in checks:
        try:
            fn()
        except AssertionError as exc:
            failed.append(name)
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
