#!/usr/bin/env python3
"""Read a served HTML page into a flat list of elements, each with its ancestry.

The portal binds a field to an element with `data-field`, and which endpoint
that field has to exist in depends on which `data-source` section and which
`<template>` the element sits under. So a checker needs the ancestry, not just
the tags, and that is the whole reason this file is not a regular expression.

Nothing here validates HTML. It reads the page the way the checks need to ask
about it and no further.
"""
from __future__ import annotations

from html.parser import HTMLParser


class Element:
    def __init__(self, name, attrs, ancestors):
        self.name = name
        self.attrs = attrs
        self.ancestors = ancestors

    def get(self, key, fallback=None):
        return self.attrs.get(key, fallback)

    def enclosing(self, key):
        """The nearest ancestor carrying an attribute, or None."""
        for name, attrs in reversed(self.ancestors):
            if key in attrs:
                return Element(name, attrs, [])
        return None

    def __repr__(self):
        return f"<{self.name} {self.attrs}>"


# Void elements never take an end tag, so a parser that pushes them onto the
# stack reports every later element as their child.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr"}


class _Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []
        self._open: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        pairs = {key: (value if value is not None else "") for key, value in attrs}
        self.elements.append(Element(tag, pairs, list(self._open)))
        if tag not in VOID:
            self._open.append((tag, pairs))

    def handle_startendtag(self, tag, attrs):
        pairs = {key: (value if value is not None else "") for key, value in attrs}
        self.elements.append(Element(tag, pairs, list(self._open)))

    def handle_endtag(self, tag):
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index][0] == tag:
                del self._open[index:]
                return


def elements(html: str) -> list[Element]:
    reader = _Reader()
    reader.feed(html)
    return reader.elements


def named(html: str, tag: str) -> list[Element]:
    return [element for element in elements(html) if element.name == tag]


def carrying(html: str, key: str) -> list[Element]:
    return [element for element in elements(html) if key in element.attrs]
