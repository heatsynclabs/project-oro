#!/usr/bin/env python3
"""Prose gate for Project ORO.

voice-check: reference

Checks documentation, UI copy, code comments, and commit messages against the
voice rules in docs/conventions/voice.md, and against the structural signatures
of machine written prose.

    voice_check.py FILE_OR_DIR [FILE_OR_DIR...]
    voice_check.py --text "some copy"
    voice_check.py --commit-msg .git/COMMIT_EDITMSG
    voice_check.py --staged

Errors fail the build. Warnings never do: they are rhythm tells a human writer
may have meant. Overrule one line with `voice-ok: <reason>` on it.

Two escape hatches, and they are different sizes:

    voice-check: reference           in the first 40 lines, whole file exempt
    <!-- voice-check: quote -->      one block, for somebody else's words
    <!-- /voice-check: quote -->

Use the block form in research and archive documents. The file form disables the
attribution and accessibility checks too, which is almost never what you want.

Extends scripts/voice_check.py from the heatsync-brand skill package, which is
the upstream source of the word lists and the reference pragma.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks import Finding, lint  # noqa: E402,F401  (re-exported for tests)

CHECKED_SUFFIXES = {
    ".md", ".markdown", ".mdx", ".txt", ".rst",
    ".ts", ".tsx", ".js", ".jsx", ".vue", ".py", ".sql", ".html",
    ".css", ".scss", ".yml", ".yaml",
}

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "__pycache__",
             ".research", "vendor", "coverage", ".next", ".astro", ".turbo"}


def expand(path: Path) -> list[Path]:
    """One path in, every checkable file out.

    A directory walks. A named file passes through whatever its suffix, because
    naming a file is an instruction rather than a guess. Returning nothing for a
    directory is how a misconfigured CI path passes without looking at anything,
    so it does not do that.
    """
    if path.is_file():
        return [path]
    if not path.is_dir():
        print(f"voice-check: {path} does not exist", file=sys.stderr)
        return []
    return [child for child in sorted(path.rglob("*"))
            if child.is_file()
            and child.suffix in CHECKED_SUFFIXES
            and not any(part in SKIP_DIRS for part in child.parts)]


def staged_files() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=False)
    return [Path(p) for p in result.stdout.split()
            if Path(p).suffix in CHECKED_SUFFIXES and Path(p).exists()]


def collect(args: argparse.Namespace) -> list[tuple[str, Path, bool]]:
    jobs: list[tuple[str, Path, bool]] = []
    if args.text is not None:
        jobs.append((args.text, Path("<text>"), False))
    if args.commit_msg:
        jobs.append((args.commit_msg.read_text(encoding="utf-8", errors="replace"),
                     args.commit_msg, True))
    for path in (staged_files() if args.staged else args.files):
        for target in expand(path):
            jobs.append((target.read_text(encoding="utf-8", errors="replace"),
                         target, False))
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--text", help="lint a string instead of files")
    parser.add_argument("--commit-msg", type=Path, help="lint a commit message file")
    parser.add_argument("--staged", action="store_true", help="lint staged files")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as errors. Not used in CI")
    parser.add_argument("--quiet", action="store_true", help="print only failures")
    args = parser.parse_args()

    jobs = collect(args)
    if not jobs:
        if not args.quiet:
            print("voice-check: nothing to check")
        return 0

    errors = warns = 0
    for raw, path, commit_mode in jobs:
        for finding in lint(raw, path, commit_mode):
            errors += finding.level == "error"
            warns += finding.level == "warn"
            print(finding.render(str(path)), file=sys.stderr)

    if errors or warns:
        print(f"\nvoice-check: {errors} error(s), {warns} warning(s) across "
              f"{len(jobs)} file(s)", file=sys.stderr)
        print("Rules: docs/conventions/voice.md. Suppress one line with "
              "'voice-ok: <reason>'.", file=sys.stderr)
    elif not args.quiet:
        print(f"voice-check: clean across {len(jobs)} file(s)")

    return 1 if errors or (args.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
