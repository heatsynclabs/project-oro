#!/usr/bin/env python3
"""Prove the undefined name check can go red.

A gate that has only ever been green proves nothing. Each test here writes one
Python file into a throwaway directory, runs the same ruff invocation run.sh
runs, and asserts what came back.

    python3 tools/names/test_names.py <ruff image> <rule list>

The image and the rule list are passed in rather than repeated here, so there is
one place in this tool that decides what runs and it is run.sh.

Needs docker and python3. Writes only under a temporary directory.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

IMAGE = sys.argv[1]
RULES = sys.argv[2]


def check(source: str) -> tuple[int, str]:
    """Run the gate over a directory holding one file, and give back what it said.

    The container runs as uid 1000 and a temporary directory is 0700 owned by
    whoever ran this, so the mount is unreadable inside without this. Docker
    Desktop hides that and Docker on Linux does not, which is how it reached CI
    the first time.
    """
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        (root / "module.py").write_text(source)
        os.chmod(root, 0o755)
        os.chmod(root / "module.py", 0o644)
        done = subprocess.run([
            "docker", "run", "--rm", "-v", f"{root}:/io:ro", "-w", "/io", IMAGE,
            "check", "--no-cache", "--isolated", "--select", RULES, ".",
        ], capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr


def test_a_name_left_behind_by_a_split_is_reported():
    """The bug this gate was built for, reduced to the shape it had.

    configure.py defined the constant, clients.py was split out carrying a use
    of it, and clients.py does not import configure. Inside a function, because
    a use at module level would have failed on import and the suite would have
    caught it.
    """
    code, output = check("def report(older):\n"
                         "    print(_GENERATED_INSTEAD, older)\n")
    assert code == 1, output
    assert "F821" in output, output
    assert "_GENERATED_INSTEAD" in output, output


def test_a_name_that_is_defined_is_not_reported():
    code, output = check("MESSAGE = 'held under an identifier'\n\n\n"
                         "def report(older):\n"
                         "    print(MESSAGE, older)\n")
    assert code == 0, output


def test_a_name_only_the_tests_import_is_not_reported():
    """A module reached through sys.path rather than a package still resolves.

    Every tool in tools/identity imports its neighbours this way. If the gate
    could not see through that it would be red on the whole directory and get
    switched off in a week.
    """
    code, output = check("import pathlib\nimport sys\n\n"
                         "sys.path.insert(0, str(pathlib.Path(__file__).parent))\n\n"
                         "import api      # noqa: E402\n\n\n"
                         "def read(token):\n"
                         "    return api.get('/x', token)\n")
    assert code == 0, output


def test_a_second_definition_silently_winning_is_reported():
    code, output = check("def held(token):\n    return 1\n\n\n"
                         "def held(token):\n    return 2\n")
    assert code == 1, output
    assert "F811" in output, output


def test_an_export_the_module_does_not_have_is_reported():
    code, output = check("__all__ = ['point_at']\n\n\n"
                         "def say_there_is_none():\n    return None\n")
    assert code == 1, output
    assert "F822" in output, output


def test_a_builtin_is_not_reported():
    """Guards against a rule list that resolves nothing and reports everything."""
    code, output = check("def count(rows):\n    return len(list(rows))\n")
    assert code == 0, output


def main() -> int:
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as broken:
            failures += 1
            print(f"FAIL {test.__name__}: {broken}")
    print(f"\n{len(tests) - failures}/{len(tests)} checks")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
