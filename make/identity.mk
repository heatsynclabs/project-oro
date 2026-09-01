# The identity service: the suite that proves it, the step that configures it,
# and the command that seats the first three admins.
#
# Its own file, included by the Makefile at the repository root, because that
# file reached the 300 line ceiling in rule 6 of CLAUDE.md and these three
# targets are one subject. Every variable the root Makefile sets is in scope
# here: make includes before it does anything else.
#
# .PHONY for these targets stays in the root Makefile, in one list, so there is
# one place to look for the whole set.

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
# The origins are the deployment's, from .env, built from ORO_HOSTNAME with no
# port on them. That is right for a deployment on 443 and wrong everywhere else,
# and this used to give a laptop the wrong example. Measured on 2026-08-31:
# ORO_IDENTITY_URL=http://localhost:8180 make identity-configure registered the
# members portal with a redirect of https://localhost/ while the portal is
# served at http://localhost:8080, so the sign in screens refuse the redirect
# the browser comes back on.
#
# So a laptop calls the step directly with the origins it actually serves, and
# so does a deployment on a port other than 443, which is step 6 of
# docs/runbooks/deploy-beside-the-legacy-system.md:
#
#   ORO_IDENTITY_TOKEN="$$(docker compose cp identity:/bootstrap/pat - | tar -xO)" \
#   ORO_IDENTITY_URL=http://localhost:8180 \
#     python3 tools/identity/configure.py \
#       --members-origin http://localhost:8080 \
#       --admin-origin http://localhost:8081 \
#       --door-origin http://localhost:8082 \
#       --mail-host mail:1025
identity-configure:
	@test -f .env || { echo "No .env file. Copy .env.example to .env and set the values in it." >&2; exit 1; }
	@ORO_IDENTITY_TOKEN="$$(docker compose cp identity:/bootstrap/pat - 2>/dev/null | tar -xO)" \
	 ORO_IDENTITY_URL="$${ORO_IDENTITY_URL:-https://id.$$(grep '^ORO_HOSTNAME=' .env | cut -d= -f2)}" \
	 python3 tools/identity/configure.py \
	   --members-origin "https://$$(grep '^ORO_HOSTNAME=' .env | cut -d= -f2)" \
	   --admin-origin "https://admin.$$(grep '^ORO_HOSTNAME=' .env | cut -d= -f2)" \
	   --door-origin "https://door.$$(grep '^ORO_HOSTNAME=' .env | cut -d= -f2)" \
	   $$(grep -q '^ORO_MAIL_HOST=..*' .env && echo --mail-host "$$(grep '^ORO_MAIL_HOST=' .env | cut -d= -f2)")

# The first three admins. Nothing else in this repository can make one: the
# database allows three admin grants with no approval behind them, and after
# that a grant needs a second admin to approve it. Three rather than two so the
# lab has a spare, per docs/plan/people-and-custody.md section 1.
#
#   make bootstrap-admins ADMIN1="Ada Byron <ada@example.org>" \
#     ADMIN2="Grace Hopper <grace@example.org>" \
#     ADMIN3="Katherine Johnson <katherine@example.org>"
#
# Run it from a terminal. Each new admin gets a password that is printed there
# and written to no file, and the command refuses rather than seating people
# whose passwords nobody can read. Safe to run again: it reports what is already
# seated and changes nothing. A laptop passes its own ORO_IDENTITY_URL, the same
# way identity-configure needs one:
#
#   ORO_IDENTITY_URL=http://localhost:8180 make bootstrap-admins ADMIN1=...
bootstrap-admins:
	@test -f .env || { echo "No .env file. Copy .env.example to .env and set the values in it." >&2; exit 1; }
	@if [ -z "$(ADMIN1)" ] || [ -z "$(ADMIN2)" ] || [ -z "$(ADMIN3)" ]; then \
	  echo 'Name three people, each as a name and an address:' >&2; \
	  echo '  make bootstrap-admins ADMIN1="Ada Byron <ada@example.org>" ADMIN2=... ADMIN3=...' >&2; \
	  echo 'For any other number of people, tools/bootstrap/seat_admins.py takes --admin as many times as you name it.' >&2; \
	  exit 1; \
	fi
	@ORO_IDENTITY_TOKEN="$$(docker compose cp identity:/bootstrap/pat - 2>/dev/null | tar -xO)" \
	 ORO_IDENTITY_URL="$${ORO_IDENTITY_URL:-https://id.$$(grep '^ORO_HOSTNAME=' .env | cut -d= -f2)}" \
	 python3 tools/bootstrap/seat_admins.py \
	   --admin "$(ADMIN1)" --admin "$(ADMIN2)" --admin "$(ADMIN3)"
