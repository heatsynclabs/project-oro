# Operate the Project ORO compose stack: Postgres, Caddy and the identity
# service.
#
# Copy .env.example to .env before the first run. Everything here is a thin
# wrapper over docker compose, so any of it can be run by hand when make is in
# the way.

# A laptop adds the mock, points Caddy at the development routes, and publishes
# the identity service on a port a browser can open.
DEV = docker compose -f compose.yaml -f compose.development.yaml

.DEFAULT_GOAL := help
.PHONY: help up down logs ps psql check test mock-test development development-test portal-test identity-test identity-configure migration-test ceilings

help:
	@echo "make up                start the stack in the background"
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
	@echo "make identity-test     prove the identity service holds the lab's existing passwords"
	@echo "make identity-configure  register the project, the clients and the branding"
	@echo "make migration-test    prove the legacy import, and prove it refuses dirty data"
	@echo "make ceilings          check every file and function against the ceilings in rule 6"
	@echo ""
	@echo "The database this stack starts is empty. make test applies"
	@echo "db/migrations to a throwaway container, never to this stack."

# --wait holds until every healthcheck passes, so a stack that did not come up
# fails here rather than in whatever the volunteer runs next. Without it the
# database is still running initdb when this target exits 0, and make psql then
# says the server is not running, which sends the reader after a fault that is
# not there. HANDOFF.md section 7, "pg_isready lies".
#
# It also waits for identity_bootstrap to have exited, because that one runs to
# completion rather than staying up.
#
# 300 seconds because the identity service is the slow one on a first run: it
# applies its own schema and seeds an instance before it answers. The database
# behind it can take 80 seconds to give up on its own, and pulling the images
# happens before the wait starts at all.
up:
	@test -f .env || { echo "No .env file, so nothing was started. Copy .env.example to .env, set the values in it, and run make up again." >&2; exit 1; }
	docker compose up --detach --wait --wait-timeout 300 || { echo "The stack did not come up, and the error above says why. If it names a variable, fix that line in .env. If it names a service, make logs shows what that service printed. If it says db is unhealthy on a machine where this stack used to work, read the header of db/init/001_identity_role.sql: that file runs only against an empty data directory, so a volume older than it has no identity database and the healthcheck now asks for one." >&2; exit 1; }

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

# One command, because thirteen of them is twelve too many to remember at 2am.
# Each still runs on its own, and this is the order CI runs them in.
check:
	./db/tests/run.sh
	./services/door/tests/run.sh
	./packages/gantry-tokens/tests/run.sh
	python3 tools/voice-check/test_voice_check.py
	python3 tools/voice-check/test_regressions.py
	python3 tools/voice-check/test_behaviour.py
	./tools/ci/voice-gate.sh
	./tools/ceilings/run.sh
	./tools/mock/tests/run.sh
	./tools/development/tests/run.sh
	./tools/members-portal/tests/run.sh
	./tools/identity/tests/run.sh
	./tools/migration/tests/run.sh
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
# The same 300 seconds make up allows, and this shape needs more of it: the mock
# reads the whole contract before it answers, and slower still on a machine that
# has to emulate linux/amd64 to run it.
development:
	@test -f .env || { echo "No .env file, so nothing was started. Copy .env.example to .env, set the values in it, and run make development again." >&2; exit 1; }
	@$(DEV) up --detach --wait --wait-timeout 300 || { echo "The development stack did not come up, and the error above says why. If it names a variable, fix that line in .env. If it names a service, make logs shows what that service printed. If it says db is unhealthy on a machine where this stack used to work, see the note under make up." >&2; exit 1; }
	@echo "Up. The portal is at / and the contract mock is under /v1, over plain HTTP on the hostname and ORO_HTTP_PORT set in .env. The identity service is on localhost and ORO_IDENTITY_PORT. No certificate to accept, and nothing redirects."

development-test:
	./tools/development/tests/run.sh

# The portal itself, through Caddy, with no browser. It brings up its own
# stack on its own ports, so it neither reads nor disturbs one you have up.
portal-test:
	./tools/members-portal/tests/run.sh

# The synthetic half of the phase 2 password proof: hashes written by the
# library the legacy application uses, imported, and signed in with. Its own
# stack on its own ports, and it is the slowest suite here because the identity
# service applies its own schema on first start.
identity-test:
	./tools/identity/tests/run.sh

# Register the project, the four clients and the GANTRY branding against a
# running stack. Idempotent, so it is safe to run again after changing an
# origin. It reads the bootstrap token out of the container, which is the only
# way to read it: that image is distroless and has no shell.
#
# The origins are the deployment's, from .env. A laptop passes its own:
#
#   tools/identity/configure.py --members-origin http://localhost:8080 #     --admin-origin http://localhost:8081 --door-origin http://localhost:8082
identity-configure:
	@test -f .env || { echo "No .env file. Copy .env.example to .env and set the values in it." >&2; exit 1; }
	@ORO_IDENTITY_TOKEN="$$(docker compose cp identity:/bootstrap/pat - 2>/dev/null | tar -xO)" 	 ORO_IDENTITY_URL="https://id.$$(grep '^ORO_HOSTNAME=' .env | cut -d= -f2)" 	 python3 tools/identity/configure.py 	   --members-origin "https://$$(grep '^ORO_HOSTNAME=' .env | cut -d= -f2)" 	   --admin-origin "https://admin.$$(grep '^ORO_HOSTNAME=' .env | cut -d= -f2)" 	   --door-origin "https://door.$$(grep '^ORO_HOSTNAME=' .env | cut -d= -f2)"

# The legacy import, eleven cases. Ten import the same fixture: three carry it
# and seven are refused, each for a reason the suite checks by name. The
# eleventh runs the role step alone and proves it cannot leave the trigger that
# guards role grants turned off.
migration-test:
	./tools/migration/tests/run.sh

# Rule 6, in two tools because no single one measures all five ceilings.
# ADR 0005 records which does what and what was priced against it.
ceilings:
	./tools/ceilings/run.sh
