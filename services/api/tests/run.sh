#!/bin/sh
# The members API, against a real Postgres carrying the real migrations.
#
#   services/api/tests/run.sh
#
# Needs docker, python3, openssl and curl. Everything it starts is named after
# this process, runs on its own network, publishes one port on the loopback
# only, and is removed when the script exits, so a stack somebody already has
# up is neither read nor touched.
#
# What it builds, in this order because each part needs the one before it:
#
#   postgres        db/migrations, db/seed, the login role, and three invented
#                   people, logging every statement so a check can count them
#   a signing key   two, in fact. The second one is a stranger's, and a token
#                   signed with it has to be refused
#   a JWKS server   the public half of the first key, served over HTTP the way
#                   the identity provider will serve its own
#   the api image   built from services/api/Dockerfile
#
# The pool is held to one connection on purpose. Two requests have to land on
# the same connection for check_identity_isolation.py to mean anything: an
# identity that leaks is an identity that survived on a connection somebody
# else was handed.
#
# Every refusal here is checked by its own text as well as by its status. A
# service that fell over answers 500 to everything, which counts as a refusal
# from far enough away.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TESTS="$ROOT/services/api/tests"

# The lane letter and the process id, so two of these can run side by side and
# neither can collide with a stack started by make up.
RUN="oro-api-test-c-$$"
NETWORK="$RUN-net"
DATABASE="$RUN-db"
JWKS="$RUN-jwks"
SERVICE="$RUN-api"
IMAGE="$RUN:local"

# Well away from 8080, 8180, 80, 443 and 5432, and published on the loopback
# only, because nothing here should be reachable from the network the laptop is
# sitting on.
PORT="${ORO_API_TEST_PORT:-8711}"

# Invented, used by nothing outside this run, and gone when the container is.
# Rule 13: nothing here resembles a credential anybody holds.
DB_PASSWORD="throwaway-api-$$"

WORK="$(mktemp -d)"
FAILURES=0

