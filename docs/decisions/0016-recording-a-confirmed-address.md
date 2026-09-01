# ADR 0016: Recording that a member's address is confirmed

- **Status:** proposed
- **Date:** 2026-08-31
- **Deciders:** TBD. `docs/plan/people-and-custody.md` names nobody yet.

## Context

`members.email_verified_at` is written by nothing. The only writers anywhere in
this repository are two test fixtures and the trigger that clears it, measured
by grep on 2026-08-31, so a member who has typed a code out of the lab's own
mail is shown "Confirmation not recorded" for as long as the column exists.
The portal says that rather than promising a state nobody can reach, which is
honest and is not a fix.

Item 21 of `HANDOFF.md` section 6 said the fix needed a claim the access token
does not carry, and that this was therefore a change to what the portal asks for
and to what the identity service asserts. **Two measurements on 2026-08-31 say
that is wrong in one half and right in the other**, and both were taken against a
deployment shaped stack running Zitadel 4.17.1.

The portal already asks for the `email` scope, in `apps/members/identity.js`.
Asking for it buys nothing. Signing a member in through the real screens under
`openid profile offline_access` and again under `openid profile email
offline_access` produced the same eight claims both times, `aud`, `client_id`,
`exp`, `iat`, `iss`, `jti`, `nbf` and `sub`, and the id token carried no address
either. So the scope is not what is missing.

`GET /oidc/v1/userinfo`, called with the member's own access token and nothing
else, answered 200 with `email`, `email_verified` true, and a `sub` matching the
token. No credential of this service's is involved and no administrator token is
needed: the member's bearer is the authorisation.

So the address is available today. What it costs is the thing this decision is
actually about.

## Options considered

### Option A: the members API calls userinfo on `POST /me`

- **What was checked:** the call above, from a container on the same host,
  answering 200 with `email_verified` true.
- **Fit:** one extra HTTP call, on the first sign in only, on a path that is
  already writing a record. The route through Caddy is the one
  `caddy/routes/deployment.caddyfile` already opens for the key set, with the
  same Host rewrite and one more `handle`.
- **Cost:** it breaks the property `services/api/app/identity.py` states in its
  first paragraph and treats as the point of the design, that this service asks
  the identity provider nothing on the request path. A provider that is down
  would slow `POST /me` down, which is the one request a member cannot retry
  their way past. It also needs a schema change: `SET_THE_ADDRESS` in
  `app/first_sign_in.py` runs as `oro_api` with an identity set, so
  `enforce_profile_self_edit` refuses a write to `email_verified_at` from it
  with "A member cannot mark their own email verified." Recording a
  confirmation the identity service asserted is a system path, and
  `db/migrations/008_system_paths.sql` is where system paths live.

### Option B: the portal sends the id token beside the access token

- **What was checked:** the id token's claims, listed above. It carries `amr`,
  `at_hash`, `aud`, `auth_time`, `azp`, `client_id`, `exp`, `iat`, `iss`, `sid`
  and `sub`, and no address.
- **Fit:** nothing on the request path, if the claims were there.
- **Cost:** they are not there. Zitadel puts user claims into an id token only
  when the application is configured to assert them, and the application
  configuration this repository writes carries no such field: the OIDC config
  read back on 2026-08-31 held `accessTokenType`, `allowedOrigins`,
  `applicationType`, `authMethodType`, `clientId`, `clockSkew`, `grantTypes`,
  `postLogoutRedirectUris`, `redirectUris` and `responseTypes`, and nothing
  named `idTokenUserinfoAssertion`. Beyond that, an id token is a statement to
  the client about the sign in and was never meant to be presented to an API,
  and taking two tokens where the contract's `memberToken` scheme describes one
  is a change to the contract for every operation rather than for this one.

### Option C: leave it, and let an admin record confirmations

- **What was checked:** the trigger. An admin may write `email_verified_at` on
  any row, and after the change made on 2026-08-31 an admin who moves an
  address loses its date unless they set both in one statement.
- **Fit:** no new call anywhere, and the admin portal is being built in phase 4
  regardless.
- **Cost:** it is a person doing by hand what the identity service already knows,
  for every member, forever. The lab has two or three admins and roughly the
  membership of a small workshop, so this is a standing chore rather than a
  one off, and the column would go on reading false for anybody nobody got to.

## Decision

Proposed: **Option A**, with the outbound call held to `POST /me` and to no
other operation, and with the write going through a system path in
`db/migrations/` rather than through the member's own UPDATE.

The reasoning, in the order that drove it. Option B is not available, measured.
Option C works and costs a person's attention every week for a value a machine
already holds. That leaves A, and A's real cost is the offline property, which
is worth spending on exactly one request: a first sign in happens once per
member, it already writes to the database, and a member who hits it while the
identity provider is down has just signed in through that provider, so the
provider being down means they never reached this call.

Not accepted, and not built. Nobody is named to accept it, and the schema half
touches `db/migrations/008_system_paths.sql`, which is where the only write in
this system that happens without an admin already lives. That file is worth its
own review rather than a change made on the way past.

## The condition that would flip this

If `POST /me` ever answers anything a member retries, or if the members API
grows a second reason to call the identity provider on a request path, then the
offline property is already gone and the argument for holding this to one
operation goes with it, and the right shape becomes a cached read of userinfo on
the clock the key set already uses.

## Consequences

- What gets easier: `email_verified_at` stops being a column nothing writes, and
  the chip in the portal can say something true. The claim branch of
  `link_or_create_member`, which needs a proved address and has never been able
  to fire, becomes reachable, which is the path a paying member who never signed
  up was meant to arrive by.
- What gets harder: `services/api/app/identity.py` stops being able to say it
  asks the provider nothing on the request path, and its opening paragraph has
  to be rewritten rather than quietly left standing. One more URL to configure,
  one more Caddy route, and one more failure mode to write an error message for.
- What we now have to operate: nothing new. The route is through the Caddy site
  that already exists for the key set, on the same name, and it exposes a
  member's own claims to a caller already holding that member's token.
- The exit: delete the call and the route, and `email_verified_at` goes back to
  being written by nothing. About an hour, and no data has to move, because a
  date that was recorded stays true.

## What was borrowed

Nothing. `/oidc/v1/userinfo` is the endpoint OpenID Connect Core section 5.3
specifies, and Zitadel's is that endpoint.

## Open questions

- **What happens when userinfo says the address is not confirmed, or does not
  answer.** The record still gets written and the date stays null, which is the
  behaviour today. Whether the member is told anything is a portal question and
  nobody has asked it.
- **Whether the address userinfo returns should also be the one written.**
  Today `POST /me` takes an address in the body and `link_or_create_member` is
  passed NULL, deliberately, because no address in the request is proved. An
  address userinfo returns is proved, and using it would let the claim branch
  fire. That is a larger change than recording a date and it belongs in its own
  decision. Resolved by whoever writes that one.
- **The timeout.** `KEY_SET_READ_TIMEOUT_SECONDS` is three seconds for a read
  that no request waits on. A read a request does wait on wants a number chosen
  against how long a member will sit on a sign up screen, and nobody has
  measured that.
