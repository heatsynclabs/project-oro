# citations

## What it is

The gate on the line numbers in `docs/api/contract-review-notes.md`.

That file cites `docs/api/members-v1.yaml` by line, and its own preamble says a
citation landing in the wrong place is a defect rather than evidence the finding
is stale. Every edit to the contract moves some of them. Hand correction was
done twice and drifted twice: measured on 2026-08-31, twenty five citations
carried an anchor, one of them landed, and the rest were adrift by as much as
150 lines.

So the number is derived rather than maintained. A citation reads
`` `MyCard` (line 1779) ``, the backticked thing is the authority, and this
finds `MyCard` in the contract and compares. Which makes a citation nothing can
resolve a defect too, because a reader cannot follow it either.

## How to run it

```sh
tools/citations/run.sh
```

Twelve self checks over a throwaway pair of files, then the real document. It is
in `make check` and in CI.

To renumber after editing the contract:

```sh
tools/citations/check_citations.py --fix
```

The default writes nothing. A fixer that runs without being asked is what
`db/tests/run.sh` records as a footgun: capturing output with `--update` once
laundered five failing assertions into expected files.

## How to test it

```sh
python3 tools/citations/test_citations.py
```

Each check plants one thing in a throwaway notes file and a throwaway contract
and requires the checker to report it. The one worth knowing about is
`test_a_citation_naming_another_file_is_left_alone`. The notes cite other files
too, as `` `004_security.sql` line 88 ``, and finding 6 broke that convention
with three bare references into `012_close_remaining.sql`. One of them named
`sort_order`, which is also a property in the contract, so a first draft of this
tool would have renumbered a correct citation to point at the wrong file.
Parentheses are what keep the two apart now, and finding 6 follows the
convention.

## What it depends on

python3 and the two files it reads. No YAML parser: the contract is 2,300 lines
of consistently indented YAML, what is needed is where a key sits, PyYAML
discards line numbers, and a dependency here is one the repository would carry,
patch and attribute under rule 9. So it walks the text by indentation and
refuses rather than guessing whenever it finds no key or more than one.

Two blocks in the notes are exempt and are marked in the file with
`<!-- citations: frozen -->`, the shape the prose gate already uses for a
quotation. Findings 1 and 3 keep a record of the state before an edit, line
numbers included, and renumbering those would destroy the before they exist to
show.

Coverage is partial and every run says by how much. Thirty three line references
in that file carry no backticked anchor, so nothing here checks them, and the
count is printed green or red. A gate that covers part of a file and does not
say which part gets read as covering all of it.
