# ADR 0007: which hosted login screens the identity service serves

- **Status:** accepted
- **Date:** 2026-08-28
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in it yet.

## Context

Zitadel 4.17.1 ships two generations of hosted login screens and defaults to the
newer one. The default is wrong for this stack, and it fails in the worst way:
`Features.LoginV2.Required` is `true` out of the box, the authorize endpoint
then redirects a member to `/ui/v2/login`, and the `ghcr.io/zitadel/zitadel`
image does not serve that path. Measured on 2026-08-28: the redirect lands on
`{"code":5, "message":"Not Found"}`.

Every other check written that day passed while that was true, because every
other check speaks to the API. The stack was healthy, the password proof was
green, and no member could have signed in.

The newer screens are a second container, `ghcr.io/zitadel/zitadel-login`,
which authenticates to Zitadel as a machine account holding `IAM_LOGIN_CLIENT`
and needs a token of its own.

## Options considered

### Option A: the screens the same binary already serves

- **What it is:** `Features.LoginV2.Required` set to false, one environment
  variable. The authorize endpoint then sends a member to `/ui/login`, which
  this image serves.
- **Fit:** measured working the same day. A member reaches a page titled
  "Welcome Back!", types a login name, types a password, is offered a second
  factor and may decline it, and arrives back at the portal with a code. It
  reads the label policy, so the GANTRY colours reach it.
- **Cost:** it is the older generation and Zitadel will remove it. Nothing says
  when.

### Option B: the newer screens, as a second container

- **What it is:** `ghcr.io/zitadel/zitadel-login` beside the identity service,
  plus `FirstInstance.LoginClient` and a second token file.
- **Fit:** the direction Zitadel is going, and the only one that will get new
  features.
- **Cost:** a second image to pin, patch and attribute; a second machine
  account; and a second standing credential written to a volume, when the one
  this project already has is an open question in
  [ADR 0004](./0004-identity-service.md). It is also a second thing that can be
  down while the first is healthy, and the failure looks identical to the one
  this record exists because of.

### Option C: leave the default and write our own screens

Rejected without pricing. `docs/plan/architecture.md` section 2 chose Zitadel
partly for having no bespoke login UI, and a login page written here is a
credential path this lab maintains forever.

## Decision

**Option A. One environment variable, one container.**

The deciding argument is not that the older screens are better. It is that this
lab has one identity service to operate and two containers is twice as much of
it, for screens that a member sees and does not otherwise care about. The lab's
constraint is the maintainers, not the machines.

## The condition that would flip this

Either of these, and the second is the likelier:

- Zitadel removes the older screens in a release this project wants to take.
- The lab decides to turn on passkeys or MFA, which
  `docs/plan/order-of-operations.md` lists as later and deliberately not now.
  If those need the newer screens, this decision goes with them.

## Consequences

- A member can sign in. That was not true before this record.
- `tools/identity/tests/check_configuration.py` asserts that the page a member
  is sent to actually serves a field to type a login name into, so this cannot
  regress quietly. Flipping the variable back turns five checks red with the
  words "the sign in page answered 404".
- The screens prompt a member to set up a second factor after the password, and
  the prompt can be declined. Nobody has decided whether it should appear. It is
  an offer rather than a requirement, so it is left alone rather than configured
  away, and it is written down here instead.
- Taking Option B later is additive: a service block, a machine account, a token
  path, and flipping the variable back.

## What was borrowed

Nothing new. The screens are part of the image
[ADR 0004](./0004-identity-service.md) already chose.

## Open questions

Whether the second factor prompt should be shown at all before the lab has
decided anything about MFA. It costs a member one click and it advertises a
feature that is not yet supported.
