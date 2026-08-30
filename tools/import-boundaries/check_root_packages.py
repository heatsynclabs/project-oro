#!/usr/bin/env python3
"""Refuse an import that leaves the graph the contracts are checked over.

import-linter starts at the root packages named in contracts.ini and follows
imports from there. A module outside every root package is not a node in that
graph, so a chain that passes through it is invisible. Measured on 2026-08-29
in a copy of this tree: services/shared_wire.py holding
`from door.adapters.oac_ethernet import wire`, and services/api/app/door_gateway.py
holding `import shared_wire`, gave "Contracts: 2 kept, 0 broken" and exit 0,
while `python -c "import app.door_gateway"` in the same image left
door.adapters.oac_ethernet.wire in sys.modules.

There is a second way out of the graph and it is inside a root package rather
than beside one. A directory holding .py files and no __init__.py is a namespace
package: the interpreter imports through it and grimp does not walk into it.
Measured the same day, `services/api/app/gateway/` with no __init__.py holding
`from door.adapters import wire`, imported by app/main.py, gave
"Analyzed 6 files, 0 dependencies" and both contracts kept, while the
interpreter loaded door.adapters.wire. Adding one empty __init__.py to the same
tree turned it red.

So this refuses two things. A top level name that one of the gate's PYTHONPATH
directories provides while contracts.ini does not declare it, and an import that
reaches through a directory inside a root package that grimp will not read. A
third party import is left alone, because no directory here provides it.

    tools/import-boundaries/check_root_packages.py CONFIG DIRECTORY [DIRECTORY ...]

CONFIG is contracts.ini. Each DIRECTORY is one entry of the PYTHONPATH the gate
runs with. Needs python3 and nothing else. Exit code is 1 if any import leaves
the graph.
"""
from __future__ import annotations

import ast
import configparser
import pathlib
import sys


def declared_root_packages(config: pathlib.Path) -> list[str]:
    parser = configparser.ConfigParser()
    parser.read(config)
    return parser["importlinter"]["root_packages"].split()


def root_directory(root: str, directories: list[pathlib.Path]) -> pathlib.Path:
    for directory in directories:
        if (directory / root).is_dir():
            return directory / root
    raise SystemExit(
        f"contracts.ini names {root} in root_packages, and none of "
        f"{', '.join(str(d) for d in directories)} holds a directory called "
        f"that. Either the name is wrong or the directory that would go on "
        f"PYTHONPATH is missing from the arguments this was called with.")


def package_modules(directory: pathlib.Path) -> list[pathlib.Path]:
    """Every .py file grimp reads for the package rooted at this directory.

    A subdirectory with no __init__.py is not part of the package, which is why
    the gate reports 23 files for a tree whose services/door/tests holds nine
    more.
    """
    modules = sorted(directory.glob("*.py"))
    for child in sorted(directory.iterdir()):
        if child.is_dir() and (child / "__init__.py").exists():
            modules.extend(package_modules(child))
    return modules


