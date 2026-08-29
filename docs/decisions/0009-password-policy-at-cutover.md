# ADR 0009: the password policy on cutover day

- **Status:** proposed
- **Date:** 2026-08-28
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in
  it yet. This record is not accepted until a build lead and a migration owner
  hold it, and both of those rows read TBD today.

## Context

`HANDOFF.md` section 7 carries the measurement that forces this. Every migrated
member can sign in, and most of them cannot change their password. The legacy
application asked for six characters and nothing else. Zitadel 4.17.1 defaults
to eight characters with an uppercase, a lowercase, a number and a symbol, and
`compose.yaml` sets no password complexity variable at all, so that default is
what this stack runs today. An imported hash is a hash rather than a password,
so it never meets the policy and the member gets in. The wall is the first
password change.

The password this decides the strength of does not open the door. Cards do,
and rule 12's second gate keeps it that way through every phase. A member's
password reaches the members portal, and an administrator's password reaches
the portal that will issue cards, which is why the answer is not obviously
"make it easier".

`HANDOFF.md` section 6 item 11 asked for this decision and now points here.
This record proposes an answer and does not make one. The people who accept it are
the build lead and the migration owner named in `people-and-custody.md`
section 1, and until those rows carry names there is nobody who can.

Every endpoint, refusal and environment variable quoted below was measured on
2026-08-28 against running instances of the image `compose.yaml` pins, on
throwaway compose projects that were taken down afterwards. Where nothing was
measured, the option says so instead of guessing.

## Options considered

The template's per option shape asks for a release, a licence and a maintainer,
which is the shape of a dependency choice. This is a configuration choice
inside a dependency [ADR 0004](./0004-identity-service.md) already made, so the
shape here is the one [ADR 0007](./0007-hosted-login-screens.md) used: what the
option is, what was measured about it, then what it costs.

### Option A: relax the policy to what the legacy application asked for

- **What it is:** minimum length 6 with all four character class requirements
  off, so no member is ever refused a password they could have used before.
- **What was measured:** `PUT /admin/v1/policies/password/complexity` with that
  body returned HTTP 200 and the policy read back as minimum length 6. A member
  imported with a real bcrypt hash out of
  `tools/migration/fixtures/legacy-data.sql` then had their password set to
  `sixchr`, and that call returned HTTP 200 where the same call under the
  default policy had returned 400. The five keys that set this at instance
  creation, `ZITADEL_DEFAULTINSTANCE_PASSWORDCOMPLEXITYPOLICY_MINLENGTH`,
  `_HASLOWERCASE`, `_HASUPPERCASE`, `_HASNUMBER` and `_HASSYMBOL`, were read out
  of the image's own embedded defaults rather than from memory, then proven by
  booting an instance with the length at 6 and the four flags false. That
  instance accepted a six character lowercase password at its forced first sign
  in.
- **Cost:** it puts a six character floor under every password in the system and
  leaves it there for as long as nobody revisits it. The members it is meant to
  spare are the ones who never change their password, so the relaxation is
  permanent by construction. It reaches none of the members the 72 byte defect
  locks out.

### Option B: keep the policy, write it down, and tell members before the day

- **What it is:** the length and the four requirements stay where the image puts
  them, set explicitly in `compose.yaml` rather than inherited, and the
  membership is told what the rule is before cutover rather than at a refusal.
- **What was measured:** nobody is locked out by this. The fixture member
  `six@fixture.invalid`, imported with the hash the legacy replica wrote, signed
  in with `sixchr` and the session call returned HTTP 201 while the default
  policy was in force. The refusals afterwards name the rule that was broken
  rather than returning one generic message: `sixchr` was refused with "Password
  is too short (DOMAIN-HuJf6)", `correct horse battery staple` with "Password
  must contain upper case (DOMAIN-VoaRj)", `sixchrA1` with "Password must
  contain symbol (DOMAIN-ZDLwA)", and `Sixchr1!` was accepted with HTTP 200.
- **Cost:** the lab has to reach the whole membership before the day, and every
  member who wants a new password has to write a longer one than they used to.
  How many members that inconveniences is not known and cannot be read out of
  the hashes, because reading it would need the plaintext.

### Option C: keep the policy and guide the first password change in the portal

- **What it is:** the policy stays, and `apps/members` gains a screen that
  states the rule before a member types rather than after.
- **What was measured:** `apps/members` has no password screen of any kind.
  `grep -ril password apps/` matches nothing, so this is new work in a portal
  that today renders member data against the mock server.