cleanup() {
  docker rm -f "$SERVICE" "$JWKS" "$DATABASE" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  docker image rm -f "$IMAGE" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

psql_in() { docker exec -i "$DATABASE" psql -U postgres -d oro -v ON_ERROR_STOP=1 -q; }

docker network create "$NETWORK" >/dev/null

# log_statement=all so a check can count what the service actually sent. One
# of them proves that a request the service is about to refuse costs no query,
# and there is no other way to see a query that did not happen.
docker run -d --rm --name "$DATABASE" --network "$NETWORK" \
  -e POSTGRES_PASSWORD="$DB_PASSWORD" -e POSTGRES_DB=oro postgres:18 \
  -c log_statement=all >/dev/null

# pg_isready lies: the image runs a temporary server during initdb and restarts
# it, so readiness goes true before the real database exists. Wait for a real
# query against the real database, twice in a row. HANDOFF.md section 7.
printf 'waiting for postgres'
i=0
ok=0
while [ "$ok" -lt 2 ]; do
  if docker exec "$DATABASE" psql -U postgres -d oro -tAc 'SELECT 1' >/dev/null 2>&1
  then ok=$((ok + 1))
  else ok=0
  fi
  i=$((i + 1)); [ "$i" -gt 90 ] && { echo " timed out"; exit 1; }
  printf '.'; sleep 1
done
echo " ready"

for f in "$ROOT"/db/migrations/*.sql "$ROOT"/db/seed/*.sql; do psql_in < "$f"; done
docker exec -i -e ORO_API_DB_PASSWORD="$DB_PASSWORD" "$DATABASE" \
  psql -U postgres -d oro -v ON_ERROR_STOP=1 -q < "$ROOT/services/api/oro_api_login.sql"
psql_in < "$TESTS/fixtures.sql"
echo "schema, seed, the login role and the fixtures are loaded"

openssl genrsa -out "$WORK/signing.pem" 2048 2>/dev/null
openssl genrsa -out "$WORK/stranger.pem" 2048 2>/dev/null

export ORO_API_TEST_URL="http://127.0.0.1:$PORT"
export ORO_API_TEST_ISSUER="http://$JWKS:8000"
export ORO_API_TEST_AUDIENCE="oro-members-api"
export ORO_API_TEST_KEY="$WORK/signing.pem"
export ORO_API_TEST_STRANGER_KEY="$WORK/stranger.pem"
export ORO_API_TEST_KID="test-$$"
export ORO_API_TEST_CONTAINER="$SERVICE"
export ORO_API_TEST_DATABASE_CONTAINER="$DATABASE"
export ORO_API_TEST_JWKS_CONTAINER="$JWKS"
export ORO_API_TEST_JWKS_DIR="$WORK/jwks"

# The window app/identity.py reads the provider's key set on. Five seconds
# rather than the deployed minute, so check_signing_keys.py can withdraw a key
# and watch it stop working inside a check. Both directions of that window are
# checked, so the number being small does not hide anything.
export ORO_API_TEST_JWKS_MAX_AGE=5

mkdir "$WORK/jwks"
python3 -c "
import sys; sys.path.insert(0, '$TESTS')
import harness, pathlib
pathlib.Path('$WORK/jwks/jwks.json').write_text(
    harness.jwks_document('$WORK/signing.pem', harness.KEY_ID))
"

docker run -d --rm --name "$JWKS" --network "$NETWORK" \
  -v "$WORK/jwks:/srv:ro" -w /srv \
  python:3.13-slim python3 -m http.server 8000 >/dev/null
printf 'waiting for the jwks server'
i=0
until docker exec "$JWKS" python3 -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/jwks.json')" \
  >/dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -gt 30 ] && { echo " timed out"; exit 1; }
  printf '.'; sleep 1
done
echo " ready"

echo "building the api image"
docker build --quiet --tag "$IMAGE" "$ROOT/services/api" >/dev/null

# A refusal, checked by its text as well as by its exit code, before anything
# is configured correctly. A service that answered requests with half its
# settings missing would fail later and somewhere else.
echo
echo "== a missing setting stops the container"
if docker run --rm "$IMAGE" > "$WORK/no-settings.out" 2>&1; then
  echo "  FAIL  it started with no settings at all"
  FAILURES=$((FAILURES + 1))
elif grep -q "ORO_API_DATABASE_URL is not set" "$WORK/no-settings.out"; then
  echo "  ok    refused, naming ORO_API_DATABASE_URL"
else
  echo "  FAIL  it stopped without naming the setting that was missing"
  tail -5 "$WORK/no-settings.out" | sed 's/^/        /'
  FAILURES=$((FAILURES + 1))
fi

docker run -d --rm --name "$SERVICE" --network "$NETWORK" \
  -p "127.0.0.1:$PORT:8000" \
  -e ORO_API_DATABASE_URL="postgresql://oro_api_login:$DB_PASSWORD@$DATABASE:5432/oro" \
  -e ORO_API_JWKS_URL="http://$JWKS:8000/jwks.json" \
  -e ORO_API_TOKEN_ISSUER="$ORO_API_TEST_ISSUER" \
  -e ORO_API_TOKEN_AUDIENCE="$ORO_API_TEST_AUDIENCE" \
  -e ORO_API_DB_POOL_MAX=1 \
  -e ORO_API_JWKS_MAX_AGE_SECONDS="$ORO_API_TEST_JWKS_MAX_AGE" \
  "$IMAGE" >/dev/null

# The service serves no health endpoint, because the contract declares none and
# rule 10 forbids inventing one to document. Readiness is a real request: a call
# with no token has to come back 401, and it can only do that after the service
# has reached the database and been refused by it.
printf 'waiting for the members api'
i=0
until [ "$(curl -s -o /dev/null -w '%{http_code}' "$ORO_API_TEST_URL/members")" = "401" ]; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo " timed out"; docker logs "$SERVICE" 2>&1 | tail -30; exit 1
  fi
  printf '.'; sleep 1
done
echo " ready"

for check in "$TESTS"/check_*.py; do
  echo
  echo "== $(basename "$check")"
  python3 "$check" || FAILURES=$((FAILURES + 1))
done

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "every members API check passed"
else
  echo "$FAILURES check file(s) failed"
  docker logs "$SERVICE" 2>&1 | tail -40
fi
exit "$FAILURES"
