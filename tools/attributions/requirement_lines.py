"""Read one requirement line, and decide whether its marker applies here.

A `Requires-Dist` line is a package name, sometimes some extras, sometimes a
version specifier, and sometimes a marker after a semicolon saying when the
requirement is real. dependency_table.py walks those lines to work out what
asked for each package in a lock, and this is the file that reads one.

Refused lives here rather than beside the code that raises it most, because
this is the lowest file of the three and every one above it raises the same
exception. There is nothing below this one to import it from.

Markers are read against the Python version the lock was compiled at, and not
against the machine. `uv pip compile --universal --python-version 3.13` resolves
as if it were 3.13 on every platform, so a requirement gated on the Python
version is decidable and one gated on the platform is not: the lock carries the
packages every platform needs, so a platform gate is treated as real and the row
for the package it brings in says where it gets installed.
"""
from __future__ import annotations

import re

# Marker variables whose value depends on the machine.
PLATFORM_VARIABLES = frozenset({
    "sys_platform", "platform_system", "platform_machine", "platform_release",
    "platform_version", "platform_python_implementation", "implementation_name",
    "implementation_version", "os_name"})

# The two the lock pins, and so the two that can be decided.
PYTHON_VARIABLES = frozenset({"python_version", "python_full_version"})

REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(?:\[([^]]*)\])?")
EXTRA_CLAUSE = re.compile(r"""^extra\s*(?:==|!=)\s*['"][^'"]+['"]$""")
EXTRA_NAME = re.compile(r"""extra\s*==\s*['"]([^'"]+)['"]""")
COMPARISON = re.compile(r"""^([A-Za-z_]+)\s*(==|!=|<=|>=|<|>)\s*['"]([^'"]*)['"]$""")


class Refused(Exception):
    """The generator stopped rather than write a row it could not stand behind."""


def canonical(name: str) -> str:
    """The name a lockfile and a metadata directory agree on, per the PyPA rule."""
    return re.sub(r"[-_.]+", "-", name).lower()


def version_tuple(text: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(\.\d+)*", text):
        raise Refused(
            f"the version {text!r} in a marker is not plain dotted numbers, so "
            "the generator stopped rather than guess how it orders. Compare it "
            "by hand and add the case to tools/attributions/requirement_lines.py")
    return tuple(int(part) for part in text.split("."))


def parse_requirement(text: str) -> tuple[str, list[str], str]:
    """One Requires-Dist line, as the name it points at, its extras, its marker."""
    body, _, marker = text.partition(";")
    found = REQUIREMENT_NAME.match(body)
    if found is None:
        raise Refused(f"cannot read {text!r} as a requirement")
    extras = [part.strip() for part in (found.group(2) or "").split(",") if part.strip()]
    return canonical(found.group(1)), extras, marker.strip()


def clause_holds(clause: str, python: tuple[int, ...], where: str) -> bool:
    found = COMPARISON.match(clause)
    if found is None:
        raise Refused(
            f"{where}: the marker clause {clause!r} is not a plain comparison "
            "against a quoted value, so the generator stopped rather than credit "
            "a package that may not have asked. Read that requirement by hand "
            "and widen tools/attributions/requirement_lines.py if it is worth it")
    variable, operator, value = found.groups()
    if variable in PLATFORM_VARIABLES:
        return True
    if variable not in PYTHON_VARIABLES:
        raise Refused(
            f"{where}: nothing here knows the marker variable {variable!r}, so "
            "the generator stopped. Add it to PLATFORM_VARIABLES in "
            "tools/attributions/requirement_lines.py if it varies by machine")
    wanted = version_tuple(value)
    width = max(len(python), len(wanted))
    left = python + (0,) * (width - len(python))
    right = wanted + (0,) * (width - len(wanted))
    return {"==": left == right, "!=": left != right, "<": left < right,
            "<=": left <= right, ">": left > right, ">=": left >= right}[operator]


def marker_holds(marker: str, python: tuple[int, ...], where: str) -> bool:
    """Whether a requirement's marker is true for the Python the lock was compiled at.

    Clauses are and-joined only. A marker carrying `or` or a bracket lands on
    clause_holds, which refuses it by name rather than reading past it.
    """
    for clause in marker.split(" and "):
        stripped = clause.strip()
        if not stripped or EXTRA_CLAUSE.match(stripped):
            continue
        if not clause_holds(stripped, python, where):
            return False
    return True
