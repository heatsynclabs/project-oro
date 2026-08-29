# ADR 0010: no bootstrap token on the first instance

- **Status:** proposed. It answers the second open question in [ADR 0004](./0004-identity-service.md), and it is not accepted until the deciders below are named
- **Date:** 2026-08-28
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in it yet. This one needs the secret custody row filled, because it changes who can administer the identity service and how.

## Context

`compose.yaml` creates a machine account called `oro-bootstrap` on the first
instance and writes its personal access token into the `identity_bootstrap`
volume. That token administers everything. It is written once by the first
setup, it survives every restart and recreate, it expires on
2027-08-28T00:00:00Z, and nothing in this repository reads that date. The
variable that sets it is written in one place only, `compose.yaml`, and no code
anywhere looks at it.

Rule 13 of `CLAUDE.md` gives each secret that matters exactly one holder process.
This one has none. It is a file in a volume, and the three things that read it
are a person's shell: the `identity-configure` target in the `Makefile`, the
copy command in `tools/identity/README.md`, and `tools/identity/tests/run.sh`.

`make identity-configure` was the last thing that needed it and it now exists,
so `HANDOFF.md` section 6 item 6 says the moment has arrived to revoke the token
or to decide it should not be minted.

## Options considered

Every measurement below was made this session against running instances of the
image `compose.yaml` pins, Zitadel 4.17.1. Each API path was checked by first
calling a plausible wrong one on the same prefix and reading the 404, so no path
here is a guess.

### Option A: mint it, then revoke it once `configure.py` has run

- **What was checked:** `DELETE /management/v1/users/{userId}/pats/{tokenId}`
  answered 200, and the same token then failed on two calls that had answered
  200 moments earlier, both with 401 `Errors.Token.Invalid (AUTH-7fs1e)`. The
  same path with a `_revoke` suffix answered 404, so the shape is read rather
  than assumed.
- **Holder, rule 13:** no process. A file in a named volume until somebody runs
  one command, and readable in the meantime by anything that can reach the
  Docker socket or mount that volume.
- **Fit:** nothing in the stack changes. It is what `compose.yaml` already says
  in a comment should happen.
- **Cost:** revoking does not remove the file. `/bootstrap/pat` still held the
  same 277 bytes after the successful `DELETE`, byte identical to the token that
  had just been killed, so the volume keeps a dead credential that looks live to
  whoever copies it out next. It is a step nobody is reminded to take and
  nothing checks. And a later re-run of `configure.py` used to fail naming
  the wrong operation: `could not create the project: 401 Errors.Token.Invalid`,
  because `api.search()` read a result list out of a refusal without looking at
  the status, so the 401 on the project search became an empty list and the next
  step tried to create a project that was already there. That was fixed in the
  same change that opened this record, and
  `tools/identity/tests/check_api_refusals.py` holds it fixed. The measurement
  above was taken before the fix, so the misleading message is what a reader of
  an older checkout would see.

### Option B: keep the account, write no file

- **What it is:** clearing `ZITADEL_FIRSTINSTANCE_PATPATH` and nothing else.
- **What was checked:** a stack booted that way came up healthy and had no file:
  `docker compose cp identity:/bootstrap/pat -` answered `Could not find the
  file /bootstrap/pat in container`. An administrator token obtained another way
  then found `oro-bootstrap` still there, `TYPE_MACHINE`, holding `IAM_OWNER`,
  with exactly one personal access token on it expiring 2027-08-28T00:00:00Z.
- **Holder, rule 13:** nobody, which is the problem rather than the fix. The
  credential is live and no operator can produce it.
- **Cost:** every reader of the token breaks and the standing credential
  survives. This is priced here because it is the obvious first move and it
  looks like it worked.

### Option C: create no machine account at all

- **What was checked:** the image is distroless and carries no configuration
  file to read, so its defaults were extracted from the `/app/zitadel` binary
  itself. They state the condition in prose: if `FirstInstance.Org.Machine.Machine`
  is defined, a service account is created with the `IAM_OWNER` role. A stack
  booted with `ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINE_USERNAME`,
  `ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINE_NAME` and
  `ZITADEL_FIRSTINSTANCE_PATPATH` all set to empty came up healthy, had no
  `/bootstrap/pat`, returned exactly one user from
  `POST /management/v1/users/_search`, and returned exactly one `IAM_OWNER` from
  `POST /admin/v1/members/_search`. Both were the initial human administrator.
- **What was checked about the replacement:** the console client id is served
  publicly at `/ui/console/assets/environment.json` with no bearer. Signing in
  as the initial human administrator through the hosted screens with the
  reserved scope `urn:zitadel:iam:org:project:id:zitadel:aud` produced a token
  the admin API accepts, and `configure.py` then ran end to end with it on a
  stack that had never had a bootstrap token and had never been configured.
