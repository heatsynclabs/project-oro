#!/usr/bin/env python3
"""Read every installed package's own metadata, from inside a built image.

This is the half that runs in the container. It writes JSON on stdout and the
generator beside it reads that. Standard library only, because it has to run in
an image that installed nothing but the lock it is being asked about.

    docker run --rm -v ...:/reader:ro IMAGE python /reader/read_metadata.py

Rule 9 wants a licence claim traced to the package rather than to a summary
field on an index or to somebody's memory, so the licence here comes from the
package's own metadata and nowhere else. Two fields can carry it. Metadata 2.4
has License-Expression, an SPDX expression, and older packages have License,
which is free text and is sometimes the whole licence pasted in. When neither
gives a usable identifier the generator falls back to the License :: OSI
Approved classifier, and this file hands it all three so it can say which one
it used.
"""
from __future__ import annotations

import importlib.metadata
import json
import platform
import re
import sys


def canonical(name: str) -> str:
    """The name a lockfile and a metadata directory agree on.

    PyPA name normalisation: runs of hyphen, underscore and dot collapse to one
    hyphen, and the result is lowercased. Without it PyJWT, typing_extensions
    and annotated-doc do not match the lines that install them.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def one_package(distribution) -> dict:
    metadata = distribution.metadata
    return {
        "name": distribution.metadata["Name"],
        "version": distribution.version,
        "license_expression": metadata.get("License-Expression"),
        "license_field": metadata.get("License"),
        "classifiers": metadata.get_all("Classifier") or [],
        "requires": list(distribution.requires or []),
    }


def main() -> int:
    packages = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if name is None:
            continue
        packages[canonical(name)] = one_package(distribution)
    # The generator compares this against the --python-version the lock was
    # compiled at. A marker reading one way at one version and the other way at
    # the other would credit a package that never asked.
    json.dump({"python_version": platform.python_version(), "packages": packages},
              sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
