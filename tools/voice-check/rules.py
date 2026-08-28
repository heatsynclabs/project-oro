"""Ban lists and pattern tables for the prose gate.

voice-check: reference
This file holds the ban lists, so it must quote what it bans.

Data only. The checks that consume these live in `checks.py`.

The word lists, the register model, and the reference pragma come from
`references/voice.md` in the HeatSync `hsl-forge` brand skill package. Where that
file and this one disagree, that one wins. Additions here are the parts specific
to a codebase: attribution trailers, and the constructions that identify machine
written prose.
"""
from __future__ import annotations

import re

REFERENCE_PRAGMA = "voice-check: reference"
LINE_PRAGMA = re.compile(r"voice-ok:\s*\S")

# A block a writer marks as somebody else's words. Research notes and archive
# documents have to quote prose that breaks the voice, and the file level
# pragma is too blunt for that: it disables the attribution and structural
# checks too.
QUOTE_OPEN = re.compile(r"<!--\s*voice-check:\s*quote\s*-->")
QUOTE_CLOSE = re.compile(r"<!--\s*/voice-check:\s*quote\s*-->")

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

BANNED_WORDS = [
    "unleash", "unlock your", "elevate your", "empower", "revolutionise",
    "revolutionize", "transform your", "game changer", "game-changer",
    "cutting edge", "cutting-edge", "state of the art", "state-of-the-art",
    "seamless", "seamlessly", "synergy", "innovate", "innovation",
    "innovative", "disrupt", "world class", "world-class", "best in class",
    "best-in-class", "passionate about", "dive in", "deep dive", "delve",
    "thrilled to announce", "excited to share", "excited to announce",
    "we are proud to", "we're proud to", "fast-paced world",
    "fast paced world", "sky is the limit", "endless possibilities",
    "one-stop shop", "one stop shop", "innovation hub", "maker ecosystem",
    "incubator", "ideas come to life", "thriving community",
    "supercharge", "turbocharge", "next-generation", "next generation",
    "paradigm shift", "move the needle", "low-hanging fruit",
    "leverage", "ecosystem play", "holistic", "bespoke solution",
]

MILITARISED = [
    "front lines", "frontline", "battle-tested", "battle tested", "war room",
    "boots on the ground", "arsenal", "weapons grade", "weapons-grade",
    "tactical", "combat", "force multiplier", "weaponise", "weaponize",
    "mission-critical", "mission critical", "deploy against", "kill chain",
]

# Ordinary inflections, so a ban on "unleash" also catches "unleashes" and a
# ban on "empower" also catches "empowerment".
INFLECTIONS = r"(?:s|es|ed|d|ing|ment|ly)?"

HEDGES = [
    "might", "maybe", "perhaps", "possibly", "somewhat", "fairly", "rather",
    "quite", "generally", "typically", "usually", "often", "potentially",
    "arguably", "relatively",
]

# Rule 2 says these are not evidence. The hedging check approximates the rest.
ASSUMPTION_TELLS = [
    (r"\bshould (just )?work\b", "'should work' is not evidence. Run it"),
    (r"\bpresumably\b", "'presumably' is an unstated assumption"),
    (r"\bstandard practice is\b", "'standard practice is' cites nothing"),
    (r"\bin theory\b", "'in theory' is an unstated assumption"),
]

# --------------------------------------------------------------------------
# Attribution. Rule 1.
# --------------------------------------------------------------------------

# Banned everywhere, because they leak into changelogs and pull request bodies
# too. A `voice-check: reference` file is exempt so it can quote them in order to
# ban them; a commit message can never claim that pragma.
ATTRIBUTION = [
    (r"co-authored-by:\s*claude", "an LLM named as a commit co-author"),
    (r"co-authored-by:.*\banthropic\b", "an LLM named as a commit co-author"),
    (r"co-authored-by:.*\b(gpt|copilot|cursor|codex|gemini)\b",
     "an AI tool named as a commit co-author"),
    (r"generated with \[?claude", "a generated-with attribution"),
    (r"generated with \[?(chatgpt|copilot|cursor|codex)",
     "a generated-with attribution"),
    (r"claude-session:", "a session trailer"),
    (r"\bassisted-by:\s*(claude|gpt|ai\b)", "an AI assistance trailer"),
    (r"\bai-generated:", "an AI generation trailer"),
    ("\U0001F916", "the robot emoji, usually part of an AI attribution trailer"),
]

