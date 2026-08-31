# tools/attributions

Writes the dependency tables in `ATTRIBUTIONS.md`, which rule 9 of `CLAUDE.md`
asks for. For each Python lockfile it builds the image that lock installs into
and reads every installed package's own metadata out of it, so a licence in the
table traces to the package rather than to an index summary or to memory. It
replaces only what sits between the two marker comments in that file. Prior
work, pinned tooling and the licence gaps are hand written and are not touched.

Two locks today, `services/api/requirements.txt` and
`tools/import-boundaries/requirements.txt`.

## How to run it

    make attributions          rewrite the tables
    make attributions-check    say what would change, and write nothing

The check compares the date the metadata was read as well as the rows, so on a
day after a run it reports that line even when no package changed.

## How to test it

    python3 tools/attributions/test_attributions.py

18 checks over a throwaway lock and a stub of what an image would have
reported. Eight plant something the generator has to refuse rather than write a
row somebody would later cite. Seven plant something correct and require the
right row, because a generator that refuses everything also passes the first
eight. Two build a page rather than a lock, and hold the markers. They need neither docker nor the
network, which is why they are in `make check` and the generator is not.

`--check` is stable on a day nobody touched the repository. It was not at first:
the page said 2026-08-30 while the generator, which stamps UTC, had reached
2026-08-31, so the check reported a diff over a date and nothing else. It
compares against the date already on the page now, and the date moves only when
something else about the table does. A check that goes red on nothing is one
people learn to skip.
[ADR 0012](../../docs/decisions/0012-python-dependencies.md) carries that
decision and what it costs.

## What it depends on

docker, python3, and the network, because building an image installs from PyPI.
Nothing is installed on the machine running it. `read_metadata.py` is the half
that runs inside the image and it imports nothing outside the standard library,
because the image installed the lock and nothing else.
