"""Joins parsing to prosody: a lyric line becomes located, stressed syllables.

Analysis is per word and never all-or-nothing. One invented word the dictionary has
never seen should cost you that word's highlighting, not the whole line's signature,
so unresolved tokens are carried alongside the results rather than replacing them.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import assert_never

from . import prosody
from .chordpro import Chord, Document, Lyric, parse_document
from .overrides import EMPTY, Override, Overrides, collect
from .rhyme import Rhyme, scheme
from .sections import Section, group
from .types import (
    LyricCol,
    RawSyllable,
    Ready,
    Stress,
    Syllabified,
    Tiled,
    Unavailable,
    Warming,
    WholeWord,
    WordSpan,
    tile,
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
class Note:
    """Something worth mentioning about a word that is not an error."""

    span: WordSpan
    message: str


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
    overridden: tuple[WordSpan, ...] = ()
    """Words read from a manual annotation rather than inferred."""
    notes: tuple[Note, ...] = ()
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
    rhymes: dict[int, Rhyme]
    """Row -> rhyme, scoped per section: a scheme is a property of a stanza."""
    overrides: Overrides = EMPTY

    def by_row(self, row: int) -> LineAnalysis | None:
        return next((line for line in self.lines if line.line.row == row), None)


def analyse_document(
    text: str, lang: str = "en", rhyming: bool = True, chord_aware: bool = True
) -> DocumentAnalysis:
    document = parse_document(text)
    found = group(document)
    annotations = collect(document, found)
    labels: dict[int, Rhyme] = {}
    if rhyming:
        for section in found:
            labels.update(scheme(list(section.lines), lang))
    return DocumentAnalysis(
        document,
        tuple(found),
        tuple(
            analyse_line(line, lang, chord_aware, annotations)
            for line in document.lyrics()
        ),
        labels,
        annotations,
    )


def _splits(syllabified: Syllabified, start: LyricCol, onsets: Sequence[LyricCol]) -> int:
    """How many of this reading's syllables a chord lands inside.

    A chord at lyric column ``c`` interrupts syllable ``[s, e)`` exactly when
    ``s < c < e`` — strictly inside, so a chord sitting on a syllable boundary is
    the good case and counts for nothing.
    """
    if not isinstance(syllabified, Tiled):
        return 0
    return sum(
        1
        for syllable in syllabified.syllables
        for chord in onsets
        if start + syllable.start < chord < start + syllable.end
    )


def _read(
    word: prosody.Word, span: WordSpan, onsets: Sequence[LyricCol], chord_aware: bool
) -> Syllabified:
    """Pick the reading of a word that best fits where its chords fall.

    Prosodic offers several pronunciations and prefers one without knowing anything
    about the music. Where a chord interrupts a word, that placement is evidence
    about how the writer means to sing it: ``chari[D]ot`` says cha-ri-ot, because
    that is the reading where the chord change lands on a syllable rather than
    inside one. Ties keep prosodic's own order, so this only ever speaks up when
    the chords actually disagree with it.
    """
    if not chord_aware or len(word.variants) < 2:
        return word.syllables
    interior = [chord for chord in onsets if span.start < chord < span.end]
    if not interior:
        return word.syllables
    return min(word.variants, key=lambda v: _splits(v, span.start, interior))


def _apply(
    override: Override, word: prosody.Word | None
) -> tuple[Syllabified, str | None]:
    """Turn a hand-written reading into syllables, keeping stress honest.

    When no stress glyphs were written the intent is "fix the split, keep the
    stress", so we take it from whichever pronunciation has the same number of
    syllables. If none does there is nothing to inherit, and inventing a pattern —
    first-syllable-primary, say — would quietly mis-stress *away* and *guitar*. It
    reads as unstressed instead, and says so.
    """
    note: str | None = None
    stresses = override.stresses
    if stresses is None:
        match = next(
            (
                variant
                for variant in (word.variants if word else ())
                if len(variant.syllables) == len(override.texts)
            ),
            None,
        )
        if match is not None:
            stresses = tuple(syllable.stress for syllable in match.syllables)
        else:
            stresses = tuple(Stress.NONE for _ in override.texts)
            note = (
                f"No stress given for “{override.token}” and no "
                f"{len(override.texts)}-syllable pronunciation to take it from. "
                "Mark it with +, ^ or - to say."
            )

    parts = [
        RawSyllable(text, "", stress)
        for text, stress in zip(override.texts, stresses)
    ]
    # Validated at parse time to spell the token, so this always tiles.
    return tile("".join(override.texts), parts), note


def analyse_line(
    line: Lyric,
    lang: str = "en",
    chord_aware: bool = True,
    overrides: Overrides = EMPTY,
) -> LineAnalysis:
    syllables: list[PlacedSyllable] = []
    unresolved: list[Unresolved] = []
    overridden: list[WordSpan] = []
    notes: list[Note] = []
    warming = False

    onsets = [chord.lyric for chord in line.chords]
    for span in line.words():
        override = overrides.find(span.token, line.row)
        result = prosody.syllabify(span.token, lang)

        if override is not None:
            # A manual annotation wins outright: it is the one source here that
            # actually knows how the song goes.
            reading, note = _apply(override, result.value if isinstance(result, Ready) else None)
            syllables.extend(_place(span, reading))
            overridden.append(span)
            if note is not None:
                notes.append(Note(span, note))
            continue

        match result:
            case Ready(word):
                syllables.extend(_place(span, _read(word, span, onsets, chord_aware)))
            case Unavailable(reason):
                unresolved.append(Unresolved(span, reason))
            case Warming():
                warming = True

    return LineAnalysis(
        line,
        tuple(syllables),
        tuple(unresolved),
        warming,
        tuple(overridden),
        tuple(notes),
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
