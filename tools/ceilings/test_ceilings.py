#!/usr/bin/env python3
"""Prove the ceilings check can go red.

A gate that has only ever been green proves nothing, which is the finding that
motivated most of the checks in this repository. Each test here builds a
throwaway repository, puts one violation in it, and asserts the check reports
that violation and exits 1.

    python3 tools/ceilings/test_ceilings.py

Needs git and python3. Writes only under a temporary directory.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

CHECKER = pathlib.Path(__file__).resolve().parent / "check_ceilings.py"


class Repository:
    """A git repository with the checker in it, in a temporary directory.

    Real git, because the checker reads its file list from `git ls-files` and a
    stub that returned a list instead would test the stub.
    """

    def __init__(self, root: pathlib.Path):
        self.root = root
        run = ["git", "-C", str(root)]
        subprocess.run(run + ["init", "--quiet"], check=True)
        (root / "tools" / "ceilings").mkdir(parents=True)
        shutil.copy(CHECKER, root / "tools" / "ceilings" / "check_ceilings.py")
        self.exempt("")

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        subprocess.run(["git", "-C", str(self.root), "add", path], check=True)

    def exempt(self, text: str) -> None:
        self.write("tools/ceilings/exemptions.txt", text)

    def check(self) -> tuple[int, str]:
        done = subprocess.run(
            [sys.executable, "tools/ceilings/check_ceilings.py"],
            cwd=self.root, capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr


def in_a_repository(body) -> None:
    with tempfile.TemporaryDirectory() as directory:
        body(Repository(pathlib.Path(directory)))


def test_a_long_source_file_is_reported():
    def body(repo):
        repo.write("apps/members/long.js", "// a line\n" * 301)
        code, output = repo.check()
        assert code == 1, output
        assert "apps/members/long.js: 301 lines" in output, output
    in_a_repository(body)


def test_a_long_typescript_file_is_reported():
    """The suffix list is the whole of what makes this reachable.

    There is no TypeScript in the repository today, and ADR 0006 says the
    admin portal brings the first of it. A file ceiling that silently skipped
    the new language would be found on the day it stopped mattering.
    """
    def body(repo):
        repo.write("apps/admin/view.tsx", "const x = 1\n" * 400)
        code, output = repo.check()
        assert code == 1, output
        assert "apps/admin/view.tsx: 400 lines" in output, output
    in_a_repository(body)


def test_a_long_function_is_reported():
    def body(repo):
        body_lines = "".join(f"    x = {n}\n" for n in range(60))
        repo.write("services/api/long.py", f"def wide():\n{body_lines}")
        code, output = repo.check()
        assert code == 1, output
        assert "wide is 61 lines" in output, output
    in_a_repository(body)


def test_an_exempted_file_passes():
    def body(repo):
        repo.write("apps/members/long.js", "// a line\n" * 301)
        repo.exempt("apps/members/long.js  it is one cascade and splitting it "
                    "would make the order load bearing\n")
        code, output = repo.check()
        assert code == 0, output
    in_a_repository(body)


def test_an_exemption_with_no_reason_is_refused():
    def body(repo):
        repo.write("apps/members/long.js", "// a line\n" * 301)
        repo.exempt("apps/members/long.js\n")
        code, output = repo.check()
        assert code == 1, output
        assert "no reason given" in output, output
    in_a_repository(body)


def test_an_exemption_that_is_no_longer_needed_is_reported():
    def body(repo):
        repo.write("apps/members/short.js", "// a line\n")
        repo.exempt("apps/members/short.js  a reason that has outlived itself\n")
        code, output = repo.check()
        assert code == 1, output
        assert "no longer over it" in output, output
    in_a_repository(body)


def test_a_migration_is_exempt_without_being_listed():
    """Rule 6 exempts migrations by name, so they are not in the list at all."""
    def body(repo):
        repo.write("db/migrations/900_wide.sql", "SELECT 1;\n" * 400)
        code, output = repo.check()
        assert code == 0, output
    in_a_repository(body)


def test_prose_is_not_a_source_file():
    def body(repo):
        repo.write("docs/plan/long.md", "A sentence.\n" * 500)
        code, output = repo.check()
        assert code == 0, output
    in_a_repository(body)


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
