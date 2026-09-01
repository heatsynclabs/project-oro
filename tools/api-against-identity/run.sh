#!/bin/sh
# The members API, asked to accept a token the real identity service issued.
#
#   tools/api-against-identity/run.sh
#
# Needs docker, openssl and curl. Runs as its own compose project on its own ports and
# supplies its own values for everything compose reads, so a stack somebody is
# already running is neither read nor touched, and no .env has to exist. Leaves
# nothing behind. Exit code is 1 if any check failed.
#
# What it builds, in this order because each part needs the one before it:
#
#   postgres        db/migrations, db/seed, and the login role the API connects
#                   as, which is services/api/oro_api_login.sql
#   the identity    the same image and the same settings compose.yaml gives a
#     service       deployment, on this run's own network
#   the clients     tools/identity/configure.py, unchanged, so what is
#                   registered here is what a deployment registers
#   two people      an identity account each, and a members row for one of them
#   the api image   built from services/api/Dockerfile
#
# Everything except the image build happens inside the compose network. The
# identity service resolves which instance a request is for from the Host
# header, so the name it was configured with is the only name that reaches it,
# and on this network that name is `identity`.
# tools/api-against-identity/identity-on-the-network.yaml is the one line that
# takes.
#
# The checks run in a container on that network too, rather than on the laptop,
# for the same reason: the laptop cannot resolve `identity` and a request under
# any other name is refused before the instance is found.

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/tools/api-against-identity"

PROJECT="oro-api-identity-test-$$"
# Compose names the default network after the project. Everything this run
# starts by hand joins it by that name.
NETWORK="${PROJECT}_default"
SERVICE="$PROJECT-api"
IMAGE="$PROJECT:local"

# The name the identity service answers to, and the port it answers on inside
# the network. Together they are the issuer it signs into every token.
export ORO_HOSTNAME=identity
ISSUER="http://identity:8080"

# The audience the api container is told to demand. Measured rather than
# chosen. An access token this instance issues carries a list: the client id of
# every application in the project, and the project's own identifier. The
# client ids are generated per instance and cannot be written down ahead of
# time. The project identifier can, because tools/identity/configure.py chooses
# it, so PROJECT_ID is the value and a check holds these two to the same string.
#
# services/api/README.md documented oro-members-api here until this suite ran.
# Nothing issues that: the service refused every real token with "Audience
# doesn't match", measured on 2026-08-30.
AUDIENCE="oro-project"

export ORO_TLS=internal
export ORO_HTTP_PORT=8097
export ORO_HTTPS_PORT=8497
# Published and unused. The suite reaches the identity service on the network,
# and a request to this port carries a Host header the instance does not know.
export ORO_IDENTITY_PORT=8197
# Nothing here starts the mock, and compose still reads the variable.
export ORO_MOCK_PORT=4097
export ORO_MAIL_PORT=8029
# Invented, used by nothing outside this run, and removed with the volumes when
# it exits. Rule 13: nothing here resembles a credential anybody holds.
export ORO_DB_PASSWORD="throwaway-$$"
export ORO_IDENTITY_DB_PASSWORD="throwaway-identity-$$"
API_DB_PASSWORD="throwaway-api-$$"
# The same value under the name compose.api.yaml reads, because compose.yaml
# includes that file and interpolates it whatever this run starts.
export ORO_API_DB_PASSWORD="$API_DB_PASSWORD"
# Exactly 32 bytes, which is what the service requires and all it requires.
export ORO_IDENTITY_MASTERKEY="throwaway-master-key-0123456789a"
export ORO_IDENTITY_ADMIN_USERNAME="fixture-admin"
export ORO_IDENTITY_ADMIN_PASSWORD="Fixture-Handover-1!"

# Published on the loopback, well away from 8080, 8180 and the port
# services/api/tests/run.sh takes, so the two can run side by side. The checks
# do not use it. It is here so that a person can curl the service while the
# suite is stopped at a failure.
PORT="${ORO_API_IDENTITY_TEST_PORT:-8712}"

# A key id nothing published, for the token that has to be refused on its key
# id alone.
STRANGER_KID="a-key-this-instance-never-published"

WORK="$(mktemp -d)"
MEMBER_ID=""

