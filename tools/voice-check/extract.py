"""Isolating prose from everything that is not prose, without moving it.

voice-check: reference

Every function here returns a string the **same length** as its input, with the
non-prose regions replaced by spaces. That is the whole design.

The obvious implementation deletes the code blocks and identifiers and returns a
shorter string. Then a match offset in the result means nothing in the original
file, so a finding cannot report a line number, and a `voice-ok:` comment on the
offending line cannot suppress it, because the checker does not know which line
that is. Masking instead of deleting keeps every offset valid, so a match at
position N in the masked text is at position N in the file.
"""
from __future__ import annotations

import re

SUFFIX_PROSE = {".md", ".markdown", ".mdx", ".txt", ".rst"}


def _blank(match: re.Match[str]) -> str:
    """Replace a match with spaces, preserving newlines so line numbers hold."""
    return "".join("\n" if ch == "\n" else " " for ch in match.group(0))


def _mask(text: str, pattern: str, flags: int = 0) -> str:
    return re.sub(pattern, _blank, text, flags=flags)


def _keep_only(text: str, spans: list[tuple[int, int]]) -> str:
    """Blank everything except the given spans, keeping length and newlines."""
    keep = bytearray(b"\x00") * len(text)
    for start, end in spans:
        for i in range(max(0, start), min(len(text), end)):
            keep[i] = 1
    return "".join(
        ch if keep[i] else ("\n" if ch == "\n" else " ")
        for i, ch in enumerate(text)
    )


def mask_markdown(text: str) -> str:
    """Blank the parts of a markdown file that are not running prose."""
    text = _mask(text, r"\A---\n.*?\n---\n", re.S)          # frontmatter
    text = _mask(text, r"```.*?```", re.S)                  # fenced code
    text = _mask(text, r"~~~.*?~~~", re.S)                  # fenced code
    text = _mask(text, r"`[^`\n]+`")                        # inline code
    text = _mask(text, r"(?m)^\s{0,3}#{1,6}\s.*$")          # headings
    text = _mask(text, r"(?m)^\s*\|.*\|\s*$")               # tables
    # [ \t] rather than \s: \s matches a newline, so ^\s{4,}\S would run from
    # a blank line straight through the next paragraph and blank the file.
    text = _mask(text, r"(?m)^[ \t]{4,}\S.*$")              # indented code
    text = _mask(text, r"<!--.*?-->", re.S)                 # comments
    text = _mask(text, r"<style.*?</style>", re.S)
    text = _mask(text, r"<script.*?</script>", re.S)
    text = _mask(text, r"<[^>]+>")                          # tags
    text = _mask(text, r"\]\([^)\s]+\)")                    # link targets
    text = _mask(text, r"(?m)^\s*>\s.*$")                   # block quotes
    return text


# A string long enough and shaped enough to be a sentence rather than an
# identifier, a path, or a SQL fragment: two spaces and a lowercase letter.
def _is_prose(value: str) -> bool:
    return (len(value) >= 25
            and value.count(" ") >= 2
            and re.search(r"[a-z]", value) is not None)


def _string_spans(text: str, pattern: str, flags: int = 0) -> list[tuple[int, int]]:
    out = []
    for match in re.finditer(pattern, text, flags):
        if _is_prose(match.group(1)):
            out.append(match.span(1))
    return out


