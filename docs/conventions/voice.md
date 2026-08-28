<!-- voice-check: reference -->

# Voice

How this project writes, everywhere words appear: UI strings, error messages,
documentation, code comments, commit messages, and API descriptions.

**Source.** The word lists, the register table, and the reference pragma come
from the HeatSync Labs brand voice guide, `references/voice.md` in the
`hsl-forge` brand skill package, which is itself derived from heatsynclabs.org,
the bylaws, and the wiki. Where this file and that one disagree, that one wins
and this one gets corrected. The additions here are the parts specific to a
codebase: comments, commit messages, error strings, and the machine gate.

The gate is `tools/voice-check/voice_check.py`. It runs in CI over markdown,
comments, and user visible strings, and on every commit message through
`.githooks/commit-msg`.

---

## 1. Who is speaking

A member, not an institution. HeatSync has no staff and no marketing department.
The person writing the error message is the same person who will read it at 2am
when the door will not open.

Three things are true at once and the writing has to hold all three:

- It is a workshop. Loud, dusty, full of half finished projects.
- It is a 501(c)(3) with a board, bylaws, and a rent bill. Precision matters when
  money, safety, and governance are involved.
- It is a door that is genuinely open to people who have never made anything.

## 2. Register by context

| Context | Register |
|---|---|
| Member facing UI copy | Plain, direct, second person |
| Error messages | What happened, what the system did, what to do next |
| Safety and tool rules | Flat and exact. No jokes, no softening |
| Governance and approvals | Procedural, cites the rule |
| Documentation | Explains why, assumes a competent reader |
| Code comments | Why, never what |
| Commit messages | Imperative mood, one line, then the reasoning |

## 3. Hard bans

These are errors in CI, not preferences.

### No em dashes or en dashes

Anywhere. Prose, alt text, code comments, commit messages, SVG titles, generated
output.

Do not route around it. Replacing an em dash with a double hyphen or a spaced
hyphen in running prose is the same tell wearing a hat, and it reads worse
because it looks like someone knew the rule and dodged it. Restructure the
sentence. Use a comma, a colon, or a full stop. If a clause needs setting off and
none of those work, the sentence wants to be two sentences.

Command line flags are not affected. `docker compose up --build` is a flag, and
the gate knows the difference: a flag has whitespace before the hyphens and none
after.

### No emoji

Never in UI, never in documentation, never in a commit message, and above all
never standing in for an icon.

An emoji as an icon renders differently on every platform, carries no accessible
name for a screen reader, cannot be styled, cannot inherit a token colour, and
shifts the line box. Use an inline SVG from the icon set. This is a correctness
rule.

### No LLM attribution

Covered in full by rule 1 of `CLAUDE.md`. The gate checks commit messages,
documentation, and pull request bodies.

### No safety softening

If a tool requires certification, write required. Never "we recommend" when the
rule is "you may not". This applies to UI copy on the certifications screen, to
the API description of a refusal, and to the error message a member sees when the
door refuses them.

### No exclusion by implication

Never phrase experience, tools, income, or identity as a prerequisite. "Even if
you have never soldered" is fine. "For serious makers" is not. Everyone is
welcome is stated flat, never qualified.

This reaches into product decisions, not only copy. A form that requires a
LinkedIn URL, a placeholder that assumes a person has a company, and an error
that says "invalid name" for a name with no surname are all the same failure.

### No militarised framing

Banned: front lines, battle tested, war room, boots on the ground, arsenal,
weapons grade, tactical, combat, force multiplier, mission critical as filler,
deploy against, target used of a person. This is a community workshop in Mesa.

It holds for placeholder and example copy too, because that is the copy that
ships most often.

### No numbers nobody checked

Member counts, square footage, attendance, dollars raised, uptime. 3,200 square
feet and 2009 are the two safe constants. Everything else gets verified before it
ships, including in a mockup.

## 4. Banned vocabulary

unleash, unlock, elevate, empower, revolutionise, transform your, game changer,
cutting edge, state of the art, seamless, robust (of a community), leverage as a
verb, synergy, ecosystem, innovate, innovation, disrupt, world class, best in
class, passionate about, dive in, delve, journey (of a person learning
something), thrilled to announce, excited to share, we are proud to, in today's
fast paced world, whether you are a beginner or a pro, the sky is the limit,
endless possibilities, one stop shop, thriving community, supercharge, paradigm
shift, move the needle, low hanging fruit.

Two specific to this lab:

- **community** used as a decorative adjective. "Community driven maker community
  space." Say what the community actually did.
- **innovation.** HeatSync members build things. They do not innovate.

Identifiers are exempt because they are code, not prose. A variable may be called
`leverageRatio`. A sentence may not say "leverage the API".

## 5. The rhythm tells

These are warnings rather than errors, because a human writer may have meant it.
Override one line with `voice-ok: <reason>`.

