# Operate the Project ORO compose stack: Postgres and Caddy.
#
# Copy .env.example to .env before the first run. Everything here is a thin
# wrapper over docker compose, so any of it can be run by hand when make is in
# the way.

# Development adds the mock and points Caddy at the development routes.
DEV = docker compose -f compose.yaml -f compose.development.yaml

.DEFAULT_GOAL := help
.PHONY: help up down logs ps psql check test mock-test development development-test portal-test

help:
	@echo "make up                start Postgres and Caddy in the background"
	@echo "make down              stop everything. The database volume is kept"
	@echo "make logs              follow the logs of every service"
	@echo "make ps                show what is running and whether it is healthy"
	@echo "make psql              open a psql shell on the oro database"
	@echo "make check             run every suite in this repository"
	@echo "make test              run the database test suite alone"
	@echo "make mock-test         prove the mock serves docs/api/members-v1.yaml"
	@echo "make development       start the stack with the portal and the mock too, on plain HTTP"
	@echo "make development-test  prove the portal and the mock share one origin"
	@echo "make portal-test       prove the members portal against the contract mock"
	@echo ""
	@echo "The database this stack starts is empty. make test applies"
	@echo "db/migrations to a throwaway container, never to this stack."

# --wait holds until every healthcheck passes, so a stack that did not come up
# fails here rather than in whatever the volunteer runs next. Without it the
# database is still running initdb when this target exits 0, and make psql then
# says the server is not running, which sends the reader after a fault that is
# not there. HANDOFF.md section 7, "pg_isready lies".
#
# 120 seconds because the database is the slow one: its healthcheck has a 30
# second start period and then 10 tries 5 seconds apart, so it can take 80
# seconds to give up. Pulling the images happens before the wait starts.
up:
	@test -f .env || { echo "No .env file, so nothing was started. Copy .env.example to .env, set the values in it, and run make up again." >&2; exit 1; }
	docker compose up --detach --wait --wait-timeout 120 || { echo "The stack did not come up, and the error above says why. If it names a variable, fix that line in .env. If it names a service, make logs shows what that service printed." >&2; exit 1; }

# Both files, so this reaches the mock as well. Naming a service compose does
# not know about is not an error, so this is safe on a stack started by make up.
down:
	$(DEV) down

logs:
	$(DEV) logs --follow

ps:
	docker compose ps

psql:
	docker compose exec db psql -U postgres -d oro

test:
	./db/tests/run.sh

# One command, because six runners is five too many to remember at 2am. Each
# still runs on its own, and this is the order CI runs them in.
check:
	./db/tests/run.sh
	./services/door/tests/run.sh
	./packages/gantry-tokens/tests/run.sh
	python3 tools/voice-check/test_voice_check.py
	python3 tools/voice-check/test_regressions.py
	python3 tools/voice-check/test_behaviour.py
	./tools/ci/voice-gate.sh
	./tools/mock/tests/run.sh
	./tools/development/tests/run.sh
	./tools/members-portal/tests/run.sh
	@echo
	@echo "every suite passed"

mock-test:
	./tools/mock/tests/run.sh

# The stack a person can open in a browser: the portal at the root and the
# contract mock under /v1, both behind Caddy on one origin, over plain HTTP.
# Plain because a certificate from Caddy's local authority costs a volunteer an
# administrator password and a root certificate in their trust store before a
# browser will open a local page. ADR 0003.
#
# The mock lives in compose.development.yaml, an override rather than a profile,
# so make up is unchanged and a deployment never carries it. An override has one
# way to ask for it. The profile had two that disagreed, and one of them started
# the mock while leaving Caddy serving the deployment 404 in front of it.
#
# 180 seconds rather than the 120 make up allows, because the mock reads the
# whole contract before it answers, and slower still on a machine that has to
# emulate linux/amd64 to run it.
development:
	@test -f .env || { echo "No .env file, so nothing was started. Copy .env.example to .env, set the values in it, and run make development again." >&2; exit 1; }
	@$(DEV) up --detach --wait --wait-timeout 180 || { echo "The development stack did not come up, and the error above says why. If it names a variable, fix that line in .env. If it names a service, make logs shows what that service printed." >&2; exit 1; }
	@echo "Up. The portal is at / and the contract mock is under /v1, over plain HTTP on the hostname and ORO_HTTP_PORT set in .env. No certificate to accept, and nothing redirects."

development-test:
	./tools/development/tests/run.sh

# The portal itself, through Caddy, with no browser. It brings up its own
# stack on its own ports, so it neither reads nor disturbs one you have up.
portal-test:
	./tools/members-portal/tests/run.sh
