# Members API

## What it is

The service the three portals will call. Today it answers three of the twenty
three operations in `docs/api/members-v1.yaml`:

| Operation | Path | What it proves |
|---|---|---|
| `getMe` | `GET /me` | A member reads their own record, with their tier and their live roles |
| `listDirectory` | `GET /members` | The directory, with an email or a phone number hidden unless its owner published it |
| `getDirectoryMember` | `GET /members/{id}` | The same object and the same visibility rules, for one member |

That is the whole of it. There is no write path and no admin path. Nothing here touches a card, an
approval or the door. This is a vertical slice built to prove one thing end to
end: an HTTP request carrying an access token turns into a database transaction
that runs under the member's own row level security policies, and the policies
are what decide the answer.

**This is ahead of the order.** `docs/plan/order-of-operations.md` forbids
starting a phase whose predecessor's exit criterion is unmet, and phase 1 has
not exited: the contract still needs a review by a person.
`docs/api/contract-review-notes.md` is a defect list handed to whoever does that
review, and it is not the review. `HANDOFF.md` section 6 nevertheless lists
`services/api` under what is buildable now, and the members portal was already
built out of order on purpose as the contract proof, so this is deliberate and
it is stated here rather than discovered later. The contract underneath these
three operations may still move.

### How a request works

```
Authorization: Bearer ...
  |  app/identity.py    verifies the signature offline against the provider's
  |                     JWKS, and answers with the sub claim or with nothing
  v
app/database.py         one transaction, and two settings on it:
  |                       SET LOCAL ROLE oro_api
  |                       set_config('oro.identity_subject', sub, true)
  v
Postgres                the policies in db/migrations/004_security.sql and
                        011_close_read_holes.sql decide what comes back
```

Five things about that are worth knowing before changing any of it.

**Nothing in this service decides who may see what.** There is no check that
turns an anonymous caller away. A caller with no usable token reaches the
database with no identity set, `current_member_id()` raises, and the service
turns that into the contract's 401. Move that decision up here and there are
two authorities for one rule, which rule 5 forbids.

**`SET LOCAL`, never `SET`.** A plain `SET` outlives the transaction, and the
connection then goes back to a pool and is handed to the next request carrying
the last member's identity. `db/migrations/004_security.sql` spends four lines
of hint text on this. Exactly one function names that setting, and
`tests/check_identity_isolation.py` runs three requests down one connection to
prove it.

**The provider's signing keys are read on a clock, never on demand.** A token
naming a key id nobody published is refused from what is already in memory, at
no network cost, because a caller who has to sign nothing can otherwise pick the
moment this service makes an outbound request. The other side of that is a key
the provider withdraws, which keeps working here until the next read.
`ORO_API_JWKS_MAX_AGE_SECONDS` is that window and it is one minute by default.
`app/identity.py` carries both measurements and `tests/check_signing_keys.py`
holds the behaviour.

**Every refusal is a problem detail.** Including the two FastAPI would answer
itself, a path nothing serves and a method a path does not take. Both arrive as
`{"detail": ...}` in `application/json` unless something catches them, and the
contract opens by saying errors are RFC 9457 in one shape everywhere.
`refused_by_the_router` in `app/main.py` is where the second shape stops.

**The service logs in as `oro_api_login` and becomes `oro_api`.**
`db/migrations/004_security.sql` creates `oro_api` `NOLOGIN` on purpose, so
something else has to hold the password. `oro_api_login.sql` beside this file
creates that role `NOINHERIT`, which means it holds nothing at all until the
transaction runs `SET LOCAL ROLE oro_api`. That file's header says why
inheriting would have been a defect. There is no bypass in the connection. `oro_api` is not a superuser and owns no
table, and `BYPASSRLS` belongs to `door_reader`, which is a different role
holding one function.

### What is deliberately missing

- **The generated OpenAPI document and the pages FastAPI serves for it.**
  `docs/api/members-v1.yaml` is the contract. A second document describing three
  operations would disagree with it about the other twenty. Rule 10 wants the
  document verified against the running service, and that check belongs with the
  change that completes the set.
- **A health endpoint.** The contract declares none, and rule 10 says not to
  document what does not exist. The suite waits for the service by making a real
  request, which is a better check anyway: a call with no token can only come
  back 401 after the service has reached the database and been refused by it.
- **First sign in.** `link_or_create_member` exists in
  `db/migrations/008_system_paths.sql` and no operation in the contract calls
  it, so a verified token whose subject matches no member row has nowhere to go.
  This answers 401 with a problem detail that says exactly that.
  `docs/api/contract-review-notes.md` finding 5 is the same gap seen from the
  contract's side.

## How to run it

It is not in `compose.yaml` or `compose.development.yaml`, and `make up` and
`make development` behave exactly as they did before it existed. The portal
still reads the contract mock. Wiring the stack over to this service is the next
change, and it has its own review.

To run it by hand against a database you already have, build the image and give
it five environment variables:

```
docker build -t oro-api services/api
docker run --rm -p 127.0.0.1:8711:8000 \
  -e ORO_API_DATABASE_URL=postgresql://oro_api_login:PASSWORD@HOST:5432/oro \
  -e ORO_API_JWKS_URL=https://id.example.org/oauth/v2/keys \
  -e ORO_API_TOKEN_ISSUER=https://id.example.org \
  -e ORO_API_TOKEN_AUDIENCE=oro-project \
  oro-api
```

