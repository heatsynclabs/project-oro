#!/usr/bin/env python3
"""Generate the dependency half of ATTRIBUTIONS.md from the lockfiles.

Rule 9 says ATTRIBUTIONS.md is generated for dependencies and hand maintained
for patterns. This is the generated half, and it rewrites only what sits
between the two markers below. Everything else on that page is somebody's
writing and is not touched.

    tools/attributions/generate.py           rewrite the region
    tools/attributions/generate.py --check   print what would change, write nothing

For each lock in the repository it builds the image that lock installs into,
reads every package's own metadata out of that image, and writes one row per
package. The licence comes from the package rather than from an index summary
or from memory, which is the whole point: a row in that file is a licence claim
somebody may act on years from now.

Needs docker, python3 and the network, because building an image installs from
PyPI. The members API suite and the import boundary gate need the same, so that
is not what keeps this out of `make check`. It is out because it rewrites a
tracked file. Run it when a lock changes, in the same sitting that recompiles
the lock.

The date in each section is not compared and does not move on its own. It said
2026-08-30 while the generator, which stamps UTC, had reached 2026-08-31, so
--check went red on a repository nobody had touched. A check that reports red
on nothing is one people learn to skip, which is the same defect as one that
reports green on something, reached from the other side. So the comparison runs
against the date already on the page, and the date is rewritten only when
something else about the table is.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import difflib
import json
import pathlib
import re
import subprocess
import sys
import textwrap

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import dependency_table as table  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
PAGE = ROOT / "ATTRIBUTIONS.md"

BEGIN = "<!-- BEGIN GENERATED DEPENDENCIES -->"
END = "<!-- END GENERATED DEPENDENCIES -->"

COLUMNS = ("Package", "Version", "Licence", "Where the licence was read",
           "Asked for, or brought in by")


@dataclasses.dataclass
class Source:
    """One lockfile and the image it installs into."""
    directory: str
    image: str


# The image tag for the import boundary gate is the one its own run.sh builds,
# so the two share a cached build rather than compiling grimp twice.
SOURCES = (
    Source("services/api", "oro-attributions-api:local"),
    Source("tools/import-boundaries", "oro-import-boundaries:2.14"),
)


def read_image(source: Source) -> dict:
    """Build the image the lock installs into, and read its metadata out."""
    context = ROOT / source.directory
    subprocess.run(["docker", "build", "--quiet", "--tag", source.image, str(context)],
                   check=True, stdout=subprocess.DEVNULL)
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{HERE}:/reader:ro",
         source.image, "python", "/reader/read_metadata.py"],
        capture_output=True, text=True)
    if done.returncode != 0:
        raise table.Refused(
            f"reading the metadata out of {source.image} exited "
            f"{done.returncode} and nothing was generated. What it printed:\n"
            f"{done.stderr.strip()}")
    return json.loads(done.stdout)


def counted(rows: list[table.Row]) -> tuple[int, int, int]:
    """How many packages, how many were asked for, how many arrived with them."""
    asked = sum(1 for row in rows if row.requesters == "asked for")
    return len(rows), asked, len(rows) - asked


def wrapped(text: str) -> list[str]:
    """One paragraph, folded to the width the rest of the page is written at.

    break_on_hyphens is off because textwrap otherwise splits a hyphenated
    filename across two lines, which is how `docs/api/contract-review-notes.md`
    reached the database as a path that does not exist. HANDOFF.md section 7
    carries that one.
    """
    return textwrap.wrap(text, width=79, break_on_hyphens=False,
                         break_long_words=False)


def preamble(source: Source, rows: list[table.Row], read_on: str) -> list[str]:
    total, asked, arrived = counted(rows)
    paragraphs = [
        f"Read on {read_on}, out of an image built from "
        f"`{source.directory}/Dockerfile`. {total} packages: {asked} named in "
        f"`{source.directory}/requirements.in`, and {arrived} that arrived with "
        "one of those.",
        "Every version is the one the lock pins. Every licence was read with "
        "`importlib.metadata` out of the installed package's own metadata, and "
        "the fourth column names the field it came from. A licence in bold wants "
        "the check rule 9 asks for before the dependency lands.",
    ]
    absent = [row.name for row in rows if row.licence_source == table.NOT_INSTALLED]
    if absent:
        paragraphs.append(
            f"{', '.join(absent)} is in the lock and not in this image. The lock "
            "is compiled `--universal` and an image is one platform, so a package "
            "another platform needs is pinned here and installed elsewhere. No "
            "licence was read for it.")
    lines = []
    for paragraph in paragraphs:
        if lines:
            lines.append("")
        lines += wrapped(paragraph)
    return lines


def render(source: Source, rows: list[table.Row], read_on: str) -> str:
    heading = (f"### `{source.directory}`, from "
               f"`{source.directory}/requirements.txt`")
    lines = [heading, ""] + preamble(source, rows, read_on) + [
        "",
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    for row in rows:
        lines.append(f"| {row.name} | {row.version} | {row.licence} | "
                     f"{row.licence_source} | {row.requesters} |")
    return "\n".join(lines)


def generated_region(read_on: str) -> str:
    sections = []
    for source in SOURCES:
        directory = ROOT / source.directory
        rows = table.rows_for(directory / "requirements.txt",
                              directory / "requirements.in",
                              read_image(source))
        sections.append(render(source, rows, read_on))
    return "\n\n".join(sections)


def splice(page: pathlib.Path, region: str) -> str:
    """Put the region between the markers and leave every other line alone."""
    text = page.read_text()
    start = text.find(BEGIN)
    stop = text.find(END)
    if start < 0 or stop < 0 or stop < start:
        raise table.Refused(
            f"{page} does not carry {BEGIN} and {END} in that order, so there is "
            "no region to replace and nothing was written. Those two comments "
            "are what keeps this generator away from the hand maintained half of "
            "the file. Put them back around the dependency tables")
    after = f"{text[:start]}{BEGIN}\n\n{region}\n\n{text[stop:]}"
    page.write_text(after)
    return after


def date_on_the_page(page: pathlib.Path) -> str | None:
    """The read date the page already carries, or nothing if it carries none."""
    found = re.search(r"Read on (\d{4}-\d{2}-\d{2}),", page.read_text())
    return found.group(1) if found else None


def region_matches(page: pathlib.Path, region: str) -> bool:
    """Whether what is between the markers is already this."""
    before = page.read_text()
    start = before.find(BEGIN)
    stop = before.find(END)
    if start < 0 or stop < 0:
        raise table.Refused(f"{page} does not carry {BEGIN} and {END}")
    return before[start + len(BEGIN):stop].strip() == region.strip()


def report(page: pathlib.Path, region: str) -> int:
    """Say what --check would change, without changing it."""
    before = page.read_text()
    start = before.find(BEGIN)
    stop = before.find(END)
    if start < 0 or stop < 0:
        raise table.Refused(f"{page} does not carry {BEGIN} and {END}")
    current = before[start + len(BEGIN):stop].strip().splitlines()
    diff = list(difflib.unified_diff(current, region.splitlines(),
                                     fromfile=f"{page.name} today",
                                     tofile="what the lockfiles say", lineterm=""))
    if not diff:
        print(f"{page.name} matches the lockfiles. {len(region.splitlines())} "
              "lines between the markers.")
        return 0
    print("\n".join(diff))
    print(f"\n{page.name} does not match the lockfiles. Nothing was written. "
          "Run tools/attributions/generate.py without --check to update it.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="print the difference and write nothing")
    parser.add_argument("--page", type=pathlib.Path, default=PAGE,
                        help="the markdown file to rewrite between the markers")
    arguments = parser.parse_args()
    # UTC, like the CI timestamps in HANDOFF.md, so a run from the lab in the
    # evening writes a date a Phoenix laptop has not reached yet. That is the
    # same date the rest of this repository's evidence is written in.
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    try:
        # Built twice, against the date already on the page and against today.
        # If the first matches, nothing about the packages changed and the page
        # keeps the date it has, so neither --check nor a write turns a clock
        # into a diff.
        standing = date_on_the_page(arguments.page)
        region = generated_region(standing or today)
        if region_matches(arguments.page, region):
            if arguments.check:
                print(f"{arguments.page.name} matches the lockfiles. "
                      f"{len(region.splitlines())} lines between the markers.")
            else:
                print(f"{arguments.page.name} already says what the lockfiles "
                      "say, so the read date was left alone.")
            return 0
        region = generated_region(today)
        if arguments.check:
            return report(arguments.page, region)
        splice(arguments.page, region)
    except table.Refused as refused:
        print(refused, file=sys.stderr)
        return 1
    print(f"{arguments.page.name} rewritten between the markers, "
          f"{len(region.splitlines())} lines from "
          f"{len(SOURCES)} lockfiles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
