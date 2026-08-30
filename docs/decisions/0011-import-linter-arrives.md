# ADR 0011: how import-linter arrives

- **Status:** accepted
- **Date:** 2026-08-29
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in it yet, and this record is not complete until a build lead signs it.

## Context

[ADR 0006](./0006-import-boundaries.md) chose `import-linter` for Python and set
its own flip condition: the first commit under `services/api/`. That condition
fired in 432fd1e. This record completes 0006 rather than superseding it. The
tool was already chosen and is not reopened here. What was left open is how it
reaches the machine running the gate.

Two facts shape the answer, and both were measured on 2026-08-29.

**Nobody publishes an import-linter image.** `docker manifest inspect` returns
`manifest unknown` for `ghcr.io/seddonym/import-linter` and for
`ghcr.io/import-linter/import-linter`, and a Docker Hub search for
`import-linter` across 25 results returns nothing related. Every other tool
here runs as an image somebody else publishes, and this one cannot.

**The compiled part still has no wheel for the interpreter on this laptop.**
`import-linter` 2.14 is pure Python. Its engine, `grimp` 3.16, ships 110 files,
and the only macOS arm64 wheel it publishes for 3.14 is
`grimp-3.16-cp314-cp314t-macosx_11_0_arm64.whl`, whose ABI tag is the free
threaded build. A plain CPython 3.14 falls through to the source distribution
and compiles Rust. This laptop runs 3.14.6, so it does exactly that.

The constraint the answer has to satisfy is in `README.md` and holds for every
suite here: a person runs the tests with Docker and python3, and installs
nothing on their own machine.

## Options considered

Every version, date, licence and issue count below was read on 2026-08-29 from
`https://pypi.org/pypi/<name>/json`, from the GitHub API, or from the registry
with `docker buildx imagetools inspect`. Every timing was measured on this
laptop, an arm64 macOS 12 machine running Docker 28.0.4, against the 23 file
graph the two contracts cover. The build times all had `python:3.13-slim`
already local, which is true here because `services/api` uses the same base.

What arrives is `import-linter` 2.14, released 2026-08-28, BSD-2-Clause, 72 open
issues, 44 contributors on GitHub with one of them dominant. It brings `grimp`
3.16, released the same day, BSD-2-Clause, 21 open issues, 15 contributors. Both
were priced in ADR 0006 and neither is what this record is choosing between.

### Option A: an image this repository builds

- **What arrives:** `python:3.13-slim`, index digest
  `sha256:7ce4b6df...`, which is 3.13.15 on Debian trixie and carries
  linux/amd64 and linux/arm64. Its build files are `docker-library/python`,
  MIT, 33 open issues, 57 or more contributors. `pip` 26.2.1, released
  2026-08-04, MIT, 947 open issues, 100 or more contributors, and already in
  the base image.
- **Fit:** 3.13 is the version `grimp` publishes a wheel for on every platform
  this runs on, so nothing compiles. The base is pinned by digest and the
  packages are pinned with hashes, so the gate cannot change under a rerun.
  After the first build there is no network in the path at all: measured with
  `--network none`, the gate ran and reported both contracts kept.
- **Cost:** a Dockerfile and a lock to maintain, and one image built on a
  machine that had none. Cold build, base image already local: 6.26 seconds.
  Warm build plus the run: 0.75 to 1.09 seconds over three runs.

### Option B: uvx inside the uv image, every run

- **What arrives:** `ghcr.io/astral-sh/uv:0.12.7-python3.13-trixie-slim`,
  index digest `sha256:6e00f3cc...`. uv 0.12.7, released 2026-08-27,
  `MIT OR Apache-2.0`, 2,864 open issues, 100 or more contributors, maintained
  by Astral.
- **Fit:** no Dockerfile and no lock. `uvx --from import-linter==2.14
  lint-imports` resolves and runs in one line, and it works: measured against
  the real tree, both contracts kept.
- **Cost:** 1.69 to 1.77 seconds over three runs, and every one of those runs
  reaches PyPI. With `--network none` it fails on
  `error sending request for url (https://pypi.org/simple/import-linter/)`.
  The direct pins hold, the transitive tree is whatever resolves today, and
  nothing about that resolve is recorded anywhere a reviewer can read.