def mask_code(text: str, suffix: str) -> str:
    """Blank everything in a source file except comments and prose strings."""
    spans: list[tuple[int, int]] = []

    if suffix in {".ts", ".tsx", ".js", ".jsx", ".vue", ".css", ".scss"}:
        spans += [m.span(1) for m in re.finditer(r"/\*\*?(.*?)\*/", text, re.S)]
        spans += [m.span(1) for m in re.finditer(r"(?m)^[ \t]*//[ \t]?(.*)$", text)]
        spans += _string_spans(text, r"`([^`$]*)`", re.S)
        spans += _string_spans(text, r"'([^'\n]*)'")
        spans += _string_spans(text, r'"([^"\n]*)"')
        if suffix == ".vue":
            for block in re.finditer(r"<template>(.*?)</template>", text, re.S):
                inner = mask_markdown(block.group(1))
                start = block.start(1)
                spans += [(start + i, start + i + 1)
                          for i, ch in enumerate(inner) if ch not in " \n"]

    elif suffix == ".py":
        spans += [m.span(1) for m in re.finditer(r'"""(.*?)"""', text, re.S)]
        spans += [m.span(1) for m in re.finditer(r"'''(.*?)'''", text, re.S)]
        spans += [m.span(1) for m in re.finditer(r"(?m)^[ \t]*#[ \t]?(.*)$", text)]
        spans += _string_spans(text, r'"([^"\n]*)"')

    elif suffix == ".sql":
        spans += [m.span(1) for m in re.finditer(r"(?m)^[ \t]*--[ \t]?(.*)$", text)]
        spans += [m.span(1) for m in re.finditer(r"/\*(.*?)\*/", text, re.S)]
        spans += _string_spans(text, r"'([^'\n]*)'")

    # Shell scripts sit here because a shell comment is a hash at the start of a
    # line, which is the same shape. Without this they fall through to the
    # default, every command in the file counts as prose, and a grep for a
    # banned word reads as a use of it.
    elif suffix in {".yml", ".yaml", ".toml", ".sh"}:
        spans += [m.span(1) for m in re.finditer(r"(?m)^[ \t]*#[ \t]?(.*)$", text)]

    elif suffix == ".html":
        return mask_markdown(text)

    else:
        return text

    return _keep_only(text, spans)


def mask_quoted_blocks(text: str) -> str:
    """Blank regions a writer marked as somebody else's words.

    Research and archive documents quote prose that breaks the voice. Marking a
    block is narrower than the file level pragma, which also turns off the
    attribution check for the whole file.
    """
    out = list(text)
    for start, end in _quoted_spans(text, len(out)):
        _blank_span(out, start, end)
    return "".join(out)


def _blank_span(out: list[str], start: int, end: int) -> None:
    """Replace a span with spaces, leaving the newlines where they were.

    The masked text has to stay the same length as the raw text, because every
    check reports offsets into the raw file and the line numbers come from
    counting newlines in it.
    """
    for i in range(start, end):
        if out[i] != "\n":
            out[i] = " "


def _quoted_spans(text: str, length: int) -> list[tuple[int, int]]:
    """Where the marked blocks are, allowing for one nested inside another.

    An opener inside an open block does not start a second span, and only the
    matching closer ends the outer one. An unclosed block runs to the end of the
    file, which is the reading that fails safe: the writer meant to quote and
    forgot the closing marker, so the checks stay off rather than firing on
    somebody else's words.
    """
    open_re = re.compile(r"<!--\s*voice-check:\s*quote\s*-->")
    close_re = re.compile(r"<!--\s*/voice-check:\s*quote\s*-->")
    events = sorted(
        [(m.start(), m.end(), 1) for m in open_re.finditer(text)]
        + [(m.start(), m.end(), -1) for m in close_re.finditer(text)]
    )
    spans = []
    depth = 0
    span_start = None
    for start, end, delta in events:
        if delta == 1:
            span_start = end if depth == 0 else span_start
            depth += 1
            continue
        depth = max(0, depth - 1)
        if depth == 0 and span_start is not None:
            spans.append((span_start, start))
            span_start = None
    if depth > 0 and span_start is not None:
        spans.append((span_start, length))
    return spans


def prose_of(text: str, suffix: str) -> str:
    """The prose in a file, masked in place so every offset still points home."""
    text = mask_quoted_blocks(text)
    if suffix in SUFFIX_PROSE or suffix == "":
        return mask_markdown(text)
    return mask_code(text, suffix)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
            if len(s.split()) >= 4]


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 80]
