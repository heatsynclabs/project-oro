# The members API against the identity service

## What it is

The suite that puts the two halves of a sign in together for the first time. A
member signs in on the hosted screens Zitadel serves, and the access token that
comes back is handed to the members API, which verifies it against the key set
that identity service publishes and answers with that member's own record.

Until this ran, `services/api/` had only ever verified tokens this repository
minted with a key of its own. That answers a narrower question than anybody
wanted, which is whether the service can check its own signature.

Nothing here is wired into `compose.yaml` or Caddy. `make up` and
`make development` are unchanged, the members portal still reads the contract
mock, and the members API is still started by hand or by a suite.

## How to run it

```sh
make api-identity-test
```

or `tools/api-against-identity/run.sh`, which is the same thing. It needs docker, openssl
and curl on the machine running it. It installs nothing.

It brings up its own compose project on its own ports, applies `db/migrations`
and `db/seed` to it, registers the clients with `tools/identity/configure.py`,
creates two invented people, builds the members API image, and takes all of it
down again. A stack you already have up is neither read nor touched.

Five things it starts, each needing the one before it:

| What | Why |
|---|---|
| Postgres | The real schema, the real policies, and `oro_api_login` |
| The identity service | The same image and settings a deployment gets |
| The clients | `configure.py`, unchanged, so this registers what a deployment registers |
| Two identity accounts | One with a members row, one without |
| The members API image | Built from `services/api/Dockerfile` |

### Why everything runs inside the compose network

The identity service works out which instance a request is for by reading the
Host header, so the name it was configured with is the only name that reaches
it. On this run that name is `identity`, which is the name it has on the compose
network, and a laptop cannot resolve it. So the checks run in a container on
that network rather than on the laptop, and `identity-on-the-network.yaml`
supplies the one setting `compose.development.yaml` cannot: the port on the
network is 8080 and the port on a laptop is not.

The compose file still publishes the laptop port, and a request to it is refused
with `Instance not found. Make sure you got the domain right`. That is expected
here and it is a trap worth knowing elsewhere, which `HANDOFF.md` section 7
carries.

## What it found

**A real access token from this instance does not carry `oro-members-api`.** It
carries a list: the client id of every application registered under the project,
and the project's own identifier, which is `oro-project` because
`tools/identity/configure.py` chose it. Measured on 2026-08-30 by signing in
through the real screens and reading the claims off the token.

`services/api/README.md` documented `oro-members-api` as the value for
`ORO_API_TOKEN_AUDIENCE`, and nothing issues that. With it set, the service
refused every real token with `token refused: Audience doesn't match` in its
log and 401 to the member. The README is corrected and this suite holds the
value: one check asserts that what the api container is configured with and what
`configure.py` registers are still the same string, so moving one and not the
other goes red here.

The client ids are the other half of that list and none of them is usable as a
setting. Zitadel generates them, so they differ per instance, and a deployment
would have to be configured after the fact from what the service happened to
issue.

Nothing in `services/api/app/` needed changing. PyJWT compares the configured
audience against every entry when the claim is a list, which is what RFC 7519
asks for and what this suite watched it do.

## What is here

| File | What it is |
|---|---|
| `run.sh` | The stack, the fixtures, then the two container passes over them |
| `identity-on-the-network.yaml` | One compose setting, so the issuer names the network |
| `make_the_fixtures.py` | Two identity accounts, and a second project to borrow a wrong audience from |
| `check_a_real_token.py` | The eight checks |

The eight, in the order they read: a member reading their own record, a guard
that the token came from the provider and not from this suite, the audience
being the one a real token carries, the same token reading the directory, and
then the four refusals. A token from another project on the same instance, a
token naming a key id nobody published, a stranger's signature wearing the
provider's own key id, and a real token belonging to somebody the members
database has never met.

The last of those is the sentence `services/api/app/problems.py` already
carried for a sign in nothing has linked to a member record, and this is the
first thing to reach it with a token the provider issued.

## What it depends on

| Thing | Why |
|---|---|
| `compose.yaml`, `compose.development.yaml` | The database and the identity service. This suite starts its own project from them |
| `tools/identity/configure.py` | The project and the clients. Called rather than copied, so what is registered here is what `make identity-configure` registers |
| `tools/identity/flow.py` | One whole sign in through the hosted screens, with no browser |
| `tools/identity/api.py`, `registrations.py` | Calling the identity service, and reading back what it holds |
| `services/api/tests/harness.py` | The HTTP client and the runner that prints the result, plus the minter both forgeries are signed with |
| `db/migrations/008_system_paths.sql` | `link_or_create_member`, which is how the members row gets the subject the identity account will arrive with |
| Docker | The database. The identity service. The api image, and the container the checks run in |
| openssl and curl | Two commands on the machine running this. Nothing is installed |

Both key settings the harness reads name the same stranger's key, because
nothing this suite signs is meant to be accepted. Every token that has to work
comes from the identity service.
