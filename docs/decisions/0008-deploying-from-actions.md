# ADR 0008: GitHub Actions may deploy, and holds a key to do it

- **Status:** accepted, and it supersedes a decision recorded in `docs/plan/architecture.md` sections 2 and 3
- **Date:** 2026-08-28
- **Deciders:** TBD. `docs/plan/people-and-custody.md` section 1 has no names in it yet, and this one needs a real name more than most, because it is about who holds a credential.

## Context

`docs/plan/architecture.md` section 2 recorded "GitHub Actions for tests only,
never holding deploy credentials", and section 3 said GitHub "does not hold
deployment credentials and cannot deploy". The reason given is real and it is
recorded in the archive: infrastructure was registered under individual accounts
rather than organisational ones, and in April 2026 a lapse in that arrangement
took the door with it.

That reasoning is about **dependency on an account the lab does not control**.
It was applied to deployment as a whole, and on inspection it does not reach
that far. What it forbids is a deployment that cannot be performed any other
way. A deployment that a person can also do by hand, from the same repository
with the same command, is not that.

There is also no server yet, and as of 2026-08-31 that is a larger gap than
this record assumed. It said phase 0 was blocked on a shell on hsl-web. That
shell was granted and used, and the survey it produced,
`docs/plan/hsl-web-survey.md`, found that hsl-web cannot run this stack at all:
32 bit, CentOS 6.8, kernel 2.6.32, and Docker needs `x86_64` and 3.10 or newer.
So the deploy this decision is about has no target host, and choosing one is
open. This decision is still being made while it costs nothing to change, which
is the cheapest moment to make it.

## Options considered

### Option A: no deployment from CI, as recorded today

- **Fit:** nothing to compromise, nothing to rotate, no new custody question.
- **Cost:** deploying is a person on a laptop with a shell and a memory of the
  steps, which is precisely the arrangement `people-and-custody.md` was written
  against. Three previous rewrites had exactly one person who knew how to
  deploy.

### Option B: push from Actions over SSH, behind a GitHub environment

- **Fit:** the deploy is written down and reviewable, it runs the same command a
  person would, and the environment gate means the credential is not readable by
  every workflow in the repository.
- **Cost:** GitHub holds a key that can reach the host. If the organisation is
  lost, that key has to be revoked on the host, which is a step somebody has to
  remember.

### Option C: pull from the host, with Actions publishing nothing but a tag

- **What it is:** a timer on the host that fetches and runs `make up` when the
  trunk moves.
- **Fit:** GitHub holds no credential at all, which keeps section 3 exactly as
  written.
- **Cost:** the host needs a scheduler and a log somebody reads, deploys happen
  on a delay nobody chose, and rolling back means racing the timer. It moves the
  operational burden onto the machine the lab is least able to look after.

## Decision

**Option B, with the escape written into the workflow itself.**

The deployment step is `make up` over SSH, and nothing else. Not a build, not a
registry push, not a provider CLI. That is the same command
`docs/plan/architecture.md` section 3 already says a member can run after
cloning the repository onto a machine they own, so the test that section sets
still passes: if GitHub is gone tomorrow, deploying is one `ssh` and one `make`.

The workflow runs only when somebody asks for it, and it asks them to type the
hostname first. There is no deploy on push. A deployment nobody chose to make,
at a time nobody chose, is how a door goes down at 2am on somebody else's
schedule.

It is dormant. No secret exists, and with none set the job says which are
missing and stops green rather than red, because a workflow that is red on every
run is one people stop reading.

## The condition that would flip this

If the lab ever puts anything in that workflow that a person cannot do by hand
from a clone, this decision is void and Option C becomes correct. The check is
concrete: read `deploy.yml`, and if the deployment step is still `make up` over
SSH, it holds.

## Consequences

- Four secrets have to exist before it can run, and each one is a thing somebody
  holds: `ORO_DEPLOY_HOST`, `ORO_DEPLOY_USER`, `ORO_DEPLOY_SSH_KEY`, and
  `ORO_DEPLOY_KNOWN_HOSTS`. `ORO_DEPLOY_PATH` is optional and defaults to
  `/srv/oro`.
- The host key is a secret rather than something the runner accepts on first
  sight. Accepting whatever answers is trusting the network to introduce the
  server.
- The key on the host should be restricted to what this does, and that is a
  server side decision nobody can make until there is a server.
- `.env` never leaves the host. It holds the database password, the identity
  master key and the door controller password, and rule 13 of `CLAUDE.md` gives
  each of those one holder.
- **This workflow has never run.** It cannot until a server exists, and the
  first person to use it should expect to fix something in it.
- `docs/plan/architecture.md` sections 2 and 3 now carry a pointer here rather
  than the sentence they used to carry.

## What was borrowed

Nothing. The workflow uses `actions/checkout`, already pinned and attributed,
and the `ssh` on the runner image.

## Open questions

- Whether the GitHub environment should require a reviewer. It is one setting
  and it turns a deploy into a two person action, which would match the shape of
  the two approver rule this project introduces elsewhere. It needs somebody to
  decide who reviews.
- Whether a deploy should be able to run anything other than `make up`, for
  instance a migration. Today it cannot, and the answer should stay no until
  somebody has watched a migration run on staging.
