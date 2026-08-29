#!/usr/bin/env python3
"""The two ceilings in rule 6 that no linter measures.

A source file may not exceed 300 lines and a function may not exceed 50. Ruff
carries the other three ceilings, cyclomatic complexity, parameter count and
nesting depth, and `ruff.toml` holds those numbers. Nothing priced in
docs/decisions/0005-file-and-function-ceilings.md counts either of the two here:
the closest measures a function in logical lines rather than the physical lines
rule 6 is written in, and reports 46 where the file says 53.

Both counts are deliberately the naive ones, because they are the counts a
person makes when they open the file and look at the line numbers.

    tools/ceilings/check_ceilings.py

Reads the file list from git, so anything untracked is out of scope and so is
anything in .gitignore. Exit code is 1 if any file or function is over, or if an
exemption no longer has anything to exempt.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

FILE_CEILING = 300
FUNCTION_CEILING = 50

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXEMPTIONS = pathlib.Path(__file__).resolve().parent / "exemptions.txt"

# What rule 6 means by a source file. Markdown is not in it: prose is governed by
# rule 11 and the gate for that is tools/voice-check. Neither is anything under
# db/migrations, which rule 6 exempts by name.
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue",
                   ".css", ".html", ".sql", ".sh",
                   ".yaml", ".yml", ".toml", ".caddyfile"}
SOURCE_NAMES = {"Makefile", "Caddyfile", "commit-msg"}
EXEMPT_DIRECTORIES = ("db/migrations/",)


def tracked_files() -> list[pathlib.Path]:
    listing = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                             capture_output=True, text=True, check=True)
    return [pathlib.Path(line) for line in listing.stdout.splitlines() if line]


def is_source(path: pathlib.Path) -> bool:
    if str(path).startswith(EXEMPT_DIRECTORIES):
        return False
    return path.suffix in SOURCE_SUFFIXES or path.name in SOURCE_NAMES


def read_exemptions() -> dict[str, str]:
    """Path to reason, and a line with no reason is an error rather than a path.

    Rule 6: a file past the ceiling carries a justification naming the reason,
    and "it is all related" is not a reason. Accepting a bare path would let the
    next red build be cleared by appending one word to this file.
    """
    allowed = {}
    for number, line in enumerate(EXEMPTIONS.read_text().splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        path, separator, reason = line.partition("  ")
        if not separator or not reason.strip():
            raise SystemExit(
                f"tools/ceilings/exemptions.txt:{number}: no reason given for "
                f"{path.strip()!r}. Rule 6 wants the reason, separated from the "
                "path by two spaces")
        allowed[path.strip()] = reason.strip()
    return allowed


def long_functions(path: pathlib.Path) -> list[tuple[str, int, int]]:
    """Every function in a Python file that runs past the ceiling.

    Measured from `def` to the last line of the body, which is what a reader
    counts. A decorator above the `def` is not part of the function.
    """
    tree = ast.parse((ROOT / path).read_text())
    over = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        lines = node.end_lineno - node.lineno + 1
        if lines > FUNCTION_CEILING:
            over.append((node.name, node.lineno, lines))
    return over


def check_file_lengths(files: list[pathlib.Path], allowed: dict[str, str]) -> list[str]:
    findings = []
    used = set()
    for path in files:
        length = len((ROOT / path).read_text().splitlines())
        if length <= FILE_CEILING:
            continue
        if str(path) in allowed:
            used.add(str(path))
            continue
        findings.append(f"{path}: {length} lines, over the ceiling of {FILE_CEILING}. "
                        "Split it, or add it to tools/ceilings/exemptions.txt with a reason")
    for path in sorted(set(allowed) - used):
        findings.append(f"{path}: exempted from the file ceiling and no longer over it. "
                        "Remove the line from tools/ceilings/exemptions.txt")
    return findings


def check_function_lengths(files: list[pathlib.Path]) -> list[str]:
    findings = []
    for path in files:
        if path.suffix != ".py":
            continue
        for name, line, length in long_functions(path):
            findings.append(f"{path}:{line}: {name} is {length} lines, over the "
                            f"ceiling of {FUNCTION_CEILING}. It is two functions")
    return findings


def main() -> int:
    files = [p for p in tracked_files() if is_source(p)]
    allowed = read_exemptions()
    findings = check_file_lengths(files, allowed) + check_function_lengths(files)
    for finding in findings:
        print(finding)
    if findings:
        print(f"\n{len(findings)} over the ceilings in rule 6 of CLAUDE.md.")
        return 1
    python_files = sum(1 for p in files if p.suffix == ".py")
    # Named precisely, because the function ceiling is measured over Python and
    # nothing else. Saying "every function" would report a JavaScript function
    # of any length as checked. ADR 0006 says when that gate arrives.
    print(f"{len(files)} source files under {FILE_CEILING} lines, and every "
          f"function in the {python_files} Python files under {FUNCTION_CEILING}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