compose() { docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" \
                           -f "$ROOT/compose.development.yaml" \
                           -f "$HERE/identity-on-the-network.yaml" "$@"; }

cleanup() {
  docker rm -f "$SERVICE" >/dev/null 2>&1 || true
  docker image rm -f "$IMAGE" >/dev/null 2>&1 || true
  compose down --volumes >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

psql_in() { compose exec -T db psql -U postgres -d oro -v ON_ERROR_STOP=1 -q; }

# python3 and openssl, in the image services/api/tests/run.sh already uses for
# its JWKS server. The repository is mounted read only and the container runs
# as root, so the mode on a temporary directory is not in the way. That
# difference between Docker on a Mac and Docker on Linux cost a red build once
# and HANDOFF.md section 7 carries it.
in_the_network() {
  docker run --rm --network "$NETWORK" \
    -v "$ROOT:/repo:ro" -v "$WORK:/work:ro" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e ORO_IDENTITY_URL="$ISSUER" \
    -e ORO_IDENTITY_TOKEN="$IDENTITY_TOKEN" \
    -e ORO_API_TEST_URL="http://$SERVICE:8000" \
    -e ORO_API_TEST_ISSUER="$ISSUER" \
    -e ORO_API_TEST_AUDIENCE="$AUDIENCE" \
    -e ORO_API_TEST_KEY=/work/stranger.pem \
    -e ORO_API_TEST_STRANGER_KEY=/work/stranger.pem \
    -e ORO_API_TEST_KID="$STRANGER_KID" \
    -e ORO_MEMBER_ID="$MEMBER_ID" \
    python:3.13-slim python3 "$@"
}

echo "Bringing up the database and the identity service"
compose up --detach --wait --wait-timeout 300 db identity >/dev/null || {
  echo "The stack did not come up, so nothing was checked." >&2
  compose logs identity 2>&1 | tail -30 >&2
  exit 1
}

for f in "$ROOT"/db/migrations/*.sql "$ROOT"/db/seed/*.sql; do
  psql_in < "$f" >/dev/null || {
    echo "$(basename "$f") did not apply, so nothing was checked." >&2
    exit 1
  }
done
compose exec -T -e ORO_API_DB_PASSWORD="$API_DB_PASSWORD" db \
  psql -U postgres -d oro -v ON_ERROR_STOP=1 -q < "$ROOT/services/api/oro_api_login.sql"
echo "the schema, the seed data and the login role are applied"

# docker cp writes a tar stream, so it stays in a pipe. Holding it in a shell
# variable first truncates it at the first NUL byte, which reads as a healthy
# service with no token at all.
IDENTITY_TOKEN=$(compose cp identity:/bootstrap/pat - 2>/dev/null | tar -xO || true)
if [ -z "$IDENTITY_TOKEN" ]; then
  echo "No bootstrap token, so nothing was checked. The identity service said:" >&2
  compose logs identity 2>&1 | tail -20 >&2
  exit 1
fi

echo
echo "Registering the project, the clients and the branding"
# --no-portal-config for the reason the other throwaway suites pass it: the
# repository is mounted here, this stack dies with the run, and the file that
# step writes is read by a portal somebody may have open on this machine.
in_the_network /repo/tools/identity/configure.py \
  --members-origin "http://portal.invalid:9999" \
  --admin-origin "http://admin.invalid:9999" \
  --door-origin "http://door.invalid:9999" --no-portal-config || {
  echo "The configuration step failed, so nothing was checked." >&2
  exit 1
}

echo
PERSON=$(in_the_network /repo/tools/api-against-identity/make_the_fixtures.py) || {
  echo "The identity accounts could not be created, so nothing was checked." >&2
  exit 1
}
SUBJECT=$(printf '%s' "$PERSON" | cut -f1)
EMAIL=$(printf '%s' "$PERSON" | cut -f2)
NAME=$(printf '%s' "$PERSON" | cut -f3)

# The database side of the pairing tools/bootstrap/ makes. The identity account
# exists first, because this takes the subject that account will arrive with.
MEMBER_ID=$(printf "SELECT link_or_create_member('%s', '%s', '%s');\n" \
              "$SUBJECT" "$EMAIL" "$NAME" \
            | compose exec -T db psql -U postgres -d oro -tAq -v ON_ERROR_STOP=1)
if [ -z "$MEMBER_ID" ]; then
  echo "No members row was written for $EMAIL, so nothing was checked." >&2
  exit 1
fi
echo "$NAME is $MEMBER_ID in the members database and $SUBJECT on the identity service"

openssl genrsa -out "$WORK/stranger.pem" 2048 2>/dev/null

echo
echo "building the api image"
docker build --quiet --tag "$IMAGE" "$ROOT/services/api" >/dev/null

docker run -d --rm --name "$SERVICE" --network "$NETWORK" \
  -p "127.0.0.1:$PORT:8000" \
  -e ORO_API_DATABASE_URL="postgresql://oro_api_login:$API_DB_PASSWORD@db:5432/oro" \
  -e ORO_API_JWKS_URL="$ISSUER/oauth/v2/keys" \
  -e ORO_API_TOKEN_ISSUER="$ISSUER" \
  -e ORO_API_TOKEN_AUDIENCE="$AUDIENCE" \
  -e ORO_API_DB_POOL_MAX=2 \
  "$IMAGE" >/dev/null

# The service serves no health endpoint, because the contract declares none.
# Readiness is a real request: a call with no token can only come back 401
# after the service has reached the database and been refused by it.
printf 'waiting for the members api'
i=0
until [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/members")" = "401" ]; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo " timed out"; docker logs "$SERVICE" 2>&1 | tail -30; exit 1
  fi
  printf '.'; sleep 1
done
echo " ready"

echo
in_the_network /repo/tools/api-against-identity/check_a_real_token.py || {
  echo
  echo "The last forty lines the members API printed:" >&2
  docker logs "$SERVICE" 2>&1 | tail -40 >&2
  exit 1
}
