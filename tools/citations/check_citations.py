#!/usr/bin/env python3
"""Every `thing` (line N) in the review notes lands on that thing.

    tools/citations/check_citations.py           report, and change nothing
    tools/citations/check_citations.py --fix     rewrite the numbers

docs/api/contract-review-notes.md cites the contract by line number, and its own
preamble says a citation landing in the wrong place is a defect rather than
evidence that the finding is stale. Every edit to docs/api/members-v1.yaml moves
some of them, and hand correction has been done twice and drifted twice.
Measured on 2026-08-31 before this existed: twenty five citations carry an
anchor, one of them landed, and the rest were adrift by as much as 150 lines.

So the number is derived rather than maintained. The backtick before it is the
authority: `MyCard` (line 1779) says the definition of MyCard is at 1779, and
this file finds MyCard in the contract and compares. Which means a citation this
cannot resolve is also a defect, because a reader cannot resolve it either.

**No YAML parser.** The contract is 2,300 lines of consistently indented YAML
and what is needed here is where a key sits, which no parser hands back without
work. PyYAML would be a dependency for the repository to carry, patch and
attribute under rule 9, and it discards line numbers. So this walks the text and
uses indentation, and it refuses rather than guessing whenever the walk finds
none or more than one.

Two blocks are exempt and are marked in the file itself, in the shape the prose
gate already uses for a quotation. Findings 1 and 3 keep a record of the state
before an edit, line numbers included, and renumbering those would destroy the
before they exist to show.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
NOTES = ROOT / "docs/api/contract-review-notes.md"
CONTRACT = ROOT / "docs/api/members-v1.yaml"

# `TOKEN` (line N). The backticked token is the anchor and N is derived from it.
#
# \s+ rather than a space, and matched over the whole file rather than line by
# line, because a citation wraps. `Tier.sort_order`\n(line 1318) is in this
# document and a line by line read walks straight past it, which is the same
# defect as the plain grep that found five copies of a sentence where six were
# wrapped across two lines. That one is recorded in finding 3.
#
# Parentheses are required, and that is what keeps this away from the citations
# into other files. The convention in the notes is that a reference to another
# file names it, as `004_security.sql` line 88, and only the contract is cited
# bare. Finding 6 broke that convention with three bare references into
# 012_close_remaining.sql, one of which named sort_order, which resolves in the
# contract as well. This tool would have renumbered a correct citation to point
# at the wrong file. The convention is now followed there.
CITATION = re.compile(r'`([^`]{1,60})`\s+\(line (\d+)\)')

# Every other way this file names a line, counted and reported so that a run
# saying "every citation lands" cannot be read as "every line number is right".
ANY_NUMBER = re.compile(r'\blines? \d+')

FROZEN_OPEN = "<!-- citations: frozen -->"
FROZEN_CLOSE = "<!-- /citations: frozen -->"


class Unresolved(Exception):
    """The anchor names nothing, or names more than one thing."""


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def block(lines: list[str], start: int) -> range:
    """The lines nested under the key on line `start`, one indexed."""
    outer = indent_of(lines[start - 1])
    end = start
    for number in range(start + 1, len(lines) + 1):
        line = lines[number - 1]
        if not line.strip():
            continue
        if indent_of(line) <= outer:
            break
        end = number
    return range(start + 1, end + 1)


def key_lines(lines: list[str], name: str, span: range | None = None) -> list[int]:
    """Line numbers whose YAML key is exactly `name`."""
    wanted = re.compile(r"^\s*" + re.escape(name) + r":")
    numbers = span if span is not None else range(1, len(lines) + 1)
    return [n for n in numbers if wanted.match(lines[n - 1])]


def shallowest(lines: list[str], found: list[int]) -> list[int]:
    """Of several keys with one name, the ones nearest the surface.

    `ProblemDetail.detail` finds three: the property, the same name inside the
    per field `errors` items, and the example that shows a value for it. What
    the citation means is the property, which is the outermost. Without this the
    only honest answer was to refuse, and there is no way to write that citation
    that would have resolved.
    """
    if not found:
        return found
    nearest = min(indent_of(lines[n - 1]) for n in found)
    return [n for n in found if indent_of(lines[n - 1]) == nearest]


def one(lines: list[str], name: str, span: range | None, token: str) -> int:
    found = shallowest(lines, key_lines(lines, name, span))
    if len(found) == 1:
        return found[0]
    if not found:
        raise Unresolved(
            f"`{token}` names {name}, and no line in {CONTRACT.name} has that "
            "key. Either the thing was renamed or the citation has a typo.")
    raise Unresolved(
        f"`{token}` names {name}, and {len(found)} lines in {CONTRACT.name} "
        f"have that key: {', '.join(str(n) for n in found[:8])}. Write the "
        "citation as Schema.property so it says which one.")


def anchor(lines: list[str], token: str) -> int:
    """The line in the contract that `token` names.

    Four shapes, and every citation in the notes is one of them. A method and a
    path is the method key inside that path. A schema and a property is the
    property key inside that schema. A path on its own and a name on its own are
    the key itself, and a name on its own has to be unique in the document.
    """
    token = token.strip()
    if " " in token:
        method, _, path = token.partition(" ")
        return one(lines, method.lower(), block(lines, one(lines, path, None, token)), token)
    if "." in token:
        holder, _, member = token.partition(".")
        return one(lines, member, block(lines, one(lines, holder, None, token)), token)
    return one(lines, token, None, token)


def frozen_lines(notes: list[str]) -> set[int]:
    """Line numbers inside a marked block, which nothing here touches."""
    inside = False
    held = set()
    for number, line in enumerate(notes, 1):
        if FROZEN_OPEN in line:
            inside = True
        if inside:
            held.add(number)
        if FROZEN_CLOSE in line:
            inside = False
    return held


def read() -> tuple[list[str], list[str]]:
    return (NOTES.read_text().splitlines(), CONTRACT.read_text().splitlines())


def report(fixing: bool) -> int:
    notes, contract = read()
    held = frozen_lines(notes)
    text = "\n".join(notes)
    adrift = unresolved = landed = 0
    replacements = []

    for found in CITATION.finditer(text):
        token, said = found.group(1), found.group(2)
        at = text.count("\n", 0, found.start()) + 1
        if at in held:
            continue
        try:
            where = anchor(contract, token)
        except Unresolved as why:
            unresolved += 1
            print(f"{NOTES.name}:{at}  {why}")
            continue
        if where == int(said):
            landed += 1
            continue
        adrift += 1
        print(f"{NOTES.name}:{at}  `{token}` says line {said} and is at {where}")
        replacements.append((found.start(2), found.end(2), str(where)))

    if fixing and replacements:
        for start, end, better in reversed(replacements):
            text = text[:start] + better + text[end:]
        NOTES.write_text(text + "\n")
        print(f"\n{NOTES.name} rewritten: {len(replacements)} citation(s) "
              "renumbered.")
        return 0

    loose = sum(len(ANY_NUMBER.findall(line)) for number, line in enumerate(notes, 1)
                if number not in held) - landed - adrift - unresolved
    print(f"\n{landed} citation(s) land, {adrift} adrift, {unresolved} "
          f"unresolved, {len(held)} line(s) frozen and not read.")
    # Said every run, green or red. A gate that covers part of a file and does
    # not say which part is one people read as covering all of it.
    print(f"{loose} line reference(s) carry no backticked anchor, so nothing "
          "here checks them.")
    if adrift or unresolved:
        print("\nRun tools/citations/check_citations.py --fix for the adrift "
              "ones. An unresolved one is a citation a reader cannot follow "
              "either, and it wants qualifying by hand.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(report("--fix" in sys.argv[1:]))