- **Cost:** unpriced, because nobody has built it. Pricing it needs an answer to
  a question nobody has asked the service. Both policy reads that
  were measured carried an administrator bearer token. Whether a public portal
  can read the complexity policy at all was not measured, and if it cannot,
  this option means the rule is copied into the portal by hand. Rule 5 permits
  that only when the copy is labelled a courtesy and the identity service stays
  the one place that decides.

### Option D: a policy between the two, length only

- **What it is:** a longer minimum, eight or more, with the four character class
  requirements off.
- **What was measured:** length and each character class are checked separately,
  which is what makes this option possible rather than imagined. Under the
  default policy `Sixchr1` was refused as too short at seven characters while
  `sixchrA1` was refused for a missing symbol at eight, so the two halves of the
  policy fail independently. Each flag is settable on its own through the same
  admin endpoint.
- **Cost:** the number that would be chosen has nothing behind it. Option A can
  point at devise, Option B can point at the image's defaults, and a middle
  number is a value somebody picked in a meeting and cannot explain at 2am. It
  refuses an unknown share of existing passwords, exactly as Option B does,
  while giving up the one thing Option B has, which is a stated source.

### Option E: an organisation override, relaxed for a window and then removed

- **What it is:** leave the instance default alone, create a relaxed policy on
  the HeatSync Labs organisation for the cutover window, and delete it when the
  window closes.
- **What was measured:** the whole cycle works.
  `POST /management/v1/policies/password/complexity` created an organisation
  policy at minimum length 12 while the instance default sat at 6, a password
  the instance default had just accepted was then refused, and `DELETE` on the
  same path returned HTTP 200 with the read falling back to the instance
  default. One trap came with it: `PUT` on that path returns HTTP 404 and
  "Password Complexity Policy not found (ORG-Dgs3g)" when no organisation
  policy exists yet, so anything scripting this has to create with `POST` and
  update with `PUT`, which is the shape `api.apply_branding` already uses for
  the label policy.
- **Cost:** nothing expires the override and nothing watches it. A relaxation
  that outlives its window is the same failure as the bootstrap token in
  ADR 0004, which has been open since the day it was minted and is item 6 of
  `HANDOFF.md` section 6. Two policies also means a volunteer reading one of
  them can be reading the wrong one.

### Option F: force a password reset for the whole membership at migration

- **What it is:** no legacy password carries forward. Every member sets a new
  one before they can use the portal.
- **What was measured:** this is the only option that also reaches the members
  the 72 byte defect locks out, which is why `tools/identity/README.md` names it
  as the only complete fix for that defect. Against it: nothing in `compose.yaml`,
  `compose.development.yaml` or `.env.example` configures a mail server, so the
  identity service has no sender and cannot send anybody a reset link today.
- **Cost:** a sender to configure, hold and back up, plus a cutover day on which
  no member can get into the portal until they have read their mail. The door
  keeps opening on cards throughout, so this is a portal outage rather than a
  building one, which is the only reason it is priceable at all.

## Decision

We propose Option B, and the policy is written into `compose.yaml` as the five
variables Option A measured rather than left inherited.

The constraint that eliminates the others is that no policy setting keeps
anybody out on cutover day. An imported hash bypasses complexity entirely, and
that was measured on a member carrying a hash the legacy replica wrote: signed
in with a six character password, HTTP 201, under the strict default. So
relaxing the policy buys nothing on the day itself. What it buys is a weaker
floor on every password set afterwards, permanently, on the system that will
issue cards.

Writing the values into `compose.yaml` even though they equal today's defaults
is the same discipline phase 2 step 2 applies to the bcrypt cost: do not
inherit a default unexamined. A Zitadel release is free to move its own default,
and the difference between a policy this lab chose and a policy it received is
one line in a file.

Two things go with the choice, and the decision is incomplete without them.

**The notice is required, not optional.** A member who is told in advance meets
a rule; a member who is not meets a refusal from a system that just replaced the
one they knew. The refusal text is good, and that was measured. It is still the
worse of the two ways to learn.

**Phase 2 part (b) measures the cohort nobody can size.** That step already
asks ten volunteers to sign in to staging with the password they already use.
Ask each of them, once they are in, to set their password to that same value. A refusal means that member's existing password fails the policy, and
the count of refusals is the number this decision has been missing. Nobody sees
a plaintext at any point: the member types it and the service answers. That
design comes straight from the measurement in Option B, where one member did
exactly this by accident.

### The members the 72 byte defect locks out

