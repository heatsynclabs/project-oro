#!/bin/sh
# Prove what a laptop adds to the stack, and prove that not asking for it
# changes nothing.
#
#   tools/development/tests/run.sh
#
# The two shapes serve different schemes and that is what most of this checks.
# The deployment answers over TLS on the HTTPS port, with a certificate from
# Caddy's own authority. A laptop answers plain HTTP on the HTTP port, with no
# redirect anywhere, because a certificate no browser trusts costs a volunteer
# an administrator password before they can read a local page.
#
# Needs docker and curl. Runs as its own compose project on its own ports and
# supplies its own values for everything compose reads, so a stack somebody is
# already running is neither read nor touched, and no .env has to exist. Leaves
# nothing behind. Exit code is 1 if any check failed.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

PROJECT="oro-development-test-$$"
export ORO_HOSTNAME=localhost
export ORO_TLS=internal
export ORO_HTTP_PORT=8081
export ORO_HTTPS_PORT=8444
export ORO_IDENTITY_PORT=8185
# Its own, because the default is shared and a stack started by make development
# is already holding it. Every other port here is chosen for the same reason.
export ORO_MOCK_PORT=4011
# Invented, used by nothing, and removed with the volumes when this exits.
export ORO_DB_PASSWORD="throwaway-$$"
export ORO_IDENTITY_DB_PASSWORD="throwaway-identity-$$"
# Exactly 32 bytes, which is what the identity service requires of it.
export ORO_IDENTITY_MASTERKEY="throwaway-master-key-0123456789a"
export ORO_IDENTITY_ADMIN_USERNAME="fixture-admin"
export ORO_IDENTITY_ADMIN_PASSWORD="Fixture-Handover-1!"

# Named for the port each one is, not for the shape, because one check below
# calls the HTTPS origin while the development shape is the one that is up.
HTTPS_ORIGIN="https://$ORO_HOSTNAME:$ORO_HTTPS_PORT"
HTTP_ORIGIN="http://$ORO_HOSTNAME:$ORO_HTTP_PORT"
# What Caddy issues when ORO_TLS is "internal". Read from a running deployment
# with: curl -skv https://localhost:8444/health 2>&1 | grep issuer
INTERNAL_AUTHORITY="CN=Caddy Local Authority - ECC Intermediate"
passed=0
failed=0

