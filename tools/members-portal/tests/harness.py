#!/usr/bin/env python3
"""The parts of the portal checks that are not themselves checks.

One HTTP client pointed at the running stack, one reader for the compose file
and the Makefile the page sends a reader to, and the runner that prints the
result. check_portal.py holds the checks and nothing else, which is what keeps
that file inside the ceiling in rule 6 of CLAUDE.md.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("ORO_PORTAL_URL", "http://localhost")
# The compose project the stack under test runs as. run.sh uses a throwaway
# name so it never reads a stack somebody is already running; make development
# uses the name in compose.yaml, which is the default here.
PROJECT = os.environ.get("ORO_PORTAL_PROJECT", "oro")

ROOT = Path(__file__).resolve().parents[3]
PORTAL = ROOT / "apps" / "members"

MISSING = object()


class Answer:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        return json.loads(self.body)


def fetch(path, headers=None):
    request = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(request) as answer:
            return Answer(answer.status, answer.headers, answer.read().decode())
    except urllib.error.HTTPError as refused:
        return Answer(refused.code, refused.headers, refused.read().decode())


def portal_token():
    """The bearer token the portal sends, read out of its own source. Hard coded
    here instead and this passes while the page sends what the mock refuses."""
    source = (PORTAL / "api.js").read_text()
    found = re.search(r'CONTRACT_MOCK_TOKEN = "([^"]+)"', source)
    assert found, "api.js does not declare CONTRACT_MOCK_TOKEN"
    return found.group(1)


def signed_in(path):
    return fetch(path, {"Authorization": "Bearer " + portal_token(),
                        "Accept": "application/json, application/problem+json"})


def resolve(record, dotted):
    """Follow a dotted field path into a record, or MISSING if it is not there."""
    value = record
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return MISSING
        value = value[part]
    return value


def recipe(target):
    """The command lines of one Makefile target, as one string."""
    lines = (ROOT / "Makefile").read_text().splitlines()
    out, inside = [], False
    for line in lines:
        if re.match(rf"^{re.escape(target)}:", line):
            inside = True
        elif inside and not line.startswith("\t"):
            break
        elif inside:
            out.append(line.strip())
    return "\n".join(out)


def compose_logs():
    """What the logs target prints, minus the following.

    Both compose files, which is the shape the target uses, because the mock is
    declared in the override and compose omits a service it was not told about.
    The target itself follows and never exits, so this is the same command
    without that."""
    ran = subprocess.run(
        ["docker", "compose", "-p", PROJECT, "-f", "compose.yaml",
         "-f", "compose.development.yaml", "logs", "--tail", "20"],
        cwd=ROOT, capture_output=True, text=True, check=False)
    return ran.stdout + ran.stderr


def caddy_bind_sources():
    """Every path on the host that compose.yaml binds into the caddy service.

    Read by hand rather than with a YAML parser, because a parser is a
    dependency and this needs one block of one file. A named volume has no
    slash in it and is not a path on the host, so it is not one of these.
    """
    lines = (ROOT / "compose.yaml").read_text().splitlines()
    sources, inside, volumes = [], False, False
    for line in lines:
        if re.match(r"^  \S", line):
            inside = line.strip() == "caddy:"
            volumes = False
        elif inside and re.match(r"^    \S", line):
            volumes = line.strip() == "volumes:"
        elif inside and volumes and line.strip().startswith("- "):
            source = line.strip()[2:].split(":")[0]
            if "/" in source:
                sources.append(source)
    return sources


def run(checks, what: str = "portal") -> int:
    """Run every test_ function in a namespace and report what failed.

    `what` names the suite in the summary line, because there are two of them
    now and a reader looking at a red run needs to know which one went red."""
    found = [(name, function) for name, function in sorted(checks.items())
             if name.startswith("test_") and callable(function)]
    failed = []
    for name, function in found:
        try:
            function()
        except AssertionError as problem:
            failed.append(name)
            print(f"FAIL  {name}\n        {problem}")
        except Exception as problem:  # noqa: BLE001
            failed.append(name)
            print(f"ERROR {name}\n        {type(problem).__name__}: {problem}")
    print(f"\n{len(found) - len(failed)}/{len(found)} {what} checks passed")
    return 1 if failed else 0
