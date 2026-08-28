# Operate the Project ORO compose stack: Postgres and Caddy.
#
# Copy .env.example to .env before the first run. Everything here is a thin
# wrapper over docker compose, so any of it can be run by hand when make is in
# the way.

.DEFAULT_GOAL := help
.PHONY: help up down logs ps psql test mock mock-test development development-test portal-test

help:
	@echo "make up                start Postgres and Caddy in the background"
	@echo "make down              stop everything. The database volume is kept"
	@echo "make logs              follow the logs of every service"
	@echo "make ps                show what is running and whether it is healthy"
	@echo "make psql              open a psql shell on the oro database"
	@echo "make test              run the database test suite"
	@echo "make mock              serve the API contract on http://127.0.0.1:4010"
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

# The wildcard is what reaches a service in a profile. Without it, a mock
# started by make development keeps running, the network cannot be removed, and
# compose reports that as a resource still in use rather than as a mistake.
down:
	COMPOSE_PROFILES='*' docker compose down

# The same wildcard, for the same reason. Compose resolves the service list for
# logs the way it resolves it for down, so without this the one service the
# development profile adds is the one service whose output this cannot show,
# and the mock is what a volunteer is reading these logs to diagnose.
logs:
	COMPOSE_PROFILES='*' docker compose logs --follow

ps:
	docker compose ps

psql:
	docker compose exec db psql -U postgres -d oro

test:
	./db/tests/run.sh

# The mock on its own, on the host, with no stack around it and no Caddy in
# front. That is what a client being pointed straight at the contract wants.
# make development runs the same image as a compose service instead, behind
# Caddy, which is what the portal wants.
#
# Foreground, so Ctrl-C ends it and the container removes itself. Nothing is
# left running and there is no matching down target to forget.
mock:
	./tools/mock/run.sh

mock-test:
	./tools/mock/tests/run.sh

# The stack a person can open in a browser: the portal at the root and the
# contract mock under /v1, both behind Caddy on one origin, over plain HTTP.
# Plain because a certificate from Caddy's local authority costs a volunteer an
# administrator password and a root certificate in their trust store before a
# browser will open a local page. ADR 0003.
#
# The mock sits in a compose profile, so make up is unchanged and a deployment
# never carries it. COMPOSE_PROFILES rather than --profile because Caddy picks
# its routes from the same variable, so one name both starts the mock and routes
# to it. The pinned image comes from tools/mock/image.sh, which compose reads
# for itself, so this target is the bare command with a wait around it.
#
# 180 seconds rather than the 120 make up allows, because the mock reads the
# whole contract before it answers, and slower still on a machine that has to
# emulate linux/amd64 to run it.
development:
	@test -f .env || { echo "No .env file, so nothing was started. Copy .env.example to .env, set the values in it, and run make development again." >&2; exit 1; }
	@COMPOSE_PROFILES=development docker compose up --detach --wait --wait-timeout 180 || { echo "The development stack did not come up, and the error above says why. If it names a variable, fix that line in .env. If it names a service, make logs shows what that service printed." >&2; exit 1; }
	@echo "Up. The portal is at / and the contract mock is under /v1, over plain HTTP on the hostname and ORO_HTTP_PORT set in .env. No certificate to accept, and nothing redirects."

development-test:
	./tools/development/tests/run.sh

# The portal itself, through Caddy, with no browser. It brings up its own
# stack on its own ports, so it neither reads nor disturbs one you have up.
portal-test:
	./tools/members-portal/tests/run.sh