They are the measurable signatures of generated prose. They are listed because
they are bad writing first. That they also identify the writer as a machine is
the secondary problem.

- **"It is not just X, it is Y."** Pick one and say it.
- **The rule of three.** Three parallel items, over and over, paragraph after
  paragraph. One triad per document is fine. Four is a fingerprint.
- **Uniform sentence length.** Human prose varies. Machine prose settles into a
  band around eighteen words and stays there. Vary it. A short sentence. Then a
  longer one that actually carries a clause worth reading.
- **Summary closings.** A final paragraph that restates the piece. Stop when you
  are done.
- **Rhetorical question openers.** "Ever wondered how the door works?"
- **Hedging stacks.** "This might potentially be able to help somewhat."
- **Filler transitions.** Moreover, furthermore, additionally, notably,
  importantly. Once is a word. Three times is a tic.
- **Bold fragments mid prose.** If a sentence needs emphasis, rewrite the
  sentence. Bold is for a term being defined, and for nothing else.
- **Scene setting openers.** "In today's landscape", "in a world where", "when it
  comes to".

## 6. Writing specific things

### Error messages

Three parts, in order: what happened, what the system did about it, what to do
next. Never only the exception text, and never an apology.

Good:

```
The door controller did not answer within 5 seconds. The unlock was not sent,
so the door is unchanged. Try again, and if it keeps failing, check that the
controller is powered and on the lab network.
```

Bad:

```
Error: ETIMEDOUT. Oops, something went wrong! Please try again later.
```

An error a member sees says what the member can do. An error only an admin sees
may name a host or a service. Never leak an internal hostname or a stack trace
to a member.

### Refusals

When the system refuses on purpose, say the rule and who can change it.

```
Rear door unlock is disabled by a lab decision from 2018. The front door
controls are unaffected.
```

Never "permission denied" with nothing else. A refusal that does not name its
rule reads as a bug and generates a support conversation.

### Code comments

Why, never what. If a comment restates the code, delete the comment. If the code
needs a comment to say what it does, rewrite the code.

Every non obvious constant names its source:

```python
# EEPROM user slot ceiling, Open_Access_Control firmware. Writing a slot at or
# above this is past the end of EEPROM, onto the alarm state bytes.
MAX_SLOT = 200
```

### Commit messages

Subject line in the imperative mood, under 72 characters, no trailing full stop.
Then a blank line, then the reasoning: why this change, not what the diff shows.
The diff shows what.

```
Preserve controller slots when importing the legacy database

A slot is an EEPROM address on the door controller, and the legacy card id was
written to it verbatim. The import was assigning fresh slots, which would have
remapped every member's door permission on the first sync after cutover.
```

No attribution trailers. See rule 1 of `CLAUDE.md`.

### Documentation

Do not document the obvious. A README explaining what `npm install` does is noise
that trains people to skip READMEs.

Never write documentation for code that does not exist yet. Aspirational
documentation is the most expensive kind of lie in a codebase, because it reads
exactly like the true kind.

## 7. House terms

Spell and capitalise these this way. They belong in `docs/glossary.md` too,
because code should use the same words.

| Term | Notes |
|---|---|
| do-ocracy | Lowercase, hyphenated |
| Hack Your Hackerspace, HYH | Twice monthly |
| open hours | Lowercase. When the public can come in |
| card access | Lowercase. Earned, based on trust |
| member in good standing | Bylaws term. Use precisely |
| Be excellent to each other | The code of conduct in one line |
| Everyone is welcome | Stated flat, never qualified |
| Open Source. Open Doors. | Site line. Works as a closer |
| 501(c)(3), EIN 27-1277735 | For donation and grant copy |
| 108 W Main St, Mesa, AZ 85201 | Full address, always this form |

Membership framing, verbatim from the site and worth keeping: membership is a
donation to a community, not a subscription to a service. This matters in the
product, not only the copy. The billing screens should not read like a SaaS
account page.

## 8. Running the gate

```
python3 tools/voice-check/voice_check.py docs/ apps/ services/
python3 tools/voice-check/voice_check.py --staged
python3 tools/voice-check/voice_check.py --text "some copy"
python3 -m pytest tools/voice-check/ -q
```

A file whose job is to document the bans, like this one, carries
`voice-check: reference` in its first 40 lines. Only the structural checks run
against it: the accessibility checks stay on, and the voice and attribution
checks are both off, so the banned trailers can be quoted in order to be banned.

The carve out is safe because a trailer only does harm in a commit message or a
pull request body, and neither can claim the pragma. `--commit-msg` ignores it,
and CI lints a pull request body the same way. Pinned by
`test_commit_mode_ignores_the_reference_pragma`.

To overrule a warning on one line, put `voice-ok: <reason>` on it. A reason is
required. "voice-ok" alone does not suppress anything.
