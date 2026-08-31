"""Turn a lockfile and one image's metadata into the rows of a licence table.

Nothing here touches docker or the working tree. It takes the lock, the
requirements.in beside it, and the JSON that read_metadata.py wrote inside the
built image, and it returns one Row per package in the lock. generate.py is the
half that builds the image and rewrites ATTRIBUTIONS.md.

Three facts go in each row and they come from three places, which is the whole
reason this file exists rather than a shell pipeline.

    version     the lock, because that is what pip installs
    licence     the installed package's own metadata, because rule 9 wants the
                claim traced to the package rather than to an index summary
    asked for   requirements.in for the direct ones, and Requires-Dist for the
                rest, because a lock records that a package is needed and not
                by whom

Every name in the table is the lock's spelling. A package's own metadata Name
sometimes differs, `typing_extensions` against the lock's `typing-extensions`,
and a table a reader cannot grep against the file it describes is worse than
one that drops a capital letter.

Anything it cannot read is refused rather than guessed. A wrong row here is a
licence claim somebody cites in three years. requirement_lines.py beside this
file reads one Requires-Dist line and raises the same Refused.
"""
from __future__ import annotations

import collections
import dataclasses
import re

from requirement_lines import (EXTRA_NAME, REQUIREMENT_NAME, Refused, canonical,
                               marker_holds, parse_requirement, version_tuple)

CLASSIFIER = "classifier"
NOT_INSTALLED = "not installed here"

# A licence identifier is one short line. Some packages put the whole licence
# text in the License field, and 64 characters is comfortably past the longest
# real identifier here, `Apache-2.0 OR BSD-3-Clause` at 26.
IDENTIFIER_CEILING = 64

# Fragments that make a reader stop and do the check rule 9 asks for before the
# dependency lands. This is a prompt, not a licence classification: a bold cell
# means read the licence, and ATTRIBUTIONS.md carries the reasoning for the two
# copyleft packages this repository already runs.
COPYLEFT_FRAGMENTS = ("GPL", "MPL", "EPL", "CDDL", "OSL", "EUPL", "SSPL")

LOCK_PYTHON = re.compile(r"--python-version\s+(\d+(?:\.\d+)*)")
LOCK_ENTRY = re.compile(r"^([A-Za-z0-9._-]+)==([^\s;\\]+)\s*(?:;\s*(.*?))?\s*\\?$")


@dataclasses.dataclass
class Row:
    name: str
    version: str
    licence: str
    licence_source: str
    requesters: str


@dataclasses.dataclass
class Entry:
    """One `name==version ; marker` line in the lock."""
    name: str
    version: str
    marker: str


def read_lock(path) -> tuple[tuple[int, ...], list[Entry]]:
    text = path.read_text()
    header = LOCK_PYTHON.search(text)
    if header is None:
        raise Refused(
            f"{path} does not name a --python-version in its header, so there is "
            "no version to read a marker against and nothing was generated. It is "
            "written by `uv pip compile`, whose command line is the first two "
            "lines of the file it writes")
    entries = []
    for line in text.splitlines():
        found = LOCK_ENTRY.match(line)
        if found is not None:
            entries.append(Entry(canonical(found.group(1)), found.group(2),
                                 (found.group(3) or "").strip()))
    return version_tuple(header.group(1)), entries


def read_direct(path) -> list[tuple[str, list[str]]]:
    """Every package requirements.in asks for by name, with the extras it asks for."""
    asked = []
    for line in path.read_text().splitlines():
        bare = line.split("#")[0].strip()
        if not bare:
            continue
        found = REQUIREMENT_NAME.match(bare)
        if found is None:
            raise Refused(f"{path}: cannot read {line!r} as a package name")
        extras = [part.strip() for part in (found.group(2) or "").split(",") if part.strip()]
        asked.append((canonical(found.group(1)), extras))
    return asked


def _requirements_of(package: dict, extra: str | None) -> list[str]:
    """The Requires-Dist lines this package has under one extra, or under none."""
    lines = []
    for line in package.get("requires") or []:
        gates = set(EXTRA_NAME.findall(line.partition(";")[2]))
        if gates != ({extra} if extra else set()):
            continue
        lines.append(line)
    return lines