### Option C: pip install inside a pinned python image, every run

- **What arrives:** the same base image and the same pip as Option A, with the
  install moved out of a build and into the run.
- **Fit:** no Dockerfile, and the same pinning is available.
- **Cost:** 3.36 to 3.45 seconds over three runs, four times Option A, and it
  reinstalls the same packages on every invocation for no reason that survives
  being said out loud. It reaches PyPI every run, so it is offline hostile in
  the same way Option B is.

### Option D: pip install on the machine running the gate

- **What arrives:** the same two packages, into whatever Python the person has.
- **Fit:** nothing to build. It is what the tool's own documentation assumes.
- **Cost:** it breaks the constraint every other suite here holds, and this
  laptop shows why that constraint is not decorative. Into a fresh virtual
  environment with `--no-cache-dir`, `pip install import-linter==2.14` took
  37.3 seconds of wall clock and 140 seconds of CPU, compiling `grimp` from
  source because 3.14 gets no wheel. With a warm pip cache the same install is
  1.8 seconds, which is the number somebody will quote after their first run
  and which no clean machine will reproduce.

## Decision

**Option A. The gate builds its own image, from a base pinned by digest and a
`requirements.txt` pinned with hashes, and `tools/import-boundaries/run.sh`
builds it before every run so nobody has to remember to.**

What eliminated the others is the network, not the clock. Options B and C reach
PyPI on every invocation, and a gate that cannot run without the internet is a
gate that stops running the first time somebody is on a train or PyPI is having
an afternoon. Option A reaches the network once per machine, which is the same
bargain every pinned image in this repository already makes. Speed agreed with
that reading rather than driving it: Option A is the fastest of the four and
would not have won on its own.

Option D is the runner up, and only because it is the shape the tool documents.
It is not close. It puts a Rust toolchain in the path of a lint on the one
platform the maintainers do not ship a wheel for, and it installs software on a
volunteer's machine, which is the thing `README.md` promises this project does
not do.

The lock is generated the way ADR 0012 generates the one for `services/api`,
with `uv pip compile --universal --generate-hashes`, so there is one mechanism
for both rather than two. uv runs when somebody changes a version, and never
during a check.

## The condition that would flip this

If `import-linter` or `grimp` starts publishing a container image, delete the
Dockerfile and the lock and pin that image by digest in `run.sh`, the way
`tools/ceilings/run.sh` pins ruff. That is a smaller change than this one and
it should be taken the week it becomes possible.

A second, narrower condition: if `grimp` publishes a standard cp314 wheel for
macOS arm64 and the base image moves to 3.14, nothing about this decision
changes. That fact is why the Dockerfile says 3.13 rather than latest, so it is
written down where somebody bumping the base will read it.

## Consequences

- One more image to build, and it is built on demand rather than pulled. A
  machine with no Docker cannot run this gate, which is already true of eleven
  of the sixteen CI jobs, counted on 2026-08-29 by reading the script each job
  runs.
- The build reaches PyPI. `services/api` already does, so this is not a new
  kind of dependency for the repository, and it is new for `make check`.
- Two files to keep current: `requirements.in` names the two packages and
  `requirements.txt` is the lock. Changing either is the two step in ADR 0012,
  and the header of the generated file is the command.
- Nothing checks that `requirements.txt` still matches `requirements.in`. That
  gap is ADR 0012's open question and this change widens it from one lock to
  two.
- Reversing this is one file and one line: drop the Dockerfile, and put the
  install into the `docker run` as Option C.
