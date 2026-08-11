"""End-rhyme detection, using only cached word data — no Text, no metrical parse.

Prosodic's own calibration counts perfect and slant as rhyme and leaves assonance
out: including it buys almost no extra recall for three times the false positives.
We follow that, so a label here means the two lines really do chime.

How they chime is kept, not collapsed to a boolean: "B~" says the pairing is a slant
rhyme, "B=" that the line simply ends on the same word again.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from string import ascii_uppercase

from . import prosody
from .chordpro import Lyric
from .types import Ready, Syllabified

UNRHYMED = "X"
"""Stands in for a line that chimes with nothing, in a scheme string."""


class Chime(Enum):
    """How closely two endings sound alike."""

    PERFECT = ""
    """The clean case carries no mark; it is the default reading of a letter."""
    SLANT = "~"
    IDENTICAL = "="
    """The same word again. Rime riche, and in a refrain, usually the point."""


@dataclass(frozen=True)
class Rhyme:
    letter: str
    chime: Chime

    @property
    def label(self) -> str:
        """What the margin shows: "A", "A~", "A="."""
        return f"{self.letter}{self.chime.value}"


DESCRIPTION = {
    Chime.PERFECT: "perfect rhyme",
    Chime.SLANT: "slant rhyme",
    Chime.IDENTICAL: "the same word repeated",
}
"""The mark in words, for tooltips and hover — anywhere with room for more than a glyph."""


def _ending(line: Lyric, lang: str) -> Syllabified | None:
    """The line's last word, which is what an end-rhyme is made of."""
    words = line.words()
    if not words:
        return None
    result = prosody.syllabify(words[-1].token, lang)
    return result.value.syllables if isinstance(result, Ready) else None


def classify(first: Syllabified, second: Syllabified) -> Chime | None:
    """How two endings chime, or None if they do not.

    Prosodic reports that a word does not rhyme with itself, which is right about
    rhyme and wrong about songs: a refrain that ends "home" every time is still the
    same slot in the pattern. A repeated ending counts here, and says so.
    """
    if first.token.casefold() == second.token.casefold():
        return Chime.IDENTICAL
    match prosody.rhyme_type(first, second):
        case "perfect":
            return Chime.PERFECT
        case "slant":
            return Chime.SLANT
        case _:
            return None


def scheme(lines: list[Lyric], lang: str = "en") -> dict[int, Rhyme]:
    """Label the lines that chime, so a repeated letter means those lines rhyme.

    Letters are handed out in first-appearance order, giving the familiar ABAB.
    Lines that chime with nothing are simply absent: an annotation on every line
    saying "this one is unlike the others" would be noise on most of them.

    Quality is measured against the line that opened the group, which is the
    natural reference — it wears the bare letter, and every later member says how
    it relates to it.
    """
    groups: list[list[tuple[int, Chime]]] = []
    representatives: list[Syllabified] = []

    for line in lines:
        ending = _ending(line, lang)
        if ending is None:
            continue
        for index, representative in enumerate(representatives):
            chime = classify(ending, representative)
            if chime is not None:
                groups[index].append((line.row, chime))
                break
        else:
            groups.append([(line.row, Chime.PERFECT)])
            representatives.append(ending)

    letters = iter(ascii_uppercase)
    return {
        row: Rhyme(letter, chime)
        for group in groups
        if len(group) > 1
        for letter in [next(letters, "?")]
        for row, chime in group
    }


def scheme_string(lines: list[Lyric], labels: dict[int, Rhyme]) -> str:
    """The section's shape as the familiar ``ABAB``, or "" when nothing rhymes.

    The letters are the ones the margin shows, minus their quality marks: a slant
    rhyme still fills that slot, and ``ABAB`` is about shape.
    """
    if not any(line.row in labels for line in lines):
        return ""
    return "".join(
        labels[line.row].letter if line.row in labels else UNRHYMED
        for line in lines
    )
