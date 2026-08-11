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
from .rhyme import Rhyme

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


def render(analysis: LineAnalysis, mode: Mode, rhyme: Rhyme | None = None) -> str:
    """Build the end-of-line signature. Empty string means "show nothing".

    The mode is required: which one to show is a setting, and a default here could
    only ever drift from it. The rhyme is governed by its own setting, so it still
    shows with the signature turned off — that pairing is the shipped default.
    """
    if not analysis.line.lyric.strip():
        return ""
    if mode is Mode.OFF:
        return "" if analysis.warming or rhyme is None else rhyme.label
    if analysis.warming:
        return WARMING
    if not analysis.syllables and not analysis.unresolved:
        return ""

    count = count_label(analysis, rhyme)
    if mode is Mode.COUNT_ONLY:
        return count
    pattern = marks(analysis, mode)
    return f"{count}{SEPARATOR}{pattern}" if pattern else count


def count_label(
    analysis: LineAnalysis, rhyme: Rhyme | None = None, width: int = 0
) -> str:
    """The syllable count and its rhyme: "8σ", "8σ?", "6σ A=".

    A word we cannot say contributes no syllables, so the total is a floor rather
    than a count. Anywhere that shows the number must show that too, or a missing
    dictionary entry reads as a short line. The rhyme travels with it because the
    two are one label everywhere they appear — margin, outline and compare view.

    ``width`` right-aligns the count *alone*, so a column of these lines up on the
    σ even where only some of the lines rhyme. Padding the whole label instead
    would let a rhyme letter shove the number out of its column, and lining the
    numbers up is the only reason the panels exist.
    """
    count = f"{analysis.count}{SYLLABLE}{INEXACT if analysis.unresolved else ''}"
    return f"{count:>{width}} {rhyme.label}" if rhyme is not None else f"{count:>{width}}"


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