- **Holder, rule 13:** the person who signs in, for the life of one token.
  Nothing is written to disk and there is no standing credential between runs.
- **Cost:** three readers of `/bootstrap/pat` stop working and their replacement
  is not written. The operator's token has a lifetime nobody has measured.

### Option D: keep it, and bound it

- **What it is:** a shorter expiry, or the file somewhere that does not persist.
- **What was checked:** the running instance reported exactly the date
  `ZITADEL_FIRSTINSTANCE_ORG_MACHINE_PAT_EXPIRATIONDATE` carries, so the date is
  settable from configuration. The other half has a measured dead end already in
  `HANDOFF.md` section 7: a tmpfs was tried, `docker cp` reads the container
  filesystem and a tmpfs is not part of it, and `docker cp` is the only way into
  a distroless image.
- **Holder, rule 13:** still a file in a volume, which is what rule 13 objects
  to. Shortening the expiry does not give it a holder.
- **Cost:** it buys a date that nothing reads. A credential with an expiry and
  no watcher fails on a day nobody chose, which is how a door goes down at 2am.

### Option E: mint a service account this project holds

- **What was checked:** all of it, on a throwaway stack, after the bootstrap
  token had been revoked. `POST /management/v1/users/machine` created the user,
  `POST /management/v1/users/{id}/pats` minted a token with an expiry we chose,
  and `POST /admin/v1/members` granted it `IAM_OWNER`. `configure.py` then ran
  to completion with that token.
- **Holder, rule 13:** `.env` on the host, which already holds the master key
  and the database password, so there is a real answer to give.
- **Cost:** it is the same standing credential under a name we picked, and
  creating it needs the same human administrator sign in that Option C uses. If
  that sign in works, the token it already produces runs `configure.py`, so the
  extra credential adds a secret and buys nothing.

## Decision

**Option C. No machine account, so there is no token to leak, to revoke, or to
leave behind.**

Rule 13 decided it. A credential that administers the whole instance has to have
one holder process, and under A, B and D the holder is a file in a volume for
some window, which is not a process and cannot be asked who it is. Under E there
is a holder, and the credential it holds is standing and permanent, obtained
through a sign in that makes it unnecessary.

What made C available rather than theoretical is the measurement above: an
administrator credential can be produced against an already running instance
with no bootstrap token, and `configure.py` ran with it. Before that was
measured, ADR 0004 priced the alternative to a standing credential as "a console
click that phase 2 says should not be needed". No click is involved. It is a
sign in as a named person, driven by a script in this repository, and what phase
2 asks for is no console click that is not also in configuration.

The suite keeps its own token, through an override file of its own.
`tools/identity/tests/run.sh` creates a compose project, boots it, reads the
token, and destroys it with its volumes on exit. A credential that exists for
the length of one script has a different question attached to it than one that
sits on the lab's server for a year, and the two should not be answered the same
way.

**Nothing in this repository implements this yet.** `compose.yaml` still mints
the account and still writes the file. The change is four edits and they belong
in one commit, because any subset of them leaves the stack unable to configure
itself:

1. `tools/identity/admin_token.py`, new, which reads the console client id from
   `/ui/console/assets/environment.json`, drives `tools/identity/flow.py`
   through the hosted screens as the administrator named in `.env`, and prints
   an access token. The reserved audience scope is what makes that token work on
   the admin API, and it is not optional.
2. `compose.yaml`, setting the two machine account variables and
   `ZITADEL_FIRSTINSTANCE_PATPATH` to empty rather than deleting the lines, with
   a comment saying why the names are still there. Empty is the shape that was
   measured. Absent was not.
3. A third compose file under `tools/identity/tests/` putting all three
   variables back, and `run.sh` passing it after the other two. Later files win,
   which is how `compose.development.yaml` already overrides
   `ZITADEL_EXTERNALSECURE` for every run of that suite.
4. The `identity-configure` target in the `Makefile` and the command in
   `tools/identity/README.md`, both off `docker compose cp` and onto the new
   script.

## The condition that would flip this

If an administrator cannot sign in and obtain an instance token against the
deployment shape, behind Caddy on a real hostname with TLS, this decision is
wrong and Option A becomes correct. The check is one run of `admin_token.py`
against a stack brought up from `compose.yaml` alone, and it has not been run.

## Consequences

- **The day somebody re-runs `configure.py`, they sign in as themselves.** They
  need the administrator's current password, and the token they get back is good
  for one run. There is a trap in that path worth knowing before 2am: without
  the scope `urn:zitadel:iam:org:project:id:zitadel:aud` the token is refused by
  the admin API with 401 `Errors.Token.Invalid (AUTH-7fs1e)`, which reads like a
  bad token and is a missing scope. That string belongs in the runbook and in a
  comment beside the request that sends it.