- The graph is only as wide as `root_packages`. import-linter follows imports
  out of the packages named there and reads nothing else, so a module outside
  all of them is not a node and a chain through it is invisible. Measured on
  2026-08-29 in a copy of this tree: `services/shared_wire.py` importing
  `door.adapters.oac_ethernet.wire`, and `services/api/app/door_gateway.py`
  importing `shared_wire`, gave "Contracts: 2 kept, 0 broken" and exit 0, while
  the same image running `python -c "import app.door_gateway"` left the door
  service in `sys.modules`. No module in the graph reaches one today: the check
  below reads 23 modules across `app` and `door`, and every import of theirs
  that those two directories provide is inside a declared root package.
  `tools/import-boundaries/check_root_packages.py` now refuses one, and the
  remedy it names works. The same tree with `services/shared/` as a package and
  `shared` on the list reported the contract broken and printed both hops,
  `app.door_gateway -> shared.wire` and
  `shared.wire -> door.adapters.oac_ethernet.wire`. A loose `.py` file cannot go
  on the list at all: import-linter answers "'shared_wire' is a module, not a
  package", so it has to become a directory with an `__init__.py` first.
- The graph is also only as deep as the packages grimp walks, and this one was
  found after the bullet above was written. A directory inside a root package
  holding `.py` files and no `__init__.py` is a namespace package: Python
  imports through it and grimp does not walk into it. Measured on 2026-08-29,
  `services/api/app/gateway/` with no `__init__.py` holding
  `from door.adapters import wire`, imported by `app/main.py`, gave "Analyzed 6
  files, 0 dependencies" and both contracts kept, while the interpreter left
  `door.adapters.wire` in `sys.modules`. Adding one empty `__init__.py` to the
  same tree turned it red. `check_root_packages.py` refuses that too, and it
  leaves alone a directory nothing in a root package imports through, which is
  what `services/door/tests` is.
- The graph is only as literal as the source. import-linter reads imports, and
  a module name written as a string is not one until the call runs. Measured on
  2026-08-30 in a copy of this tree, `door.adapters.oac_ethernet.wire` passed
  from `services/api/app` to `importlib.import_module`, to `__import__` and to
  `importlib.__import__` each gave "Contracts: 2 kept, 0 broken" and exit 0
  while the same image running `python -c "import app.main"` left the door
  service in `sys.modules`. A PEP 562 `__getattr__` in `app/__init__.py` did the
  same with nothing that reads as an import anywhere in the members API.
  `check_root_packages.py` now refuses a call to any of those three whose first
  argument is a literal naming a root package, and leaves alone a literal naming
  anything else, because loading a module by name is ordinary Python.
- What that check cannot reach is a name the source does not hold.
  `import_module("door." + part)`, or a name read out of a config file, is not
  in the file for any tool that reads source to find, so a computed name
  reaching a root package is a rule 5 violation the tooling does not catch and
  review is what stands behind it. Nothing under `services/`, `packages/`,
  `apps/` or `tools/` imports dynamically today, checked on 2026-08-30 by
  grepping every `.py` file for `import_module` and `__import__`.

## What was borrowed

`import-linter` and `grimp`, BSD-2-Clause, installed unmodified from PyPI into
an image built here. `python:3.13-slim`, MIT for the build files it is made
from, run unmodified. Nothing is vendored and no code is copied.
`ATTRIBUTIONS.md` carries all three.

The Dockerfile takes its shape from `services/api/Dockerfile`, which is this
repository's own, including the hashed install and the non root user.

## Open questions

- The contracts cover `services/` only. `apps/` holds no Python:
  `git ls-files 'apps/**/*.py'` returns nothing on 2026-08-29. `packages/` holds
  seven files, all under `packages/gantry-tokens/validator/`, and they are not a
  package. There is no `__init__.py`, each one puts its own directory on
  `sys.path` and imports its siblings by bare name, and import-linter refuses a
  bare module as a root package. Rule 5's arrow from `packages/` down to
  `services/` also has nothing to hold there yet, because the validator imports
  the standard library and the files beside it and reaches nothing else. The
  JavaScript half of ADR 0006 is still owed on its own flip condition.
- `services/api/app` is importable as `app` and `services/door` as `door`,
  which is why `run.sh` puts two directories on `PYTHONPATH` for a repository
  with two packages in it. If a third service arrives, that line grows. Giving
  `services/` an `__init__.py` would make it one root package and one path, and
  it would rename every import in the door suite, so it is worth doing on the
  day a third service lands and not before.