def imported_top_level_names(module: pathlib.Path) -> set[str]:
    """The first component of every absolute import in one file.

    A relative import cannot leave the package it is written in, so it cannot
    leave the graph either, and level 0 is what separates the two.
    """
    names = set()
    for node in ast.walk(ast.parse(module.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def provider(name: str, directories: list[pathlib.Path]) -> pathlib.Path | None:
    """Where the interpreter would find this name, or nothing if it is elsewhere.

    Directory before file within one PYTHONPATH entry, and entries in the order
    they were given, which is the order the import system uses.
    """
    for directory in directories:
        package = directory / name
        if package.is_dir() and any(package.rglob("*.py")):
            return package
        module = directory / f"{name}.py"
        if module.is_file():
            return module
    return None


def readable(path: pathlib.Path) -> str:
    """A path a reader can paste, relative to where they ran this from."""
    try:
        return str(path.resolve().relative_to(pathlib.Path.cwd()))
    except ValueError:
        return str(path)


def refusal(module: pathlib.Path, name: str, found: pathlib.Path) -> str:
    remedy = (
        f"Add {name} to root_packages in tools/import-boundaries/contracts.ini "
        f"and the chain through it is checked."
    )
    if found.is_file():
        remedy = (
            f"{name} is a file, so it cannot go in root_packages as it stands: "
            f"import-linter answers \"'{name}' is a module, not a package\". "
            f"Give it a directory with an __init__.py, then add the name to "
            f"root_packages in tools/import-boundaries/contracts.ini."
        )
    return (f"{readable(module)} imports {name}, and {readable(found)} provides "
            f"it. root_packages does not name {name}, so import-linter never "
            f"reads it and a chain through it is reported as kept. {remedy} Or "
            f"move what it holds into a package the contracts already reach.")


def _absolute_targets(node: ast.AST, root: str) -> list[list[str]]:
    """The parts below the root package for one absolute import, or nothing."""
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[1:] for alias in node.names
                if alias.name.split(".")[0] == root]
    if node.module and node.module.split(".")[0] == root:
        return [node.module.split(".")[1:]]
    return []


def _relative_target(node: ast.ImportFrom, here: tuple[str, ...]) -> list[str]:
    """Where a relative import lands, as parts below the root package.

    Level 1 is the file's own package, level 2 its parent, and so on, which is
    what the interpreter does. A relative import cannot leave the root package,
    so the answer always sits under it.
    """
    kept = len(here) - (node.level - 1)
    base = list(here[:max(kept, 0)])
    return base + (node.module.split(".") if node.module else [])


def imports_inside_the_root(module: pathlib.Path,
                            package_root: pathlib.Path) -> list[list[str]]:
    """Every module path this file imports from inside its own root package."""
    here = module.parent.relative_to(package_root).parts
    root = package_root.name
    targets = []
    for node in ast.walk(ast.parse(module.read_text())):
        if isinstance(node, ast.Import):
            targets.extend(_absolute_targets(node, root))
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            targets.extend(_absolute_targets(node, root))
        elif isinstance(node, ast.ImportFrom):
            targets.append(_relative_target(node, here))
    return targets


def unreadable_directory(package_root: pathlib.Path,
                         target: list[str]) -> pathlib.Path | None:
    """The first directory on this import path that grimp will not walk into."""
    here = package_root
    for part in target:
        here = here / part
        if not here.is_dir():
            return None
        if not (here / "__init__.py").exists():
            return here
    return None


def namespace_refusal(module: pathlib.Path, found: pathlib.Path) -> str:
    return (f"{readable(module)} imports through {readable(found)}, which holds "
            f"no __init__.py. Python treats that as a namespace package and "
            f"imports through it, and grimp does not walk into it, so every "
            f"import inside it is outside the graph and the contracts are "
            f"reported kept over it. Put an empty __init__.py in it. If it is "
            f"deliberately not a package, nothing in a root package may import "
            f"through it.")


def holes_inside(root: str, directories: list[pathlib.Path]) -> list[str]:
    """Namespace directories a root package imports through."""
    package_root = root_directory(root, directories)
    found = []
    for module in package_modules(package_root):
        for target in imports_inside_the_root(module, package_root):
            where = unreadable_directory(package_root, target)
            if where is not None:
                found.append(namespace_refusal(module, where))
    return sorted(set(found))


def findings(config: pathlib.Path, directories: list[pathlib.Path]) -> list[str]:
    roots = declared_root_packages(config)
    found = []
    for root in roots:
        for module in package_modules(root_directory(root, directories)):
            for name in sorted(imported_top_level_names(module)):
                if name in roots:
                    continue
                where = provider(name, directories)
                if where is not None:
                    found.append(refusal(module, name, where))
        found.extend(holes_inside(root, directories))
    return found


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Usage: check_root_packages.py CONFIG DIRECTORY [DIRECTORY ...]")
        return 1
    config = pathlib.Path(argv[1])
    directories = [pathlib.Path(entry) for entry in argv[2:]]
    refusals = findings(config, directories)
    for one in refusals:
        print(one)
        print()
    if refusals:
        count = len(refusals)
        leaving = "import leaves" if count == 1 else "imports leave"
        print(f"{count} {leaving} the graph the contracts are checked over. "
              "Rule 5 of CLAUDE.md is not held over a module import-linter "
              "never reads.")
        return 1
    roots = declared_root_packages(config)
    modules = sum(len(package_modules(root_directory(root, directories)))
                  for root in roots)
    print(f"{modules} modules in {' and '.join(roots)}. Every import of theirs "
          "that these directories provide is inside a declared root package, "
          "and none of them reaches through a directory grimp will not read.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
