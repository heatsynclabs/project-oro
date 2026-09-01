#!/usr/bin/env python3
"""Every lockfile in this repository has a Source, and every Source has a lock.

    python3 tools/attributions/test_sources.py

Its own file rather than a section of test_attributions.py, which reached the
300 line ceiling in rule 6, and the seam is real: that file builds throwaway
locks and asserts what the generator makes of them, and this one asserts against
the repository as it stands.

The hole this closes: SOURCES was a two entry tuple while three lockfiles were
tracked, so tools/browser-checks/requirements.txt landed on 2026-08-30 and
`make attributions-check` reported ATTRIBUTIONS.md correct over four packages it
had never read. Rule 9 says every dependency, and a list somebody has to remember
to extend is not that.

Needs python3 and git. No docker: nothing here builds an image.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import dependency_table as table  # noqa: E402
import generate  # noqa: E402


def test_every_lockfile_in_this_repository_has_a_source():
    """The hole rule 9 had, asserted against the repository rather than a stub.

    SOURCES was two entries long while three locks were tracked, so
    tools/browser-checks/requirements.txt landed and `make attributions-check`
    reported the page correct over four packages it had never read.
    """
    generate.every_lock_is_covered()


def test_a_lockfile_with_no_source_is_refused():
    """Watch the check above fail, by taking an entry out of SOURCES.

    Restored in a finally, because a check that leaves a module global changed
    makes whichever check sorts after it depend on this one having run.
    """
    was = generate.SOURCES
    generate.SOURCES = tuple(source for source in was
                             if source.directory != "tools/browser-checks")
    try:
        generate.every_lock_is_covered()
    except table.Refused as refused:
        assert "tools/browser-checks/requirements.txt" in str(refused), refused
        assert "SOURCES" in str(refused), refused
        return
    finally:
        generate.SOURCES = was
    raise AssertionError("a lockfile with no entry in SOURCES was not refused")


def test_a_source_naming_a_lockfile_nobody_tracks_is_refused():
    """The other direction, which is a table generated from a lock nobody has."""
    was = generate.SOURCES
    generate.SOURCES = was + (generate.Source("tools/gone", "oro-gone:local"),)
    try:
        generate.every_lock_is_covered()
    except table.Refused as refused:
        assert "tools/gone/requirements.txt" in str(refused), refused
        return
    finally:
        generate.SOURCES = was
    raise AssertionError("a source naming a lockfile nobody tracks was not refused")


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