- **If the administrator's credential is also lost, there is no measured way
  back in.** `ORO_IDENTITY_ADMIN_PASSWORD` is read once at first boot and
  `ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORDCHANGEREQUIRED` is true, so `.env`
  stops holding the live password the moment somebody signs in. Nothing in
  `compose.yaml`, `compose.development.yaml` or `.env.example` configures a mail
  server, so a password reset by email has nothing to send with, and no reset
  was tested. This decision therefore commits the lab to a second human
  administrator on the instance, created before the first one is relied on.
  `people-and-custody.md` section 1 asks for two holders of every role for the
  same reason, and this is that rule reaching the identity service.
- **The failure that `HANDOFF.md` section 7 calls unrecoverable can no longer
  start the way it starts today.** That trap begins with the setup dying on
  `open /bootstrap/pat: permission denied` after writing half the first
  instance. With no file to open, that cause is gone, and a stack with the
  account cleared came up healthy. The recovery it records was checked against
  `compose.yaml` and it holds, and it is worse than the sentence suggests:
  `docker compose down --volumes` removes `db_data`, and `db_data` is the whole
  Postgres cluster, so it destroys the members database in the same breath as
  the identity one. Neither is declared external.
- **A failed configuration run is not a door outage.** `configure.py` registers
  OIDC clients for portals, and the door service has not been built, so nothing
  between a card and the door passes through any of this. That stays true only
  while phase 5 designs it that way, per gate 2 of rule 12.
- **Reversing this is cheap on a new instance and is not on an existing one.**
  Three variables go back and the stack is recreated from nothing. On an
  instance that has already been seeded, putting them back changes nothing,
  because the first setup records that it ran and every later start skips it.
  Reversal there means creating the account through the API, which is Option E.

## What was borrowed

Nothing is vendored and no code is copied. The configuration key names and the
sentence describing when a service account is created were read out of the
Zitadel 4.17.1 image itself, AGPL-3.0, run unmodified and pinned by digest in
`compose.yaml`, and recorded in `ATTRIBUTIONS.md` by ADR 0004.

## Open questions

- Whether the text embedded in the binary is the same document the Zitadel
  repository calls `cmd/defaults.yaml` at tag v4.17.1. Resolve by fetching that
  file at the tag and diffing the `FirstInstance` block against the bytes read
  here. This affects the provenance of the key names only. The keys themselves
  were proven by booting an instance with them set.
- Whether any of this holds on the deployment shape. Every stack measured was
  brought up with `compose.development.yaml`, so `ZITADEL_EXTERNALSECURE` was
  false, the service answered plain HTTP on loopback, and Caddy never started.
  Resolve by repeating the sign in and one `configure.py` run against
  `compose.yaml` alone on a real hostname. The console sign in is the part most
  likely to differ, because it depends on redirect URIs and cookies.
- How long the operator's token lives. It is a JWE and its claims cannot be
  read, so the ten minute lifetime this instance is configured for was confirmed
  on a portal token rather than on this one, at 600 seconds between the issued
  at and expiry claims. Resolve by introspecting one, through whichever endpoint
  the discovery document names, or by holding one for eleven minutes and calling
  an `/admin/v1` path again. If it is ten minutes, a slow configuration run could expire
  part way through.
- What the second factor prompt does to the recovery path. MFA was left at its
  defaults and the scripted sign in skips the prompt. `HANDOFF.md` section 6
  item 7 has MFA undecided. Resolve by running the same sign in with a second
  factor enforced. If the only administrator loses their second factor, this
  question becomes the previous one about lost credentials.
- Whether a person in a browser reaches the same place the script does.
  `flow.py` speaks the protocol underneath the hosted screens and says so in its
  own header. Resolve by opening the hosted console in a browser against a
  running stack and signing in.
- Whether the `identity_bootstrap` service and its volume are still needed once
  nothing writes to `/bootstrap`. Both ran on every stack measured and neither
  was removed. Resolve by bringing up a stack without them. This is a tidy up:
  if the service turns out to be doing something else, the stack fails to start
  rather than starting wrong.
- What recovery looks like from an instance with no administrator credential at
  all. Nobody has measured one. Resolve on a throwaway stack, by reading whether
  `/app/zitadel` carries a subcommand that grants `IAM_OWNER` against an
  existing database, and by attempting a password reset with no mail server
  configured.
- Whether `/oauth/v2/revoke`, which the discovery document advertises, also
  revokes a personal access token. Not tested, because the management API delete
  was proven and one working revocation is enough. It matters only if this
  decision flips to Option A.
