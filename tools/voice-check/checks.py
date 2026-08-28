"""The checks themselves.

voice-check: reference

Every check takes the raw text and the masked prose, which are the same length,
and reports offsets that are valid in the raw file. That is what makes line
numbers and the `voice-ok:` escape hatch work.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from statistics import pstdev

import rules
from extract import paragraphs, prose_of, sentences


@dataclass
class Finding:
    level: str          # "error" or "warn"
    rule: str
    message: str
    line: int | None = None
    excerpt: str = ""

    def render(self, path: str) -> str:
        where = f"{path}:{self.line}" if self.line else path
        tail = f"  |  {self.excerpt.strip()[:80]}" if self.excerpt else ""
        return f"{where}: {self.level}: [{self.rule}] {self.message}{tail}"


def line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def suppressed(raw: str, line: int | None) -> bool:
    if line is None:
        return False
    lines = raw.splitlines()
    return 0 < line <= len(lines) and bool(rules.LINE_PRAGMA.search(lines[line - 1]))


def _report(raw: str, out: list[Finding], level: str, rule: str,
            message: str, offset: int, excerpt: str) -> None:
    line = line_at(raw, offset)
    if not suppressed(raw, line):
        out.append(Finding(level, rule, message, line, excerpt))


# --------------------------------------------------------------------------

def check_dashes(raw: str, prose: str, out: list[Finding]) -> None:
    for char, name in rules.DASH_CHARS:
        for match in re.finditer(re.escape(char), raw):
            _report(raw, out, "error", "dash",
                    f"contains an {name}. Use a comma, a colon, or a full stop",
                    match.start(), raw[max(0, match.start() - 35):match.start() + 35])

    for pattern, label in rules.DASH_DODGES:
        for match in re.finditer(pattern, prose, re.I):
            _report(raw, out, "error", "dash-dodge",
                    f"{label} standing in for an em dash. Restructure the "
                    "sentence, do not substitute punctuation",
                    match.start(), match.group(0))


def check_emoji(raw: str, out: list[Finding]) -> None:
    for match in rules.EMOJI.finditer(raw):
        if match.group(0) in rules.DINGBAT_ALLOWED:
            continue
        _report(raw, out, "error", "emoji",
                f"contains the emoji {match.group(0)!r}. Use an inline SVG from "
                "the icon set. An emoji has no accessible name and cannot take "
                "a token colour",
                match.start(), raw[max(0, match.start() - 25):match.start() + 25])


def check_attribution(raw: str, out: list[Finding]) -> None:
    for pattern, why in rules.ATTRIBUTION:
        for match in re.finditer(pattern, raw, re.I):
            out.append(Finding(
                "error", "attribution",
                f"{why}. The human who ran the session is the author",
                line_at(raw, match.start()), match.group(0)))


def check_words(raw: str, prose: str, out: list[Finding]) -> None:
    """Report every occurrence, not only the first.

    Reporting one hit per banned word per file understates the problem, and a
    writer fixing them one build at a time is a bad use of a gate.
    """
    for group, rule, note in (
        (rules.BANNED_WORDS, "banned-word", "banned vocabulary"),
        (rules.MILITARISED, "militarised",
         "militarised language. HeatSync is a community workshop"),
    ):
        for word in group:
            pattern = rf"\b{re.escape(word)}{rules.INFLECTIONS}\b"
            for match in re.finditer(pattern, prose, re.I):
                _report(raw, out, "error", rule,
                        f"{match.group(0)!r} is {note}",
                        match.start(), match.group(0))


def check_constructions(raw: str, prose: str, out: list[Finding]) -> None:
    for group, level, rule in (
        (rules.CONSTRUCTIONS, "error", "construction"),
        (rules.SAFETY_SOFTENING, "error", "safety"),
        (rules.EXCLUSION, "error", "exclusion"),
        (rules.ASSUMPTION_TELLS, "warn", "assumption"),
    ):
        for pattern, why in group:
            for match in re.finditer(pattern, prose, re.I):
                _report(raw, out, level, rule, f"uses {why}",
                        match.start(), match.group(0))
                break       # one per pattern per file is enough to make the point


def check_rhythm(prose: str, out: list[Finding]) -> None:
    """The statistical tells. Warnings, permanently.

    Sentence length variance on a short README is noise, so these never fail a
    build. Eight sentences is the floor before any of it means anything.
    """
    sents = sentences(prose)
    if len(sents) >= 8:
        lengths = [len(s.split()) for s in sents]
        mean = sum(lengths) / len(lengths)
        if mean > 8 and pstdev(lengths) / mean < 0.32:
            out.append(Finding(
                "warn", "rhythm",
                f"sentence length is unnaturally uniform (mean {mean:.0f} words, "
                f"spread {pstdev(lengths):.1f}). Vary it"))

    triads = re.findall(r"\b\w[\w\s]{2,28}, [\w\s]{2,28}, and [\w\s]{2,28}\b", prose)
    if len(triads) >= 3:
        out.append(Finding(
            "warn", "triad",
            f"{len(triads)} three item lists. Three parallel items over and "
            "over is the clearest tell that a machine wrote it. Keep one"))

    words = re.findall(r"\b\w+\b", prose.lower())
    if len(words) > 120:
        hedges = sum(words.count(h) for h in rules.HEDGES)
        if hedges / len(words) > 0.022:
            out.append(Finding(
                "warn", "hedging",
                f"{hedges} hedges in {len(words)} words. Say the thing"))

    for para in paragraphs(prose):
        if re.match(r"(?i)^(in (summary|conclusion|short)|to (sum up|summarise|"
                    r"summarize)|overall,|ultimately,)", para):
            out.append(Finding(
                "warn", "closing",
                "a summary closing that restates the piece. Stop when you are done"))

    starts = [s.split()[0].lower() for s in sents if s.split()]
    for opener in ("moreover", "furthermore", "additionally", "notably", "importantly"):
        if starts.count(opener) >= 2:
            out.append(Finding(
                "warn", "transition",
                f"{opener!r} opens {starts.count(opener)} sentences. It is filler"))

    # Mid sentence means mid sentence. Bold at the start of a line is a
    # definition term or a labelled list item, which is structure.
    mid = re.findall(r"(?m)(?<=[\w)\]])[ ,;(]\*\*[^*\n]{1,60}\*\*(?![*\w])", prose)
    if len(mid) >= 4:
        out.append(Finding(
            "warn", "emphasis",
            f"{len(mid)} bolded fragments mid sentence. If a sentence needs "
            "emphasis, rewrite the sentence"))


def check_structure(raw: str, path: Path, out: list[Finding]) -> None:
    if path.suffix != ".html":
        return
    if "<html" in raw and "lang=" not in raw:
        out.append(Finding("error", "a11y", "html element has no lang attribute"))
    if '<meta name="viewport"' not in raw and "<head" in raw:
        out.append(Finding("error", "a11y", "no viewport meta tag"))
    for match in re.finditer(r"<img\b(?![^>]*\balt=)[^>]*>", raw):
        out.append(Finding("error", "a11y", "img without an alt attribute",
                           line_at(raw, match.start()), match.group(0)[:60]))


def lint(raw: str, path: Path, commit_mode: bool = False) -> list[Finding]:
    out: list[Finding] = []
    head = "\n".join(raw.splitlines()[:40])
    is_reference = rules.REFERENCE_PRAGMA in head

    # A reference file has to quote the banned trailers in order to ban them.
    # Safe, because the trailer only does harm in a commit message or a pull
    # request body, and neither can claim the pragma: commit mode ignores it.
    if commit_mode or not is_reference:
        check_attribution(raw, out)
    check_structure(raw, path, out)

    if is_reference and not commit_mode:
        return out

    if commit_mode:
        raw = re.sub(r"(?m)^#.*$", _blank_line, raw)   # git's comment block
    prose = prose_of(raw, "" if commit_mode else path.suffix)

    check_dashes(raw, prose, out)
    check_emoji(raw, out)
    check_words(raw, prose, out)
    check_constructions(raw, prose, out)
    if not commit_mode:
        check_rhythm(prose, out)
    return out


def _blank_line(match: re.Match[str]) -> str:
    return " " * len(match.group(0))