| Variable | What it is |
|---|---|
| `ORO_API_DATABASE_URL` | libpq URL for the `oro` database, as `oro_api_login` |
| `ORO_API_JWKS_URL` | where the identity provider publishes its signing keys |
| `ORO_API_TOKEN_ISSUER` | the `iss` claim every token has to carry |
| `ORO_API_TOKEN_AUDIENCE` | the `aud` claim every token has to carry. Against the identity service in `compose.yaml` that is `oro-project`, and the paragraph below says how that was established |
| `ORO_API_DB_POOL_MAX` | connections in the pool. Ten by default, and the suite runs it at one |
| `ORO_API_JWKS_MAX_AGE_SECONDS` | how long the provider's signing keys are used before they are read again. Sixty by default, and the suite runs it at five |

The first four are required and the service refuses to start without them,
naming the one that is missing.

**The audience was measured rather than chosen, and this file had it wrong.** It
said `oro-members-api` until 2026-08-30, and nothing issues that. A real access
token from the identity service in `compose.yaml` carries a list: the client id
of every application registered under the project, and the project's own
identifier, which `tools/identity/configure.py` sets to `oro-project`. The
client ids are generated per instance, so the project identifier is the only
entry a container can be configured with ahead of time. With the old value set,
the service refused every real token, logged `token refused: Audience doesn't
match`, and answered the member 401.

Nothing in `app/` changed to fix it. PyJWT compares the configured audience
against every entry when the claim is a list, and `tools/api-against-identity/`
watched it do that. That suite is also where the two values are held together:
one check fails if the audience an api container is given and the project
`configure.py` registers stop being the same string.

`oro_api_login` does not exist until somebody creates it. Run
`oro_api_login.sql` against the database as the superuser, with
`ORO_API_DB_PASSWORD` in the environment. That file's header says where it
belongs, which is `db/init/`, and why it is here instead.

## How to test it

```
make api-test
```

or `services/api/tests/run.sh`, which is the same thing. It needs docker,
python3, openssl and curl. Nothing gets installed on your machine.

What it builds before it asks a single question: a Postgres carrying every
migration and seed applied from nothing, the login role, three invented people,
a signing key of its own, a JWKS server serving the public half of it, and this
image. Then it makes real HTTP requests against the result. Everything it starts
is named after its own process id and is removed when it exits, so a stack you
have up is neither read nor touched.

Thirty five checks. One is in `run.sh` itself, a refusal: a container with no
settings has to stop and name the one that is missing. The other thirty four are
in three files. `check_members_api.py` is what the three operations return and
what they withhold. `check_identity_isolation.py` is who the service thinks you
are and how long that lasts, and the last check in it is the reason this suite
exists. `check_signing_keys.py` is when the provider's keys are read, which is
one clock answering two failures that pull in opposite directions.

That suite mints its own tokens, so what it cannot see is what the identity
provider actually issues. `tools/api-against-identity/` is the suite that does:
it signs a member in on the hosted screens and hands the token that comes back
to this service. Run it with `make api-identity-test`.

Four ways to make it go red, each of which was run:

| Break | What goes red |
|---|---|
| Never set `oro.identity_subject` | Everything, and the log reads `refused by the database: No identity set on this transaction` |
| `set_config(..., false)`, which is a plain `SET` | The anonymous request in the middle of `test_an_identity_does_not_survive_on_a_pooled_connection` comes back 200 carrying the previous caller's record |
| Drop `SET LOCAL ROLE oro_api` | `permission denied for table members`, because the login role inherits nothing |
| Read the directory from `members` instead of `member_directory` | The directory returns one row, the caller's own, because no policy lets one member read another's row |
| Turn PyJWKClient's per key cache back on | A key withdrawn from the published JWKS keeps verifying tokens, and `test_a_key_withdrawn_from_the_jwks_stops_being_accepted` goes red |
| Let an unknown key id trigger a read of the JWKS | Twenty tokens naming keys nobody published cost twenty outbound requests, and a member's own call times out while they arrive |

## What it depends on

- **Postgres**, with `db/migrations` applied. The service holds no schema of its
  own and runs no migration. A request waits two seconds for a free connection
  and is then answered 500, and every connection carries a five second ceiling
  on a statement and a ten second ceiling on an idle transaction.
  `app/database.py` says where each number comes from.
- **An OIDC provider** publishing a JWKS. The identity service in `compose.yaml`
  is that provider, and `tools/api-against-identity/` is what has been run
  against it: a member signs in on the hosted screens and the token that comes
  back reads their own record here. The suite in `tests/` still serves its own
  JWKS from its own key, and that is what lets it withdraw a key and watch one
  stop being accepted, which nothing can ask a real provider to do on cue.
- **Four Python packages**, which bring seventeen more with them. They are
  chosen and priced in
  [ADR 0012](../../docs/decisions/0012-python-dependencies.md), and every one is
  listed with its licence in `ATTRIBUTIONS.md`. `requirements.in` says what was
  asked for and `requirements.txt` is the lock, with a hash for every wheel on
  every platform.

It depends on nothing in `apps/` or `packages/`, and it never speaks the door
wire protocol. Rule 5.
