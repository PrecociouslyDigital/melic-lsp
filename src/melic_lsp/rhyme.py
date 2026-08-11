"""End-rhyme detection, using only cached word data — no Text, no metrical parse.

Prosodic's own calibration counts perfect and slant as rhyme and leaves assonance
out: including it buys almost no extra recall for three times the false positives.
We follow that, so a label here means the two lines really do chime.
"""

from __future__ import annotations

from string import ascii_lowercase

from . import prosody
from .chordpro import Lyric
from .types import Ready, Syllabified

UNRHYMED = "·"


def _ending(line: Lyric, lang: str) -> Syllabified | None:
    """The line's last word, which is what an end-rhyme is made of."""
    words = line.words()
    if not words:
        return None
    result = prosody.syllabify(words[-1].token, lang)
    return result.value.syllables if isinstance(result, Ready) else None


def chimes(first: Syllabified, second: Syllabified) -> bool:
    """Whether two endings sound alike for the purpose of a scheme.

    Prosodic reports that a word does not rhyme with itself, which is right about
    rhyme and wrong about songs: a refrain that ends "home" every time is still the
    same slot in the pattern. A repeated ending counts here.
    """
    if first.token.casefold() == second.token.casefold():
        return True
    return prosody.rhymes(first, second)


def scheme(lines: list[Lyric], lang: str = "en") -> dict[int, str]:
    """Label the lines that chime, so a repeated letter means those lines rhyme.

    Letters are handed out in first-appearance order, giving the familiar ABAB.
    Lines that chime with nothing are simply absent: an annotation on every line
    saying "this one is unlike the others" would be noise on most of them.
    """
    groups: list[list[int]] = []
    representatives: list[Syllabified] = []

    for line in lines:
        ending = _ending(line, lang)
        if ending is None:
            continue
        for index, representative in enumerate(representatives):
            if chimes(ending, representative):
                groups[index].append(line.row)
                break
        else:
            groups.append([line.row])
            representatives.append(ending)

    letters = iter(ascii_lowercase)
    return {
        row: letter
        for group in groups
        if len(group) > 1
        for letter in [next(letters, "?")]
        for row in group
    }
