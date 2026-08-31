# Operate the Project ORO compose stack: Postgres, Caddy and the identity
# service.
#
# Copy .env.example to .env before the first run. Everything here is a thin
# wrapper, so any of it can be run by hand when make is in the way.

# A laptop adds the mock, points Caddy at the development routes, and publishes
# the identity service on a port a browser can open.
DEV = docker compose -f compose.yaml -f compose.development.yaml

# The identity service's three targets, which are one subject and were the part
# of this file that took it past the ceiling in rule 6.
include make/identity.mk

.DEFAULT_GOAL := help
.PHONY: help up down logs ps psql check test mock-test development development-test portal-test identity-test identity-configure bootstrap-admins migration-test ceilings names backup restore backup-test api-test api-identity-test import-boundaries attributions attributions-check browser-checks

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
	@echo "make portal-test       prove the members portal, through Caddy, with no browser"
	@echo "make browser-checks    open the portal in a real browser. Needs a stack already up"
	@echo "make identity-test     prove the identity service holds the lab's existing passwords"
	@echo "make identity-configure  register the project, the clients and the branding"
	@echo "make bootstrap-admins  seat the first three admins, who can then administer everything"
	@echo "make migration-test    prove the legacy import, and prove it refuses dirty data"
	@echo "make ceilings          check every file and function against the ceilings in rule 6"
	@echo "make names             check that every name a Python module uses exists"
	@echo "make import-boundaries check that the layers in rule 5 only import downward"
	@echo "make backup            write a backup of the members database outside this repository"
	@echo "make restore FILE=...  restore one. It refuses over a database that holds members"
	@echo "make backup-test       run the restore drill: back up, destroy, restore, check"
	@echo "make api-test          prove the members API against a real Postgres and the real policies"
	@echo "make api-identity-test prove the members API accepts a token the identity service issued"
	@echo "make attributions      regenerate the dependency tables in ATTRIBUTIONS.md from the lockfiles"
	@echo "make attributions-check say what those tables would become, and write nothing"
	@echo ""
	@echo "The database this stack starts carries db/migrations and the reference"
	@echo "data, put there by the schema service, and no members at all. make test"
	@echo "applies the migrations to a throwaway container, never to this stack."

# --wait holds until every healthcheck passes, so a stack that did not come up
# fails here rather than in whatever the volunteer runs next. Without it the
# database is still running initdb when this target exits 0, and make psql then
# says the server is not running, which sends the reader after a fault that is
# not there. HANDOFF.md section 7, "pg_isready lies".
#
# It also waits for identity_bootstrap to have exited, because that one runs to
# completion rather than staying up. 300 seconds because the identity service
# applies its own schema and seeds an instance on a first run before it answers,
# and pulling the images happens before the wait starts at all.
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

# One command, because nobody remembers every suite by name at 2am. Each still
# runs on its own, and this is the order CI runs them in.
check:
	./db/tests/run.sh
	./services/door/tests/run.sh
	./packages/gantry-tokens/tests/run.sh
	python3 tools/voice-check/test_voice_check.py
	python3 tools/voice-check/test_regressions.py
	python3 tools/voice-check/test_behaviour.py
	./tools/ci/voice-gate.sh
	./tools/ceilings/run.sh
	./tools/names/run.sh
	./tools/import-boundaries/run.sh
	python3 tools/attributions/test_attributions.py
	./tools/mock/tests/run.sh
	./tools/development/tests/run.sh
	./tools/members-portal/tests/run.sh
	./tools/identity/tests/run.sh
	./tools/migration/tests/run.sh
	./tools/bootstrap/tests/run.sh
	./tools/backup/tests/run.sh
	./services/api/tests/run.sh
	./tools/api-against-identity/run.sh
	@echo
	@echo "every suite passed"

mock-test:
	./tools/mock/tests/run.sh

# The stack a person can open in a browser: the portal at the root and the
# members API under /v1, on one origin, over plain HTTP. Plain because a
# certificate from Caddy's local authority costs a volunteer an administrator
# password and a root certificate in their trust store first. ADR 0003.
#
# The mock lives in compose.development.yaml, an override rather than a profile,
# so make up is unchanged and a deployment never carries it. An override has one
# way to ask for it; the profile had two that disagreed. The mock has had no
# route since the members API took /v1, and make mock-test reaches it on its own
# port. The same 300 seconds make up allows, and this shape needs more of them.
development:
	@test -f .env || { echo "No .env file, so nothing was started. Copy .env.example to .env, set the values in it, and run make development again." >&2; exit 1; }
	@$(DEV) up --detach --wait --wait-timeout 300 || { echo "The development stack did not come up, and the error above says why. If it names a variable, fix that line in .env. If it names a service, make logs shows what that service printed. If it says db is unhealthy on a machine where this stack used to work, see the note under make up." >&2; exit 1; }
	@echo "Up. The portal is at / and the members API is under /v1, over plain HTTP on the hostname and ORO_HTTP_PORT set in .env. The identity service is on localhost and ORO_IDENTITY_PORT. Nothing signs in yet, so a call under /v1 comes back 401 with a problem detail saying so, and that is the API working. The contract mock still runs on ORO_MOCK_PORT with no route of its own, because one prefix cannot answer twice."

development-test:
	./tools/development/tests/run.sh

# The portal itself, through Caddy, with no browser. It brings up its own
# stack on its own ports, so it neither reads nor disturbs one you have up.
portal-test:
	./tools/members-portal/tests/run.sh

