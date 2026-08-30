#!/usr/bin/env python3
"""Prove the import boundary gate can go red.

A gate that has only ever been green proves nothing, which is the finding
behind most of the checks in this repository. Each test here builds a throwaway
tree shaped like services/, plants one import in it, and asserts the gate either
reports that import or stays quiet about it.

Three of the planted imports are one import deep. Two of the three cross a line
and have to be named, which is what the contracts being evaluated over a graph
buys: the module that crosses does not have to be the module anybody opened. The
third is a legal chain and has to stay silent, because a gate that reported
every chain would pass the other cases while refusing the tree this repository
already has.

Six more hold the width of the graph rather than the arrows across it, because
import-linter only reads what root_packages reaches. Four put the module in the
middle beside the root packages and one puts it inside one, in a directory with
no __init__.py that Python imports through and grimp does not read. The sixth
proves a directory nothing imports through is left alone, which is what
services/door/tests is.

Ruff's TID rules see that shape too. Pointed at the same two file tree with
`door` as a banned-api, ruff 0.16.5 reported `TID251 door is banned` on the file
in the middle, measured on 2026-08-29. What they cannot see is an import that
crosses in a file their config does not cover: with a ruff.toml under
services/api and the crossing import in services/shared_wire.py, ruff reported
"All checks passed". That is the case
docs/decisions/0006-import-boundaries.md is really about, and it is the case
check_root_packages.py beside this file exists to refuse, because import-linter
misses it too until the module in the middle is a declared root package.

    python3 tools/import-boundaries/test_import_boundaries.py [IMAGE]

Needs docker and python3. IMAGE defaults to the tag run.sh builds. Writes only
under a temporary directory.
"""
from __future__ import annotations

import sys

from harness import DEFAULT_IMAGE, in_a_tree, run_checks


def test_the_api_importing_the_door_service_is_reported(tree):
    tree.write("services/api/app/main.py",
               "from door.adapters import wire\n")
    tree.write("services/door/adapters/wire.py", "PASSWORD_HEX_DIGITS = 8\n")
    code, output = tree.check()
    assert code == 1, output
    assert "do not import each other BROKEN" in output, output
    assert "app.main -> door.adapters.wire" in output, output


def test_the_api_importing_the_door_service_one_import_deep_is_reported(tree):
    """The contract is evaluated over a graph, not over the module in the diff.

    app.main imports app.gateway, and app.gateway is the one that reaches
    across. Nothing about app.main says door, so the module that crosses the
    line is not the module a reviewer opened.
    """
    tree.write("services/api/app/main.py", "from app import gateway\n")
    tree.write("services/api/app/gateway.py",
               "from door.adapters import wire\n")
    tree.write("services/door/adapters/wire.py", "PASSWORD_HEX_DIGITS = 8\n")
    code, output = tree.check()
    assert code == 1, output
    assert "do not import each other BROKEN" in output, output
    assert "app.gateway -> door.adapters.wire" in output, output


def test_the_door_service_importing_the_api_is_reported(tree):
    """Independence is checked both ways, so the refusal is not one directional."""
    tree.write("services/door/domain/reconcile.py", "from app import members\n")
    tree.write("services/api/app/members.py", "OWN_MEMBER = 'select 1'\n")
    code, output = tree.check()
    assert code == 1, output
    assert "do not import each other BROKEN" in output, output
    assert "door.domain.reconcile -> app.members" in output, output


def test_the_domain_importing_an_adapter_is_reported(tree):
    tree.write("services/door/domain/reconcile.py",
               "from door.adapters import wire\n")
    tree.write("services/door/adapters/wire.py", "PASSWORD_HEX_DIGITS = 8\n")
    code, output = tree.check()
    assert code == 1, output
    assert "does not import its adapters BROKEN" in output, output
    assert "door.domain.reconcile -> door.adapters.wire" in output, output


def test_the_domain_importing_an_adapter_one_import_deep_is_reported(tree):
    """The layer is crossed by a module that sits between the two.

    door.domain.reconcile imports door.domain.slots, which is legal, and
    door.domain.slots is the one that reaches down into an adapter.
    """
    tree.write("services/door/domain/reconcile.py", "from door.domain import slots\n")
    tree.write("services/door/domain/slots.py",
               "from door.adapters import wire\n")
    tree.write("services/door/adapters/wire.py", "PASSWORD_HEX_DIGITS = 8\n")
    code, output = tree.check()
    assert code == 1, output
    assert "does not import its adapters BROKEN" in output, output
    assert "door.domain.slots -> door.adapters.wire" in output, output


def test_an_adapter_importing_the_domain_is_kept(tree):
    """The legal direction, which is the one the real tree already uses."""
    tree.write("services/door/adapters/wire.py", "from door.domain import slots\n")
    tree.write("services/door/domain/slots.py", "TAG_DELETED = 'FFFFFFFF'\n")
    code, output = tree.check()
    assert code == 0, output
    assert "2 kept, 0 broken" in output, output


def test_an_adapter_importing_the_domain_one_import_deep_is_kept(tree):
    """A chain in the legal direction is still legal.

    Worth its own case: a gate that reported every chain would pass every
    violation here while refusing the tree this repository already has.
    """
    tree.write("services/door/adapters/wire.py", "from door.adapters import base\n")
    tree.write("services/door/adapters/base.py", "from door.domain import slots\n")
    tree.write("services/door/domain/slots.py", "TAG_DELETED = 'FFFFFFFF'\n")
    code, output = tree.check()
    assert code == 0, output
    assert "2 kept, 0 broken" in output, output


