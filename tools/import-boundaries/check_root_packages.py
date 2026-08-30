#!/usr/bin/env python3
"""Refuse an import that leaves the graph the contracts are checked over.

import-linter starts at the root packages named in contracts.ini and follows
imports from there, so anything that graph does not reach is checked by nothing.
There are three ways out of it and this refuses all three.

A module beside the root packages. services/shared_wire.py holding
`from door.adapters.oac_ethernet import wire`, imported by
services/api/app/door_gateway.py, gave "Contracts: 2 kept, 0 broken" and exit 0
while the same image running `python -c "import app.door_gateway"` left
door.adapters.oac_ethernet.wire in sys.modules. Measured on 2026-08-29.

A directory inside a root package holding .py files and no __init__.py. Python
imports through it as a namespace package and grimp does not walk into it.
services/api/app/gateway/ holding `from door.adapters import wire`, imported by
app/main.py, gave "Analyzed 6 files, 0 dependencies" and both contracts kept.

A module name written as a string. import-linter reads imports, and a string is
not an import until the call runs. Measured on 2026-08-30, the name
door.adapters.oac_ethernet.wire passed from services/api/app to
importlib.import_module, to __import__ and to importlib.__import__ gave both
contracts kept each time while the interpreter loaded the door service.

A third party import is left alone, because no directory here provides it, and
so is a string naming anything that is not a root package.

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

    Two passes, because a directory with no __init__.py does not win the name
    where it stands. The import system records it as a namespace portion and
    keeps searching, and a package or a module found later takes the name off
    it. Measured on 2026-08-30 in the image this gate runs in: services/bridge/
    holding a .py file, and services/api/bridge.py on the entry after it,
    `import bridge` loaded services/api/bridge.py.
    """
    for directory in directories:
        if (directory / name / "__init__.py").is_file():
            return directory / name
        if (directory / f"{name}.py").is_file():
            return directory / f"{name}.py"
    for directory in directories:
        namespace = directory / name
        if namespace.is_dir() and any(namespace.rglob("*.py")):
            return namespace
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


# Whether importlib is bound to its own name or another, and whether __import__
# is reached as the builtin or as an attribute of it.
DYNAMIC_IMPORT_NAMES = ("import_module", "__import__")


def dynamic_import_target(node: ast.AST) -> str | None:
    """The module name one dynamic import spells out as a literal, or nothing.

    A name built at runtime is not in the source to be read, so nothing here
    can see it, and contracts.ini carries that limit beside the list of roots.
    """
    if not isinstance(node, ast.Call) or not node.args:
        return None
    if isinstance(node.func, ast.Attribute):
        spelling = node.func.attr
    elif isinstance(node.func, ast.Name):
        spelling = node.func.id
    else:
        return None
    named = node.args[0]
    if spelling in DYNAMIC_IMPORT_NAMES and isinstance(named, ast.Constant):
        return named.value if isinstance(named.value, str) else None
    return None


def string_refusal(module: pathlib.Path, named: str) -> str:
    return (f"{readable(module)} passes \"{named}\" to a dynamic import, and "
            f"{named.split('.')[0]} is a root package. import-linter reads "
            f"imports rather than strings, so the contracts are reported kept "
            f"over this call while the interpreter loads {named}. Write it as a "
            f"plain import and they are checked over it. If one then breaks, "
            f"the break is the answer: the call was crossing a line.")


def string_imports(module: pathlib.Path, roots: list[str]) -> list[str]:
    """Dynamic imports in one file that name a root package in a literal."""
    named = [dynamic_import_target(node)
             for node in ast.walk(ast.parse(module.read_text()))]
    return [string_refusal(module, one) for one in named
            if one is not None and one.split(".")[0] in roots]


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
            found.extend(string_imports(module, roots))
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
          "none of them reaches through a directory grimp will not read, and "
          "none of them names a root package in a string.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