# The same portal in a real chromium, which sees the page after its own script
# has run rather than the document Caddy served. One check, and a screenshot
# every time, red or green. ADR 0015 chose the driver.
#
# The only target here that is not in make check, because it drives a stack
# somebody else started rather than bringing up its own. Start one first with
# make development. That cost something once: the check went red for a day
# against a portal that was working, and nothing noticed.
#
# ORO_PORTAL_URL defaults to http://localhost:8080 and ORO_SHOT_DIR to
# $$HOME/oro-screenshots, which is outside the working tree on purpose.
browser-checks:
	./tools/browser-checks/run.sh

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

# Rule 5, over the Python in services/. import-linter reads a real import
# graph, so a violation one import deep is caught the same way a direct one is.
# ADR 0006 chose the tool. ADR 0011 records how it arrives, which is an image
# this repository builds, because nobody publishes one.
# Every name a Python module uses has to exist. ruff reads it with F821, out of
# pyflakes, in the same pinned image the ceilings gate uses. tools/names/run.sh
# carries the bug it was built for.
names:
	./tools/names/run.sh

import-boundaries:
	./tools/import-boundaries/run.sh

# Rule 9, over the two Python lockfiles. It builds the image each lock installs
# into and reads every package's own metadata out of it, so a licence claim in
# ATTRIBUTIONS.md traces to the package rather than to an index summary. It
# rewrites only what sits between the two marker comments in that file.
#
# Deliberately not in make check, which is why there are two targets here. Not
# over the network: make api-test and make import-boundaries already build
# images that install from PyPI. It is out because it rewrites a tracked file,
# and because the check below compares the date the metadata was read, so as a
# gate it would go red the day after every run. What make check runs is the
# generator's own suite, which needs neither docker nor the network. Run this
# when a lockfile changes. ADR 0012 carries the reasoning.
attributions:
	./tools/attributions/run.sh

# The same thing with nothing written. The read date in each section moves
# whenever the metadata is read again, so on a later day this reports that line
# even when no package changed. That is the record of when somebody last looked.
attributions-check:
	./tools/attributions/run.sh --check

# Gate 1 of rule 12: a verified, restorable backup of the members database.
# Two files land in $ORO_BACKUP_DIR, which defaults to $HOME/oro-backups and is
# never allowed to be inside this working tree. A dump is member data, and rule
# 13 says member data is not committed and is not carried around on laptops.
backup:
	@test -f .env || { echo "No .env file, so docker compose cannot read compose.yaml and nothing was backed up. Copy .env.example to .env and run make backup again." >&2; exit 1; }
	@./tools/backup/backup.sh

# make restore FILE=$$HOME/oro-backups/oro-20260828T204500Z.dump
#
# Restoring into an empty database needs nothing else. Restoring over a database
# that still holds members is refused, and the refusal prints the command that
# goes ahead, which carries the number of members it is about to replace:
#
#   make restore FILE=... OVERWRITE=12-members
#
# docs/runbooks/restore-the-members-database.md is the version of this to read
# at 2am, with the expected output at every step.
#
# The confirmation has to be typed on the command line. make imports the
# environment into its own variables, so a plain $(OVERWRITE) would read an
# exported one too, and a single export would arm every later restore in that
# shell with nothing on the command line to see. $(origin) is how make tells a
# command line variable from an inherited one.
restore:
	@test -f .env || { echo "No .env file, so docker compose cannot read compose.yaml and nothing was restored. Copy .env.example to .env and run make restore again." >&2; exit 1; }
	@test -n "$(FILE)" || { echo "Name the archive to restore: make restore FILE=$$HOME/oro-backups/oro-20260828T204500Z.dump" >&2; echo "The newest one is the last line of: ls -l $$HOME/oro-backups" >&2; exit 1; }
	@test -z "$(OVERWRITE)" || test "$(origin OVERWRITE)" = "command line" || { echo "OVERWRITE is set in this shell rather than on this command line, and" >&2; echo "make restore reads it only from the command line. A confirmation you" >&2; echo "cannot see in the command you typed is not a confirmation." >&2; echo "Nothing was restored. Run: unset OVERWRITE" >&2; exit 1; }
	@./tools/backup/restore.sh "$(FILE)" $(if $(filter command,$(firstword $(origin OVERWRITE))),--overwrite "$(OVERWRITE)")

# The drill. It builds its own database, backs it up, destroys it, restores it,
# and then checks that what came back is the same database down to the slot each
# card sits at. It touches nothing that make up started.
backup-test:
	./tools/backup/tests/run.sh

# The first slice of the members API, against a real Postgres carrying the real
# migrations. It builds its own database, its own signing key, its own JWKS
# server and its own image, all named after its own process id, so it neither
# reads nor disturbs a stack you have up.
#
# The service is in the stack as well, as of 2026-08-30: compose.api.yaml, which
# compose.yaml includes, with Caddy serving it under /v1 in both shapes.
api-test:
	./services/api/tests/run.sh

# The two halves of a sign in put together: a member signs in on the hosted
# screens, and the members API accepts the token that comes back and answers
# with that member's own record. Its own compose project on its own ports.
#
# api-test above verifies tokens this repository minted with a key of its own,
# so it cannot see anything about what the provider actually issues. This one
# found ORO_API_TOKEN_AUDIENCE documented as a value nothing issues.
api-identity-test:
	./tools/api-against-identity/run.sh
