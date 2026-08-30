"""The throwaway tree the import boundary checks are planted in.

Split out of test_import_boundaries.py when that file went past the 300 line
ceiling in rule 6. Nothing here asserts anything: it builds a copy of the shape
services/ has, runs the gate over it, and reports what the gate said.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CONTRACTS = HERE / "contracts.ini"
DEFAULT_IMAGE = "oro-import-boundaries:2.14"


class Tree:
    """A throwaway copy of the shape services/ has, in a temporary directory.

    The real contracts.ini is copied in rather than a cut down one written
    here, because the thing under test is that file and a paraphrase of it
    would test the paraphrase.
    """

    def __init__(self, root: pathlib.Path, image: str):
        self.root = root
        self.image = image
        (root / "tools" / "import-boundaries").mkdir(parents=True)
        shutil.copy(CONTRACTS, root / "tools" / "import-boundaries" / "contracts.ini")
        for package in ("services/door", "services/door/domain",
                        "services/door/adapters", "services/api/app"):
            self.write(f"{package}/__init__.py", "")

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def readable_to_the_container(self) -> None:
        """Let uid 1000 inside the image read a tree this process just made.

        tempfile creates its directory 0700 and the image runs as uid 1000, so
        on a Linux runner the container cannot traverse into it at all. Measured
        on 2026-08-30: every docker backed check here failed with "Could not
        find tools/import-boundaries/contracts.ini" on the runner while the same
        fourteen passed on a laptop, because Docker Desktop presents a shared
        directory to the container as readable whatever its real mode. The
        working tree run.sh mounts is world readable in an ordinary checkout, so
        this is the harness's problem and not the gate's.
        """
        os.chmod(self.root, 0o755)
        for path in self.root.rglob("*"):
            os.chmod(path, 0o755 if path.is_dir() else 0o644)

    def check(self) -> tuple[int, str]:
        self.readable_to_the_container()
        done = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{self.root}:/io:ro", "-w", "/io",
             "-e", "PYTHONPATH=/io/services:/io/services/api", self.image,
             "lint-imports", "--config", "tools/import-boundaries/contracts.ini",
             "--no-cache", "--no-logo"],
            capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def root_packages(self) -> tuple[int, str]:
        """Run check_root_packages.py over this tree, the way run.sh does."""
        done = subprocess.run(
            [sys.executable, str(HERE / "check_root_packages.py"),
             str(self.root / "tools" / "import-boundaries" / "contracts.ini"),
             str(self.root / "services"), str(self.root / "services" / "api")],
            capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def declare(self, name: str) -> None:
        """Add one root package to the copied contracts.ini.

        The real file plus one line, rather than a config written here, for the
        same reason the copy exists at all.
        """
        config = self.root / "tools" / "import-boundaries" / "contracts.ini"
        config.write_text(config.read_text().replace(
            "root_packages =\n", f"root_packages =\n    {name}\n", 1))


def in_a_tree(body, image: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        body(Tree(pathlib.Path(directory), image))


def run_checks(namespace: dict, image: str) -> int:
    # One clear refusal rather than the same docker error eight times. Somebody
    # running this file on its own has skipped the build that run.sh does.
    if subprocess.run(["docker", "image", "inspect", image],
                      capture_output=True).returncode != 0:
        print(f"No image called {image}. It is built from the Dockerfile beside "
              "this file, and tools/import-boundaries/run.sh builds it before "
              "running these checks. Run that instead, or build it by hand with "
              f"docker build --tag {image} tools/import-boundaries")
        return 1

    checks = [(name, fn) for name, fn in sorted(namespace.items())
              if name.startswith("test_") and callable(fn)]
    failed = []
    for name, fn in checks:
        try:
            in_a_tree(fn, image)
        except AssertionError as exc:
            failed.append(name)
            print(f"FAIL {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}  {type(exc).__name__}: {exc}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0