No policy choice reaches them. A password over 72 bytes verifies in the Rails
application and fails in the identity service, the failure arrives as HTTP 500
with the text `An internal error occurred`, and the members it affects cannot be
found in advance because finding them would need the plaintext. They need a
reset path that exists before cutover day rather than after, and under this
decision that path is an administrator setting a password for them directly:
`POST /v2/users/{userId}/password`, which returned HTTP 200 for a value meeting
the policy. Three things follow that are work, not decisions:

- The path needs an administrator credential. After `HANDOFF.md` item 6 revokes
  the bootstrap token, the measured way to get one is a sign in through the
  console as the initial human administrator.
- With no mail sender configured, the temporary password is handed over by a
  person, through a channel the lab already uses, and changed immediately.
- `docs/runbooks/` holds nothing. The directory is on disk, empty and
  untracked, so a fresh clone does not have it, and rule 10 says it is created
  with the first runbook. The runbook this decision owes is the one that
  creates it, because a volunteer at the desk on cutover day has to read an
  HTTP 500 as a long password rather than as an outage.

## The condition that would flip this

If three or more of the ten volunteers in phase 2 part (b) cannot re-set their
existing password because the policy refuses it, this decision is wrong and
Option D becomes correct at a length the same measurement will have named. Three
of ten is a threshold chosen here, not a measured one, and it is written as a
number so that a year from now somebody can answer yes or no.

## Consequences

- The policy stops being a default and becomes a line somebody wrote. A Zitadel
  upgrade that moves its own default no longer moves this stack's.
- The membership has to be reached before cutover day, which is a scheduling
  task on the same list as the part (b) volunteers and belongs to the same
  person.
- Phase 2 part (b) gains a step and produces a number. That number is the only
  evidence this decision will ever have about its own cost.
- A runbook is now owed for a member who cannot sign in at all, covering the
  72 byte case and the administrator reset. It is required before cutover, not
  after.
- Reversing this is one call, `PUT /admin/v1/policies/password/complexity`, which
  was measured taking effect immediately on a running instance and reading back
  changed. The compose variables would be edited in the same change so the file
  and the instance do not disagree. Nothing about member data moves either way.
- Every password set after cutover is longer than what the lab asked for before
  it, so any member who has to type one at the desk will find it slower.

## What was borrowed

Nothing new. The policy values are the ones built into the Zitadel image that
[ADR 0004](./0004-identity-service.md) chose, AGPL-3.0, run unmodified and
pinned by digest in `compose.yaml`, and already recorded in `ATTRIBUTIONS.md`.
What is taken is the default itself: a length of 8 with all four character
classes required, read out of the image's own embedded defaults rather than
from documentation.

## Open questions

Five, each with the step that settles it.

```
ASSUMPTION: setting the five PASSWORDCOMPLEXITYPOLICY variables changes the
  policy only at first instance creation, which is what their names say and
  what was proven on fresh instances.
CONFIRM BY: change one of them on a stack whose instance already exists,
  restart the identity service, and read
  GET /admin/v1/policies/password/complexity.
BLAST RADIUS: whether editing compose.yaml is enough to change the policy on
  a deployed stack, or whether the admin PUT is also required. If it is the
  second, the runbook needs both steps.
```

```
ASSUMPTION: these measurements hold on the deployment shape as well as the
  laptop shape. Every stack behind them ran compose.development.yaml, where
  ZITADEL_EXTERNALSECURE is false and Caddy is not started. compose.yaml sets
  it true.
CONFIRM BY: repeat one policy read and one refusal against a stack brought up
  from compose.yaml alone, behind Caddy, on a real hostname.
BLAST RADIUS: the refusal text a member meets through the hosted screens,
  which is the part of this decision a member actually experiences.
```

```
ASSUMPTION: the key names extracted from the image binary are the same
  document Zitadel publishes as cmd/defaults.yaml at tag v4.17.1.
CONFIRM BY: fetch that file at the tag and diff its PasswordComplexityPolicy
  block against the extracted bytes.
BLAST RADIUS: provenance only. Booting an instance with the keys set proved
  they work, so the measurement stands even if the file name is wrong.
```

- Whether a public portal can read the complexity policy without an
  administrator token. Both measured reads carried a bearer. The step is one
  unauthenticated `GET` against each of the two policy paths, and the answer
  prices Option C, which is otherwise unpriceable.
- Whether the hosted password change screen at `/ui/login/password/change`
  states the rules before a member types. That screen was seen during a forced
  first sign in, and what it says was not read. If it states them, the notice
  in this decision gets shorter.
