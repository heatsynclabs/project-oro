# Operate the Project ORO compose stack: Postgres and Caddy.
#
# Copy .env.example to .env before the first run. Everything here is a thin
# wrapper over docker compose, so any of it can be run by hand when make is in
# the way.

.DEFAULT_GOAL := help
.PHONY: help up down logs ps psql test mock mock-test

help:
	@echo "make up         start Postgres and Caddy in the background"
	@echo "make down       stop them. The database volume is kept"
	@echo "make logs       follow the logs of every service"
	@echo "make ps         show what is running and whether it is healthy"
	@echo "make psql       open a psql shell on the oro database"
	@echo "make test       run the database test suite"
	@echo "make mock       serve the API contract on http://127.0.0.1:4010"
	@echo "make mock-test  prove the mock serves docs/api/members-v1.yaml"
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

down:
	docker compose down

logs:
	docker compose logs --follow

ps:
	docker compose ps

psql:
	docker compose exec db psql -U postgres -d oro

test:
	./db/tests/run.sh

# Deliberately not a service in compose.yaml. That file is the deployment, and
# a fake members API that answers with invented records has no business being
# one docker compose up away from a real hostname. Keeping it here also keeps
# make up working for everybody who already has a .env, because .env.example
# forbids a silent default and a new required variable would stop the stack
# for a tool the stack does not use. ADR 0002 records the trade.
#
# Foreground, so Ctrl-C ends it and the container removes itself. Nothing is
# left running and there is no matching down target to forget.
mock:
	./tools/mock/run.sh

mock-test:
	./tools/mock/tests/run.sh
