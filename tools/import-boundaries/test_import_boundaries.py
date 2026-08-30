#!/usr/bin/env python3
"""Prove the import boundary gate can go red.

A gate that has only ever been green proves nothing. Each check below builds a
throwaway tree shaped like services/, plants one shape in it, and asserts the
gate either names that shape or stays quiet about it.

The shapes fall in three groups. Some cross a layer line, directly or one import
deep, which is what evaluating the contracts over a graph buys: the module that
crosses does not have to be the module anybody opened. Some leave the graph
altogether, through a module beside the root packages or through a directory
inside one that holds no __init__.py, and check_root_packages.py beside this
file is what refuses those. The rest name a root package in a string, which
import-linter reads as text rather than as an import.

Each group also holds a legal case that has to stay quiet, because a gate that
reported every chain would pass every violation here and refuse the real tree.
docs/decisions/0006-import-boundaries.md priced ruff's TID rules against all of
this and recorded the crossing import they miss.

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
    tree.shared_package()
    code, output = tree.root_packages()
    assert code == 1, output
    assert "root_packages does not name shared" in output, output


def test_a_declared_third_package_puts_the_chain_back_in_the_graph(tree):
    """The remedy the refusal asks for, and proof that it is a remedy.

    Once `shared` is on the list, the contract breaks and both hops are named,
    so the reader is not left hunting for the module in the middle.
    """
    tree.shared_package()
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


def test_a_string_import_of_a_root_package_is_reported(tree):
    """A module name written as a string is a hole in the graph.

    import-linter reads imports, and a string is not an import until the call
    runs. Measured on 2026-08-30 outside this repository: each spelling below
    gave "Contracts: 2 kept, 0 broken" and exit 0, and importing app.main in
    the gate's own image left door.adapters.oac_ethernet.wire in sys.modules.
    """
    tree.plant_string_import(
        'importlib.import_module("door.adapters.oac_ethernet.wire")',
        '__import__("door.adapters.oac_ethernet.wire", fromlist=["wire"])',
        'importlib.__import__("door.adapters.oac_ethernet.wire", fromlist=["w"])')
    # Asserted rather than described, so the day import-linter starts reading
    # strings is the day this goes red and somebody deletes the check.
    code, output = tree.check()
    assert code == 0, output
    assert "2 kept, 0 broken" in output, output
    code, output = tree.root_packages()
    assert code == 1, output
    assert output.count("reads imports rather than strings") == 3, output


def test_a_module_getattr_reaching_for_a_root_package_is_reported(tree):
    """The same hole, reached by touching an attribute rather than calling.

    PEP 562 lets app/__init__.py answer `app.wire` by loading the door service
    on demand, so nothing that reads as an import appears in the members API.
    Measured the same day: both contracts kept, and importing app.main left
    door.adapters.wire in sys.modules.
    """
    tree.write("services/api/app/__init__.py",
               "import importlib\n\n\ndef __getattr__(name):\n"
               "    return importlib.import_module('door.adapters.wire')\n")
    tree.write("services/door/adapters/wire.py", "PASSWORD_HEX_DIGITS = 8\n")
    code, output = tree.root_packages()
    assert code == 1, output
    assert "reads imports rather than strings" in output, output


def test_a_string_import_of_anything_else_is_left_alone(tree):
    """Loading a module by name is ordinary Python and stays ordinary here.

    Only a string naming a declared root package is a hole. A check that spoke
    up about every string would be switched off in a week.
    """
    tree.plant_string_import('importlib.import_module("json")',
                             'importlib.import_module("fastapi.routing")')
    code, output = tree.root_packages()
    assert code == 0, output


def test_the_refusal_names_the_module_the_interpreter_would_import(tree):
    """A namespace directory offers the name first and does not get it.

    Naming the directory sends the reader to the remedy for a package, and
    following that leaves check_root_packages.py at exit 0 while lint-imports
    stops on "'bridge' is a module, not a package". Measured on 2026-08-30.
    """
    tree.shadowed_name()
    code, output = tree.root_packages()
    assert code == 1, output
    assert "services/api/bridge.py provides it" in output, output
    assert "not a package" in output, output



if __name__ == "__main__":
    sys.exit(run_checks(globals(),
                        sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE))
