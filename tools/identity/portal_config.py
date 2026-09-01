#!/usr/bin/env python3
"""Hand the members portal the client id the identity service generated for it.

Zitadel generates a client id per instance, so no portal can carry one in its
source. A portal here is static files behind a file server, so a document in the
directory it serves is how the value gets across. This is the one file
configure.py writes, and it is split out of that file because rule 6 caps a
source file at 300 lines and registering the clients is a separate job from
telling a page about them.
"""
from __future__ import annotations

import json
import pathlib

import api
import clients

# The checkout, so the document lands beside the portal whatever the cwd is.
ROOT = pathlib.Path(__file__).resolve().parents[2]


def write_configuration(portal: clients.Portal, application: dict, origin: str) -> None:
    """Put the client id where the portal that signs in with it can read it.

    Zitadel generates one per instance, so no portal can carry a client id in
    its source. A portal is static files behind a file server, so a document in
    the directory it serves is how the value gets handed over.

    Not written on every run, since 2026-08-31. The run that made that a defect
    was not the obvious one: tools/identity/tests/run.sh configures a throwaway
    service on port 8184 that dies with the suite, and the file it left behind
    said `"issuer": "http://localhost:8184"` beside a redirect back to the
    portal a laptop serves on 8080. So running the identity suite repointed a
    working portal at an instance that no longer existed, repeatedly, during an
    audit. The suite passes --no-portal-config now.

    The audit proposed a guard here comparing origins, and that cannot work:
    the suite passes the real portal origin, http://localhost:8080, for a stack
    that serves the portal on 8084 and serves nothing at 8080. The origin it
    passes is a fiction and it is the right fiction, because what is being
    checked is that the identity service sends a browser back there. Nothing in
    this file can tell that apart from a deployment. The caller knows and says.
    """
    where = ROOT / portal.configuration
    document = json.dumps({
        "issuer": api.BASE,
        "client_id": application["oidcConfiguration"]["clientId"],
        "redirect_uri": origin + "/",
        "written_by": "tools/identity/configure.py",
    }, indent=2) + "\n"
    # Registering the clients is what the caller asked for. This file is a
    # convenience for a portal served off this working tree, and several suites
    # run this command with the repository mounted read only, where it cannot be
    # written and does not need to be. Failing the whole run over it turned a
    # green suite red on 2026-08-31 with every client already registered.
    try:
        where.write_text(document)
    except OSError as unwritable:
        print(f"{portal.name}: registered. {portal.configuration} was not "
              f"written ({unwritable.strerror}), so a portal served from this "
              f"tree needs this run repeating where it can be.")
        return
    print(f"{portal.name}: signs in at {api.BASE}, written to "
          f"{portal.configuration}")


