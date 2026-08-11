"""Joins parsing to prosody: a lyric line becomes located, stressed syllables.

Analysis is per word and never all-or-nothing. One invented word the dictionary has
never seen should cost you that word's highlighting, not the whole line's signature,
so unresolved tokens are carried alongside the results rather than replacing them.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import assert_never

from . import prosody
from .chordpro import Chord, Document, Lyric, parse_document
from .rhyme import scheme
from .sections import Section, group
from .types import (
    LyricCol,
    Ready,
    Stress,
    Syllabified,
    Tiled,
    Unavailable,
    Warming,
    WholeWord,
    WordSpan,
)


@dataclass(frozen=True)
class PlacedSyllable:
    """A syllable in lyric space, ready to be projected onto the source."""

    text: str
    ipa: str
    stress: Stress
    start: LyricCol
    end: LyricCol
    exact: bool
    """False when the syllable could not be tiled onto the token, in which case
    start/end cover the whole word and only the count and stress are trustworthy."""


@dataclass(frozen=True)
class Unresolved:
    """A token prosodic could not pronounce, and why."""

    span: WordSpan
    reason: str


@dataclass(frozen=True)
class ChordGroup:
    """The syllables one chord covers. ``chord is None`` is the run sung before any."""

    chord: Chord | None
    syllables: tuple[PlacedSyllable, ...]

    @property
    def marks(self) -> str:
        return "".join(syllable.stress.value for syllable in self.syllables)


@dataclass(frozen=True)
class LineAnalysis:
    line: Lyric
    syllables: tuple[PlacedSyllable, ...]
    unresolved: tuple[Unresolved, ...]
    warming: bool
    guessed: tuple[WordSpan, ...] = ()
    """Words espeak guessed rather than looked up; worth a hint, not a warning."""
    """True when tier 0 had not finished; the counts below are not yet meaningful."""

    @property
    def count(self) -> int:
        return len(self.syllables)

    @property
    def complete(self) -> bool:
        return not self.warming and not self.unresolved

    def groups(self) -> tuple[ChordGroup, ...]:
        """Syllables split by the chord governing each — the shape every view wants.

        A syllable belongs to the last chord starting at or before it. Chords with
        nothing under them are kept: a chord change with no syllable to sing on is
        exactly the sort of thing worth seeing.
        """
        onsets = [chord.lyric for chord in self.line.chords]
        buckets: list[list[PlacedSyllable]] = [[] for _ in range(len(onsets) + 1)]
        for syllable in self.syllables:
            buckets[bisect_right(onsets, syllable.start)].append(syllable)

        leading = [ChordGroup(None, tuple(buckets[0]))] if buckets[0] else []
        return tuple(
            leading
            + [
                ChordGroup(chord, tuple(buckets[index + 1]))
                for index, chord in enumerate(self.line.chords)
            ]
        )


@dataclass(frozen=True)
class DocumentAnalysis:
    """Everything the features need for one document, computed in one pass."""

    document: Document
    sections: tuple[Section, ...]
    lines: tuple[LineAnalysis, ...]
    rhymes: dict[int, str]
    """Row -> rhyme letter, scoped per section: a scheme is a property of a stanza."""

    def by_row(self, row: int) -> LineAnalysis | None:
        return next((line for line in self.lines if line.line.row == row), None)


def analyse_document(text: str, lang: str = "en", rhyming: bool = True) -> DocumentAnalysis:
    document = parse_document(text)
    found = group(document)
    labels: dict[int, str] = {}
    if rhyming:
        for section in found:
            labels.update(scheme(list(section.lines), lang))
    return DocumentAnalysis(
        document,
        tuple(found),
        tuple(analyse_line(line, lang) for line in document.lyrics()),
        labels,
    )


def analyse_line(line: Lyric, lang: str = "en") -> LineAnalysis:
    syllables: list[PlacedSyllable] = []
    unresolved: list[Unresolved] = []
    guessed: list[WordSpan] = []
    warming = False

    for span in line.words():
        match prosody.syllabify(span.token, lang):
            case Ready(word):
                syllables.extend(_place(span, word.syllables))
                if word.guessed:
                    guessed.append(span)
            case Unavailable(reason):
                unresolved.append(Unresolved(span, reason))
            case Warming():
                warming = True

    return LineAnalysis(
        line, tuple(syllables), tuple(unresolved), warming, tuple(guessed)
    )


def _place(span: WordSpan, syllabified: Syllabified) -> list[PlacedSyllable]:
    """Lift syllables from word space into lyric space, honestly.

    A ``WholeWord`` has no per-syllable offsets to lift, so every one of its
    syllables is given the whole token's extent and flagged inexact. The count and
    the stress pattern stay true, which is all the signature needs; only
    highlighting has to care about the difference.
    """
    match syllabified:
        case Tiled(syllables=syllables):
            return [
                PlacedSyllable(
                    syllable.text,
                    syllable.ipa,
                    syllable.stress,
                    span.lyric_col(syllable.start),
                    span.lyric_col(syllable.end),
                    exact=True,
                )
                for syllable in syllables
            ]
        case WholeWord(syllables=syllables):
            return [
                PlacedSyllable(
                    syllable.text,
                    syllable.ipa,
                    syllable.stress,
                    span.start,
                    span.end,
                    exact=False,
                )
                for syllable in syllables
            ]
    assert_never(syllabified)
