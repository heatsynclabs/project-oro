"""What a custom property resolves to on a given theme and ground.

This is a model of one specific file, `packages/gantry-tokens/tokens.css`, and
not a CSS engine. It handles the three things that file does: a theme selected
by `:root[data-theme=...]`, a ground selected by `[data-ground=...]` on any
element, and `var()` chains between them. Anything more would be a browser.

The model that matters: a theme is set on the root element, a ground is set on
the root element or on any element below it, and the ground wins for the tokens
it declares. So the environment for a pair is the theme's declarations in
document order, then the ground's on top.
"""
from __future__ import annotations

import re

Block = tuple[list[str], dict[str, str]]

_THEME = re.compile(r'^:root\[data-theme="([^"]+)"\]$')
_GROUND = re.compile(r'^\[data-ground="([^"]+)"\]$')
# Anchored at the start of the block or just after a semicolon, so a colon
# inside a value cannot be read as the start of another declaration.
_DECLARATION = re.compile(r"(?:^|;)\s*([\w-]+)\s*:\s*([^;]+)")
_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)")

# A chain longer than this is a mistake rather than a design, and the cycle
# guard below already covers the common way that happens.
_MAX_LINKS = 32


class BaseAfterThemeError(Exception):
    """A bare `:root` block is declared after a `:root[data-theme=...]` block.

    The model here merges in document order and treats a bare `:root` as
    applying under every theme, because that is what it is: the base. A browser
    does not, because `:root[data-theme="dark"]` is the more specific selector
    and wins wherever it is written.

    So in that order the two disagree. The checker measures the later base
    values as if they were the theme's, the browser paints the theme's, and the
    checker is the one that is wrong. It reports a clean run on a file whose
    dark theme it never looked at.

    Teaching this model specificity would make it a CSS engine, which the
    docstring above refuses. Refusing the one arrangement where the shortcut
    breaks costs a rule and keeps the model honest. Declare the base first.
    """


class NestedGroundError(Exception):
    """A theme or ground block sits inside an at-rule.

    The flat model here would not see it, so the checker would report on a file
    it had only half read. Failing loudly is the only honest answer.
    """


def _selectors_of(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _is_theme_or_ground(selectors: list[str]) -> bool:
    return any(selector == ":root" or selector.startswith("[data-ground")
               or _THEME.match(selector) for selector in selectors)


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def parse_blocks(css: str) -> list[Block]:
    """Every rule in the file, in document order, with its custom properties."""
    blocks = [(selectors, {name: value for name, value in declarations.items()
                           if name.startswith("--")})
              for selectors, declarations in parse_rules(css)]
    _refuse_base_after_theme(blocks)
    return blocks


def _refuse_base_after_theme(blocks: list[Block]) -> None:
    """Refuse the one block order this model reads differently from a browser.

    Only a collision matters. A later bare `:root` block that declares tokens
    no theme declares is theme independent, which is what the type scale and
    the spacing steps are, and it is fine where it is. What is not fine is a
    later base block redeclaring a token a theme already set, because then the
    two disagree about which value that token has under that theme.
    """
    claimed: dict[str, str] = {}
    for selectors, declarations in blocks:
        # Grounds are meant to layer over a theme, per the docstring above, so
        # `:root, [data-ground="page"]` is the intended shape and not a clash.
        is_ground = any(s.startswith("[data-ground") for s in selectors)
        if not is_ground and any(s == ":root" for s in selectors):
            clash = sorted(set(declarations) & set(claimed))
            if clash:
                theme = claimed[clash[0]]
                raise BaseAfterThemeError(
                    f"the bare :root block declaring {', '.join(clash[:3])} is "
                    f"written after the :root[data-theme=\"{theme}\"] block "
                    f"that also declares {clash[0]}. Declare the base set "
                    "first. This model merges in document order, so in this "
                    "order it would measure the base value as if it were the "
                    "theme's, while a browser would paint the theme's. It "
                    "would report a clean run on a theme it never looked at.")
        for selector in selectors:
            if (match := _THEME.match(selector)):
                for name in declarations:
                    claimed.setdefault(name, match.group(1))


def parse_rules(css: str) -> list[Block]:
    """Every rule in the file, in document order, with every declaration.

    Ordinary properties are kept here and dropped by `parse_blocks`, because
    the rule that paints a ground declares no custom property at all and a
    custom property view of the file cannot see whether painting is there.

    Only blocks at the top level are returned. A block nested in an at-rule is
    skipped, and raises if it is one this checker would otherwise have to
    understand.
    """
    css = _strip_comments(css)
    blocks: list[Block] = []
    depth = 0
    prelude_start = 0
    stack: list[str] = []
    for index, char in enumerate(css):
        if char == "{":
            stack.append(css[prelude_start:index])
            depth += 1
            prelude_start = index + 1
        elif char == "}":
            if not stack:
                continue
            prelude = stack.pop()
            depth -= 1
            selectors = _selectors_of(prelude)
            if depth == 0:
                blocks.append((selectors, _declarations_of(css[prelude_start:index])))
            elif _is_theme_or_ground(selectors):
                raise NestedGroundError(
                    f"the block {prelude.strip()!r} is inside an at-rule. "
                    "Move it to the top level of the token file, or teach "
                    "cascade.py about at-rules before relying on this check")
            prelude_start = index + 1
    return blocks


def _declarations_of(body: str) -> dict[str, str]:
    return {name: value.strip() for name, value in _DECLARATION.findall(body)}


def themes(blocks: list[Block]) -> list[str]:
    found = {match.group(1)
             for selectors, _ in blocks
             for selector in selectors
             if (match := _THEME.match(selector))}
    return sorted(found)


def grounds(blocks: list[Block]) -> list[str]:
    found = {match.group(1)
             for selectors, _ in blocks
             for selector in selectors
             if (match := _GROUND.match(selector))}
    return sorted(found)


def _applies_at_root(selectors: list[str], theme: str) -> bool:
    return any(selector == ":root"
               or (_THEME.match(selector) and _THEME.match(selector).group(1) == theme)
               for selector in selectors)


def _applies_on_ground(selectors: list[str], ground: str) -> bool:
    return any(selector == "[data-ground]"
               or (_GROUND.match(selector) and _GROUND.match(selector).group(1) == ground)
               for selector in selectors)


def environment(blocks: list[Block], theme: str, ground: str | None) -> dict[str, str]:
    """Every custom property in force on `ground` under `theme`."""
    values: dict[str, str] = {}
    for selectors, declarations in blocks:
        if _applies_at_root(selectors, theme):
            values.update(declarations)
    if ground is not None:
        for selectors, declarations in blocks:
            if _applies_on_ground(selectors, ground):
                values.update(declarations)
    return values


def resolve(name: str, values: dict[str, str], seen: frozenset[str] = frozenset()) -> str | None:
    """A token's value with every var() substituted, or None if it cannot be.

    A cycle returns None rather than raising, because an unresolvable token is
    something the caller reports alongside the rest of its findings.
    """
    if name in seen or len(seen) > _MAX_LINKS:
        return None
    value = values.get(name)
    if value is None:
        return None
    return _substitute(value, values, seen | {name})


def _substitute(value: str, values: dict[str, str], seen: frozenset[str]) -> str | None:
    while (match := _VAR.search(value)) is not None:
        referenced = resolve(match.group(1), values, seen)
        if referenced is None:
            referenced = (match.group(2) or "").strip()
            if not referenced:
                return None
        value = value[:match.start()] + referenced + value[match.end():]
    return value.strip()