def test_the_two_services_importing_the_same_outside_module_is_kept(tree):
    """Independence is about the two of them, not about what each one uses.

    Both reach for the standard library here. A contract that read that as the
    two touching would refuse app and door for sharing `logging`, which every
    module in both already does.
    """
    tree.write("services/api/app/main.py", "import logging\n")
    tree.write("services/door/domain/status.py", "import logging\n")
    code, output = tree.check()
    assert code == 0, output
    assert "2 kept, 0 broken" in output, output


def test_a_module_outside_every_root_package_is_refused(tree):
    """The hole in the graph, held shut by the check beside this file.

    app.door_gateway imports shared_wire, which sits under services/ and is in
    no root package. import-linter never reads it, so it reports both contracts
    kept while the interpreter loads the door service from app. A bare .py file
    cannot be added to root_packages either, which is why the refusal says to
    give it a directory first.
    """
    tree.write("services/shared_wire.py", "from door.adapters import wire\n")
    tree.write("services/api/app/door_gateway.py", "import shared_wire\n")
    tree.write("services/door/adapters/wire.py", "PASSWORD_HEX_DIGITS = 8\n")
    # Asserted rather than described, so the day import-linter stops needing
    # help here is the day this goes red and somebody deletes the check.
    code, output = tree.check()
    assert code == 0, output
    assert "2 kept, 0 broken" in output, output
    code, output = tree.root_packages()
    assert code == 1, output
    assert "imports shared_wire" in output, output
    assert "not a package" in output, output


def test_a_package_outside_every_root_package_is_refused(tree):
    """Same hole, reached through a package rather than a loose file."""
    tree.write("services/shared/__init__.py", "")
    tree.write("services/shared/wire.py", "from door.adapters import wire\n")
    tree.write("services/api/app/door_gateway.py", "from shared import wire\n")
    tree.write("services/door/adapters/wire.py", "PASSWORD_HEX_DIGITS = 8\n")
    code, output = tree.root_packages()
    assert code == 1, output
    assert "root_packages does not name shared" in output, output


def test_a_declared_third_package_puts_the_chain_back_in_the_graph(tree):
    """The remedy the refusal asks for, and proof that it is a remedy.

    Once `shared` is on the list, the contract breaks and both hops are named,
    so the reader is not left hunting for the module in the middle.
    """
    tree.write("services/shared/__init__.py", "")
    tree.write("services/shared/wire.py", "from door.adapters import wire\n")
    tree.write("services/api/app/door_gateway.py", "from shared import wire\n")
    tree.write("services/door/adapters/wire.py", "PASSWORD_HEX_DIGITS = 8\n")
    tree.declare("shared")
    code, output = tree.root_packages()
    assert code == 0, output
    code, output = tree.check()
    assert code == 1, output
    assert "app.door_gateway -> shared.wire" in output, output
    assert "shared.wire -> door.adapters.wire" in output, output


def test_an_import_no_directory_here_provides_is_left_alone(tree):
    """Third party imports are not the root package check's business.

    services/api/app really does import fastapi, and nothing under services/
    provides it, so a check that spoke up about names it cannot find would fail
    the tree it runs over on its first day.
    """
    tree.write("services/api/app/main.py", "import fastapi\n")
    code, output = tree.root_packages()
    assert code == 0, output


def test_a_namespace_directory_inside_a_root_package_is_refused(tree):
    """The other way out of the graph, and it is inside a root package.

    app/gateway/ holds a .py file and no __init__.py. Python imports through
    it, grimp does not walk into it, and import-linter reports both contracts
    kept while the interpreter loads the door service from the members API.
    Measured on 2026-08-29 on this exact shape: "Analyzed 6 files, 0
    dependencies", and adding one empty __init__.py turned the same tree red.
    """
    tree.write("services/api/app/main.py", "from app.gateway import wire\n")
    tree.write("services/api/app/gateway/wire.py",
               "from door.adapters import wire\n")
    tree.write("services/door/adapters/wire.py", "PASSWORD_HEX_DIGITS = 8\n")
    # Asserted rather than described, so the day grimp starts reading namespace
    # packages is the day this goes red and somebody deletes the check.
    code, output = tree.check()
    assert code == 0, output
    assert "2 kept, 0 broken" in output, output
    code, output = tree.root_packages()
    assert code == 1, output
    assert "imports through" in output, output
    assert "no __init__.py" in output, output


def test_a_directory_nothing_imports_through_is_left_alone(tree):
    """services/door/tests is exactly this, and it is not a violation.

    It holds nine .py files and no __init__.py on purpose, and nothing inside
    the door package imports through it. Refusing every namespace directory
    would fail the tree this gate was written for.
    """
    tree.write("services/door/tests/test_wire.py", "from door.domain import slots\n")
    tree.write("services/door/domain/slots.py", "TAG_DELETED = 'FFFFFFFF'\n")
    code, output = tree.root_packages()
    assert code == 0, output
    assert "grimp will not read" in output, output



if __name__ == "__main__":
    sys.exit(run_checks(globals(),
                        sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE))