# --------------------------------------------------------------------------
# Constructions
# --------------------------------------------------------------------------

CONSTRUCTIONS = [
    (r"not just [^.,;]{2,40},? (it'?s|but|it is) ",
     "the 'not just X, it's Y' construction. Pick one and say it"),
    (r"\bin a world where\b", "'in a world where'"),
    (r"(?im)^\s*(ever (wanted|wondered|thought)|have you ever)\b",
     "a rhetorical question opener"),
    (r"\bwhether you(?:'re| are) a (beginner|newbie|pro|expert)\b",
     "the 'whether you are a beginner or a pro' formula"),
    (r"\bjourney\b(?![^.]{0,30}(bike|road|drive|home))",
     "'journey' used of a person learning something"),
    (r"\bit'?s worth noting that\b",
     "'it is worth noting that', which notes nothing"),
    (r"\bat the end of the day\b", "'at the end of the day' as filler"),
    (r"(?i)\bin (today|this)'?s? (digital |modern )?(landscape|world|age)\b",
     "a scene setting opener"),
    (r"(?i)\blet'?s (dive|jump) (in|into)\b", "'let us dive in'"),
    (r"(?i)\bwhen it comes to\b", "'when it comes to' as a topic opener"),
]

SAFETY_SOFTENING = [
    (r"\bwe recommend (you )?(get |take |complete )?(the )?certif",
     "certification stated as a recommendation rather than a requirement"),
    (r"\bshould (probably )?be certified\b", "a certification requirement hedged"),
    (r"\bit'?s a good idea to (get |be )?certif",
     "a certification requirement hedged"),
]

EXCLUSION = [
    (r"(?i)\bfor serious (makers|builders|hackers)\b",
     "exclusion by implication. Everyone is welcome is stated flat"),
    (r"(?i)\breal (makers|engineers|hackers) (know|use|understand)\b",
     "exclusion by implication"),
    (r"(?i)\bif you'?re not .{0,30}, this (is not|isn'?t) for you\b",
     "exclusion by implication"),
]

# --------------------------------------------------------------------------
# Dashes
# --------------------------------------------------------------------------

DASH_CHARS = [
    ("—", "em dash"),
    ("–", "en dash"),
    ("―", "horizontal bar"),
    ("⸺", "two-em dash"),
]

# A command line flag is `--word`: whitespace before, none after, so none of
# these match it. `[ \t]` rather than `\s`, because `\s` matches a newline and
# would read a sentence followed by a markdown bullet as a substituted dash.
DASH_DODGES = [
    (r"[a-z]{2,}[ \t]+--[ \t]+[a-z]{2,}", "a spaced double hyphen"),
    (r"[a-z]{2,}--[a-z]{2,}", "an attached double hyphen"),
    (r"[a-z]{3,}[ \t]+-[ \t]+[a-z]{3,}", "a spaced hyphen"),
]

# --------------------------------------------------------------------------
# Emoji
# --------------------------------------------------------------------------

# Deliberately excludes the Arrows block (U+2190 to U+21FF) and most of
# Dingbats. A rightwards arrow describing a mapping and a check mark in a
# checklist are typography, not emoji, and flagging them trains people to
# ignore the gate.
EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # pictographs, emoticons, symbols, supplemental
    "\U00002600-\U000026FF"   # miscellaneous symbols
    "\U0001F1E6-\U0001F1FF"   # regional indicators, flags
    "\U0000FE0F"              # variation selector 16, the emoji presentation
    "]"
)

# Dingbats that are legitimate typography rather than emoji.
DINGBAT_ALLOWED = {"✓", "✗", "✔", "✘", "•", "…"}
