"""Colour parsing, alpha compositing, and the WCAG 2.1 contrast ratio.

Standard library only. Anything a volunteer has to install to run the theme
check is a reason the theme check stops being run, so there is nothing here but
arithmetic.

The formulas are from Web Content Accessibility Guidelines 2.1, W3C
Recommendation 05 June 2018:

  relative luminance   https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
  contrast ratio       https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# WCAG 2.1 success criterion 1.4.3, Contrast (Minimum), for text below 18 point
# or 14 point bold. Large text is allowed 3.0, and none of the status inks in
# this theme are large text, so the theme is held to the stricter number.
MINIMUM_RATIO = 4.5

# The knee in the sRGB transfer function, and its two branches, quoted from the
# relative luminance definition rather than from any implementation of it.
_KNEE = 0.03928
_LINEAR_DIVISOR = 12.92
_GAMMA_OFFSET = 0.055
_GAMMA_DIVISOR = 1.055
_GAMMA_EXPONENT = 2.4

_COEFFICIENTS = (0.2126, 0.7152, 0.0722)

# The ratio is (lighter + 0.05) / (darker + 0.05). The 0.05 stands for ambient
# light reflecting off the screen, so two blacks do not divide by zero.
_AMBIENT = 0.05

# Only the named colours the GANTRY token layer actually uses. A full CSS
# colour table would be 148 names nobody in this repository writes.
_NAMED = {
    "transparent": (0, 0, 0, 0.0),
    "black": (0, 0, 0, 1.0),
    "white": (255, 255, 255, 1.0),
}

_HEX = re.compile(r"^#([0-9a-fA-F]{3,8})$")
_FUNCTIONAL = re.compile(r"^rgba?\(([^()]*)\)$")


@dataclass(frozen=True)
class Colour:
    red: int
    green: int
    blue: int
    alpha: float

    def __str__(self) -> str:
        if self.alpha >= 1.0:
            return f"#{self.red:02x}{self.green:02x}{self.blue:02x}"
        return f"rgba({self.red}, {self.green}, {self.blue}, {self.alpha:g})"


def _from_hex(digits: str) -> Colour | None:
    if len(digits) in (3, 4):
        digits = "".join(ch * 2 for ch in digits)
    if len(digits) not in (6, 8):
        return None
    channels = [int(digits[i:i + 2], 16) for i in range(0, len(digits), 2)]
    alpha = channels[3] / 255 if len(channels) == 4 else 1.0
    return Colour(channels[0], channels[1], channels[2], alpha)


def _from_functional(body: str) -> Colour | None:
    parts = [p for p in re.split(r"[,/\s]+", body.strip()) if p]
    if len(parts) not in (3, 4):
        return None
    try:
        channels = [int(round(float(p))) for p in parts[:3]]
        alpha = float(parts[3]) if len(parts) == 4 else 1.0
    except ValueError:
        return None
    if any(c < 0 or c > 255 for c in channels) or not 0.0 <= alpha <= 1.0:
        return None
    return Colour(channels[0], channels[1], channels[2], alpha)


def parse_colour(value: str) -> Colour | None:
    """A CSS colour, or None when the value is not a colour at all.

    Returning None rather than raising is deliberate: the token file holds
    lengths, shadows, and clamp() expressions under the same custom property
    syntax, and the caller decides which of those are worth complaining about.
    """
    text = value.strip().lower()
    if text in _NAMED:
        return Colour(*_NAMED[text])
    hex_match = _HEX.match(text)
    if hex_match:
        return _from_hex(hex_match.group(1))
    functional = _FUNCTIONAL.match(text)
    if functional:
        return _from_functional(functional.group(1))
    return None


def _to_linear(channel: int) -> float:
    proportion = channel / 255
    if proportion <= _KNEE:
        return proportion / _LINEAR_DIVISOR
    return ((proportion + _GAMMA_OFFSET) / _GAMMA_DIVISOR) ** _GAMMA_EXPONENT


def relative_luminance(colour: Colour) -> float:
    channels = (colour.red, colour.green, colour.blue)
    return sum(weight * _to_linear(channel)
               for weight, channel in zip(_COEFFICIENTS, channels))


def composite(front: Colour, back: Colour) -> Colour:
    """Lay a translucent colour over an opaque one, the way a browser paints it.

    Without this a line drawn as rgba over the ground reports the ratio of a
    colour that is never on screen.
    """
    if front.alpha >= 1.0:
        return front
    weight = front.alpha
    mixed = [int(round(weight * f + (1 - weight) * b))
             for f, b in ((front.red, back.red),
                          (front.green, back.green),
                          (front.blue, back.blue))]
    return Colour(mixed[0], mixed[1], mixed[2], 1.0)


def contrast_ratio(one: Colour, other: Colour) -> float:
    first = relative_luminance(one)
    second = relative_luminance(other)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + _AMBIENT) / (darker + _AMBIENT)
