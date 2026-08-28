# ADR NNNN: <the decision, as a short noun phrase>

- **Status:** proposed | accepted | superseded by [ADR NNNN](./NNNN-slug.md)
- **Date:** YYYY-MM-DD
- **Deciders:** <names, not roles. Someone has to answer for it.>

## Context

What forced a decision. The constraint, the problem, or the thing that broke.
Two or three sentences. If this section is long, the decision is probably two
decisions.

## Options considered

At least three, per rule 8 of `CLAUDE.md`. For each, state what was actually
checked, not what is generally believed.

### Option A: <name>

- **Last release:** <version, date. Checked how.>
- **Licence:** <SPDX id. Read from the repository, not from memory.>
- **Maintainers:** <one person, a company, a foundation?>
- **Fit:** what it does well here.
- **Cost:** what it makes worse here.

### Option B: <name>

Same shape.

### Option C: <name>

Same shape.

## Decision

We chose **<option>**.

The reasoning, in the order that actually drove it. Lead with the constraint that
eliminated the others.

## The condition that would flip this

One sentence, concrete and observable. Not "if requirements change". Something a
person could check in a year and say yes or no to.

> Example: if the door service ever needs to run on a host with less than 1 GB
> of memory, this choice is wrong and Option B becomes correct.

## Consequences

What this commits us to, including the bad parts.

- What gets easier.
- What gets harder.
- What we now have to operate, back up, patch, or renew.
- What the exit looks like if we reverse this, and roughly what it costs.

## What was borrowed

If this decision takes a design, a schema, or an approach from an existing
project, name it here with a link and its licence. Rule 9. "Inspired by" is not
a citation; say which parts.

## Open questions

Anything unresolved, each with the step that would resolve it. An ADR may ship
with open questions. It may not ship with unstated assumptions.
