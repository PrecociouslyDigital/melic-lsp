"""Renders a line's syllable count and stress pattern, grouped by chord.

    Swing [D]low, sweet [G]chari[D]ot,     6σ · + [D]++ [G]+- [D]-
    Comin' for to carry me [A7]home.       8σ · +---+-- [A7]+

``+`` primary, ``^`` secondary, ``-`` unstressed. The run before the first bracket
is sung before any chord. Grouping is the point: both lines above scan plausibly,
but one changes chord every couple of syllables while the other holds a single
chord for seven, and that is invisible in the plain text.
"""

from __future__ import annotations

from enum import Enum

from .analysis import LineAnalysis

SYLLABLE = "σ"
SEPARATOR = " · "
WARMING = "…"
INEXACT = "?"
"""Appended to the count when a word could not be pronounced, so a short count
reads as "at least this many" rather than as a confident total."""


class Mode(Enum):
    CHORD_GROUPED = "chord-grouped"
    FLAT = "flat"
    COUNT_ONLY = "count-only"
    OFF = "off"


def render(analysis: LineAnalysis, mode: Mode = Mode.CHORD_GROUPED) -> str:
    """Build the end-of-line signature. Empty string means "show nothing"."""
    if mode is Mode.OFF or not analysis.line.lyric.strip():
        return ""
    if analysis.warming:
        return WARMING
    if not analysis.syllables and not analysis.unresolved:
        return ""

    count = count_label(analysis)
    if mode is Mode.COUNT_ONLY:
        return count
    pattern = marks(analysis, mode)
    return f"{count}{SEPARATOR}{pattern}" if pattern else count


def count_label(analysis: LineAnalysis) -> str:
    """The syllable count, marked uncertain when a word could not be pronounced.

    A word we cannot say contributes no syllables, so the total is a floor rather
    than a count. Anywhere that shows the number must show that too, or a missing
    dictionary entry reads as a short line.
    """
    return f"{analysis.count}{SYLLABLE}{INEXACT if analysis.unresolved else ''}"


def marks(analysis: LineAnalysis, mode: Mode = Mode.CHORD_GROUPED) -> str:
    """The stress pattern alone, for panels that show the count in their own column."""
    if not analysis.syllables:
        return ""
    if mode is Mode.FLAT:
        return "".join(syllable.stress.value for syllable in analysis.syllables)
    return " ".join(
        group.marks if group.chord is None else f"[{group.chord.name}]{group.marks}"
        for group in analysis.groups()
    )