def resolve_requesters(direct, packages: dict, python: tuple[int, ...]) -> dict:
    """Walk out from requirements.in and record what named each package.

    One node per package and extra, so a requirement that arrives only because
    somebody asked for `psycopg[binary]` is labelled that way and a requirement
    under an extra nobody asked for is never walked at all.
    """
    named = collections.defaultdict(list)
    pending = collections.deque()
    for name, extras in direct:
        pending.extend([(name, None)] + [(name, extra) for extra in extras])
    seen = set()
    while pending:
        name, extra = pending.popleft()
        if (name, extra) in seen:
            continue
        seen.add((name, extra))
        package = packages.get(name)
        if package is None:
            continue
        label = f"{name}[{extra}]" if extra else name
        for line in _requirements_of(package, extra):
            target, extras, marker = parse_requirement(line)
            if not marker_holds(marker, python, f"{label} requires {line!r}"):
                continue
            named[target].append(label)
            pending.extend([(target, None)] + [(target, one) for one in extras])
    return named


def _identifier(text: str | None) -> str | None:
    if not text:
        return None
    trimmed = text.strip()
    if "\n" in trimmed or len(trimmed) > IDENTIFIER_CEILING:
        return None
    return trimmed


def _from_classifiers(package: dict) -> str | None:
    found = []
    for classifier in package.get("classifiers") or []:
        if not classifier.startswith("License :: OSI Approved :: "):
            continue
        name = classifier.split(" :: ")[-1]
        # The trailing word is the same word for every one of them and says
        # nothing. "MIT License" becomes MIT, which is what a reader wants.
        found.append(name[:-len(" License")] if name.endswith(" License") else name)
    return " or ".join(found) if found else None


def licence_of(package: dict, where: str) -> tuple[str, str]:
    expression = _identifier(package.get("license_expression"))
    if expression is not None:
        return expression, "License-Expression"
    field = _identifier(package.get("license_field"))
    if field is not None:
        return field, "License"
    classifier = _from_classifiers(package)
    if classifier is not None:
        return classifier, CLASSIFIER
    raise Refused(
        f"{where} records no licence its metadata can be read for: no "
        "License-Expression, no License field short enough to be an identifier, "
        "and no License :: OSI Approved classifier. Nothing was generated. Read "
        "the licence off the project and add the row to the hand maintained half "
        "of ATTRIBUTIONS.md, above the generated markers")


def marked(licence: str) -> str:
    if any(fragment in licence.upper() for fragment in COPYLEFT_FRAGMENTS):
        return f"**{licence}**"
    return licence


def _one_row(entry: Entry, package: dict | None, requesters: str) -> Row:
    if package is None:
        return Row(entry.name, entry.version,
                   f"not read: only where `{entry.marker}`",
                   NOT_INSTALLED, requesters)
    if package["version"] != entry.version:
        raise Refused(
            f"the lock pins {entry.name} at {entry.version} and the image has "
            f"{package['version']}. Nothing was generated, because a row is only "
            "worth citing if both agree. Rebuild the image: it installs the lock, "
            "so the two disagree only when the build is older than the file")
    licence, source = licence_of(package, entry.name)
    return Row(entry.name, entry.version, marked(licence), source, requesters)


def rows_for(lock_path, direct_path, metadata: dict) -> list[Row]:
    python, entries = read_lock(lock_path)
    running = version_tuple(metadata["python_version"])[:len(python)]
    if running != python:
        raise Refused(
            f"{lock_path} was compiled for Python {'.'.join(map(str, python))} and "
            f"the image runs {metadata['python_version']}. Nothing was generated: "
            "a marker reading one way at one version and the other way at the "
            "other would credit the wrong package. Recompile the lock, or pin the "
            "image's base to the version the lock names")
    packages = metadata["packages"]
    direct = read_direct(direct_path)
    locked = {entry.name for entry in entries}
    for name, _ in direct:
        if name not in locked:
            raise Refused(
                f"{direct_path} asks for {name} and {lock_path} does not carry "
                "it, so the lock is older than the file beside it and nothing "
                "was generated. Recompile it, which is the command in its header")
    named = resolve_requesters(direct, packages, python)
    asked = {name for name, _ in direct}
    rows = []
    for entry in sorted(entries, key=lambda one: one.name):
        if entry.name in asked:
            requesters = "asked for"
        elif entry.name in named:
            requesters = ", ".join(sorted(set(named[entry.name])))
        else:
            raise Refused(
                f"{entry.name} is in {lock_path} and nothing in the lock asks for "
                "it, directly or through another package. Nothing was generated. "
                "Either requirements.in lost a line or the lock is stale, and "
                "recompiling it is the command in its header")
        package = packages.get(entry.name)
        if package is None and not entry.marker:
            raise Refused(
                f"{entry.name} is in {lock_path}, the image has no metadata for "
                "it, and the lock gives no marker saying it belongs to another "
                "platform. Nothing was generated, because the licence can only be "
                "read from the installed package. Rebuild the image")
        rows.append(_one_row(entry, package, requesters))
    return rows