# Two shapes: the deployment alone, and the deployment plus what a laptop adds.
compose()     { docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" "$@"; }
compose_dev() { compose -f "$ROOT/compose.development.yaml" "$@"; }

# Down through the override, so this reaches the mock as well.
cleanup() { compose_dev down --volumes >/dev/null 2>&1 || true; }
trap cleanup EXIT

check() {
  what="$1"
  expected="$2"
  actual="$3"
  if [ "$expected" = "$actual" ]; then
    passed=$((passed + 1))
    echo "ok    $what"
  else
    failed=$((failed + 1))
    echo "FAIL  $what"
    echo "        expected: $expected"
    echo "        actual:   $actual"
  fi
}

# The deployment answers from an authority the machine does not trust, so calls
# to it pass -k. Verifying that certificate is not what is being tested, and
# one check below reads the issuer directly instead. The flag does nothing on
# the development origin, which has no TLS to verify.
status_of() {
  curl -sk -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer development-test' "$1"
}

# Empty when the answer was not a redirect, which is the point of it here.
redirect_from() {
  curl -sk -o /dev/null -w '%{redirect_url}' "$1"
}

certificate_issuer() {
  curl -sk -o /dev/null -v "$1" 2>&1 | sed -n 's/^\* *issuer: //p' | head -1
}

reaches_tls() {
  if curl -sk -o /dev/null --max-time 5 "$1" 2>/dev/null; then
    echo yes
  else
    echo no
  fi
}

body_holds() {
  if curl -sk -H 'Authorization: Bearer development-test' "$1" | grep -q "$2"; then
    echo yes
  else
    echo no
  fi
}

running_services() { compose ps --services --status running | sort | xargs; }

# The identity service publishes its own discovery document, and it refuses any
# call whose Host header is not the domain it was configured with, so this is
# both a check that Caddy routes the name and a check that the service agrees
# it owns it.
identity_status() {
  curl -sk -o /dev/null -w '%{http_code}' \
    --resolve "id.$ORO_HOSTNAME:$1:127.0.0.1" \
    "https://id.$ORO_HOSTNAME:$1/.well-known/openid-configuration"
}

project_is_valid() {
  if compose_dev config >/dev/null 2>&1; then
    echo yes
  else
    echo no
  fi
}

# Both files, which is the form the logs target in the Makefile uses. Without
# the override compose resolves the service list from the deployment and the
# mock is not in it, so the one service a laptop adds is the one whose output
# the reader cannot see.
logs_reach_the_mock() {
  if compose_dev logs --tail 1 2>/dev/null | grep -q '^mock-1'; then
    echo yes
  else
    echo no
  fi
}

echo "Reading the project with nothing sourced and nothing exported"
check "development needs no environment prepared first" \
  "yes" "$(project_is_valid)"
echo

echo "Bringing up the deployment default on ports $ORO_HTTP_PORT and $ORO_HTTPS_PORT"
compose up --detach --wait --wait-timeout 300 >/dev/null
check "compose.yaml alone starts only the deployment" \
  "caddy db identity" "$(running_services)"
check "the root says nothing is deployed" "404" "$(status_of "$HTTPS_ORIGIN/")"
# The status code alone cannot tell a considered front page from a bare 404,
# and a bare 404 is what deployment.caddyfile exists to avoid. Read the
# sentence, so an edit that drops it fails here rather than being noticed by
# whoever opens the hostname next.
check "and names the stack that answered" "yes" \
  "$(body_holds "$HTTPS_ORIGIN/" 'No application is deployed here yet')"
check "the deployment serves it over TLS from Caddy's own authority" \
  "$INTERNAL_AUTHORITY" "$(certificate_issuer "$HTTPS_ORIGIN/")"
check "the health route answers" "200" "$(status_of "$HTTPS_ORIGIN/health")"
check "the deployment sends plain HTTP to HTTPS" \
  "308" "$(status_of "$HTTP_ORIGIN/")"
# id.localhost does not resolve on a machine with no entry for it, so this
# names the address itself rather than asking a resolver. That is also why
# make development publishes the identity service on a port instead of routing
# it: a volunteer opening a login screen cannot pass --resolve to a browser.
check "the deployment serves the identity service under id" \
  "200" "$(identity_status "$ORO_HTTPS_PORT")"
# The port is missing from that target and that is a known defect, warned about
# in .env.example: Caddy cannot see the host side of a published port, so it
# names the standard one. On a deployment holding 80 and 443, which is what
# .env.example ships, the target is right.
check "and names the hostname it was asked for" \
  "https://$ORO_HOSTNAME/" "$(redirect_from "$HTTP_ORIGIN/")"

echo
echo "Bringing up what a laptop adds"
compose_dev up --detach --wait --wait-timeout 300 >/dev/null
check "the override adds the mock and nothing else" \
  "caddy db identity mock" "$(running_services)"
check "the portal is served at the root over plain HTTP" \
  "200" "$(status_of "$HTTP_ORIGIN/")"
check "nothing redirects the reader anywhere" "" "$(redirect_from "$HTTP_ORIGIN/")"
check "the root serves a page" "yes" "$(body_holds "$HTTP_ORIGIN/" '<html')"
check "a member arrives through /v1/me" "200" "$(status_of "$HTTP_ORIGIN/v1/me")"
check "that member has an email address" "yes" "$(body_holds "$HTTP_ORIGIN/v1/me" '"email"')"
check "/v1/nope is refused" "404" "$(status_of "$HTTP_ORIGIN/v1/nope")"
# Caddy has its own 404 for the deployment, so proving the mock wrote this one
# is what proves the proxy reached it rather than falling through.
check "/v1/nope is refused by the mock rather than by Caddy" "yes" \
  "$(body_holds "$HTTP_ORIGIN/v1/nope" 'stoplight.io/prism/errors')"
check "the health route still answers" "200" "$(status_of "$HTTP_ORIGIN/health")"
# There is no TLS listener at all under this shape, so the HTTPS port answers
# nothing. A reader who typed https by habit gets a connection error rather than
# a certificate they have to decide about.
check "the HTTPS port answers nothing" "no" "$(reaches_tls "$HTTPS_ORIGIN/")"
check "the log of every service reaches the mock" "yes" "$(logs_reach_the_mock)"
# The shape a volunteer opens in a browser, and the one nothing checked until
# this line existed. It answers on its own port rather than under id., because
# that name does not resolve on a machine with no entry for it. The identity
# service refuses any call whose Host is not the domain it was configured with,
# so a plain 200 here is also proof that the two shapes agree about its name.
check "the identity service answers on its own port over plain HTTP" \
  "200" "$(status_of "http://$ORO_HOSTNAME:$ORO_IDENTITY_PORT/.well-known/openid-configuration")"
check "and publishes an issuer a client can use" "yes" \
  "$(body_holds "http://$ORO_HOSTNAME:$ORO_IDENTITY_PORT/.well-known/openid-configuration" "\"issuer\":\"http://$ORO_HOSTNAME:$ORO_IDENTITY_PORT\"")"

echo
echo "Taking it down"
compose_dev down --volumes >/dev/null 2>&1
check "nothing is left running" "" "$(running_services)"

echo
if [ "$failed" -gt 0 ]; then
  echo "$failed of $((passed + failed)) checks failed."
  echo "The stack is down, so nothing is left to inspect. Bring it back with"
  echo "make development and call the failing path by hand."
  exit 1
fi
echo "all $passed development stack checks passed"
