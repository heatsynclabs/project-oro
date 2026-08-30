# ADR 0013: when the members API re-reads the identity provider's signing keys

- **Status:** proposed
- **Date:** 2026-08-29
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in it yet, and this record is not complete until a build lead signs it.

## Context

`services/api/app/identity.py` verifies an access token offline against the key
set the identity provider publishes, so the provider is never on the request
path. That leaves one question, and its two answers pull against each other.
Read the key set whenever a token names a key id nobody published, and a caller
who has signed nothing gets to choose when this service makes an outbound HTTP
request. Read it rarely, and a key withdrawn because it leaked keeps verifying
tokens.

The reasoning is already in that module's docstring and in
`services/api/tests/check_signing_keys.py`. `HANDOFF.md` section 6 item 16 asks
for it as a decision record as well, which is what this is.

## Options considered

The PyJWKClient behaviour below was read on 2026-08-29 out of
`jwt/jwks_client.py` in the PyJWT 2.13.0 wheel, which is the version pinned in
`services/api/requirements.txt`. MIT, and listed in `ATTRIBUTIONS.md`.

### Option A: a clock, and no read a caller can ask for

- **What it is:** `read_key_set()` replaces every key held in memory, and
  `_signing_key()` calls it only when the last read is older than
  `ORO_API_JWKS_MAX_AGE_SECONDS`. Both PyJWKClient caches are turned off in the
  constructor. The read happens under a lock that nobody waits on, so a slow
  provider costs one thread rather than every thread that arrives.
- **Fit:** a token naming an unpublished key id is refused from the set already
  in memory, and what it can cost in outbound requests comes off the clock
  rather than off the caller's request rate. Twenty of them in a row are
  allowed at most two reads of the key set by
  `services/api/tests/check_signing_keys.py`, at the few second window the
  suite runs on, and the comment on that bound says why it is not zero. A
  withdrawn key stops verifying within one window with nobody restarting
  anything. Three checks hold all of this and they run in CI.
- **Cost:** the same window is what a rotation costs. A token signed with a key
  the provider published after the last read is refused until the next read.

### Option B: PyJWKClient's own caching, left as it comes

- **What it is:** `cache_jwk_set` at its default of `True` with the default
  `lifespan` of 300 seconds, and optionally `cache_keys=True`.
- **Fit:** no code here at all.
- **Cost:** `get_signing_key` calls `get_signing_keys(refresh=True)` whenever
  the key id is not in the set it holds, which bypasses that cache, so the set
  cache does not cover the case this decision is about. That is the outbound
  request an unauthenticated caller can ask for once per request. Measured
  before the fix and recorded in `services/api/app/identity.py`: with the key
  set server paused, forty five such requests took a member's own call from
  0.06 seconds to a timeout, out of a threadpool holding forty. The per key
  cache is an `lru_cache` with no expiry at all, and
  `services/api/tests/check_signing_keys.py` records a key removed from the
  published set still verifying freshly minted tokens six minutes later, with
  one read of the key set in the whole life of the container.

### Option C: re-read when a key id is unknown, at most once per window

- **What it is:** the same clock used as a rate limit on a trigger rather than
  as the whole policy. A planned rotation is then picked up on the first token
  carrying the new key id instead of on the next tick, which buys back most of
  option A's rotation cost.
- **Cost:** the caller still chooses when the read happens, and the read is on
  their request, so a member arriving behind an unknown key id waits up to
  `KEY_SET_READ_TIMEOUT_SECONDS`, which is 3. It gives back the property that
  made option A worth having, in exchange for a cost that only shows up on
  rotation days.

### Option D: read once at start, restart the container to rotate

- **What it is:** `open_verifier()` reads the set and nothing reads it again.
- **Fit:** the least machinery, and no clock for a volunteer to reason about at
  2am.
- **Cost:** a leaked key stays trusted until a person notices and restarts, and
  rotating a key at the provider turns into an outage of sign in here until
  they do. That is the failure the first check in
  `services/api/tests/check_signing_keys.py` was written against.

## Decision

**Option A, which is what the code does.**

An unknown key id is refused from the set already in memory, and what it can
cost in outbound requests is capped by the clock rather than chosen by the
caller. That is the property being bought, because whoever sends one has signed
nothing and can send as many as they like. It eliminates B and C, both of which
hand that caller a read of the key set on their own request. D fails on the
other side: a key the provider withdraws has to stop working here without
waiting for a person.

The window's default of sixty seconds has no requirement behind it, and this is
the part worth writing down. Nothing in the plan says how quickly a withdrawn
key must stop being accepted, and nothing here has been run against the identity
service's key set at all. `services/api/README.md` records the suite serving its
own key set from its own key. Sixty seconds is short enough that a withdrawn key
is a minute of exposure rather than an afternoon of it, and long enough not to
be a poll every few seconds. It is a setting rather than a constant so that the
number can move once somebody has measured the provider.

## The condition that would flip this

Somebody establishes how Zitadel publishes a rotated signing key. If the new
public key appears in the key set before it is used to sign anything, option A
costs a rotation nothing, the window can be far longer than a minute, and the
argument for option C disappears. If it signs with a key it has not yet
published, no window helps and this record has to be reopened.

## Consequences

- Two numbers to operate. `ORO_API_JWKS_MAX_AGE_SECONDS` in the environment,
  sixty by default and five in the suite, and `KEY_SET_READ_TIMEOUT_SECONDS` in
  the source, three.
- Nothing polls. `read_key_set()` has two callers in
  `services/api/app/identity.py`: `open_verifier()` at start, and
  `_signing_key()`, which a request reaches only by carrying a bearer token and
  only when the last read is older than the window. Measured on 2026-08-29 with
  the module loaded against a key set server that logs every request and the
  window set to two seconds: one read at start, then nothing across the next
  twelve seconds while no request arrived. The first request carrying a token
  after that cost one read, and nine more behind it inside the same window cost
  none. A container nobody calls reads the key set once in its life.
- A provider that cannot be reached is a warning in the log and the keys already
  held stay in use. `read_key_set` stamps the clock before the read rather than
  after it, so an outage costs one attempt per window rather than one per
  request.
- Reversing this is cheap: the two cache arguments on the PyJWKClient
  constructor, and one function deleted. Three checks go red, which is what they
  are for.

## What was borrowed

Nothing copied. PyJWT 2.13.0, MIT, used as a dependency with both of its caches
switched off, and the constructor call in `services/api/app/identity.py` says
why each one is off.

## Open questions

```
ASSUMPTION: the identity service publishes a rotated signing key before it
starts signing tokens with it, so one stale minute costs a member one refused
sign in rather than an outage.
CONFIRM BY: rotate a key on a throwaway Zitadel from compose.yaml and watch
whether the new key id reaches ORO_API_JWKS_URL before a token carrying it
reaches the API.
BLAST RADIUS: the default of ORO_API_JWKS_MAX_AGE_SECONDS, and whether option C
is needed after all.
```

- How long a withdrawn key may keep working here. Nobody has said, so sixty
  seconds is measured against nothing. Whoever answers it changes one setting.
