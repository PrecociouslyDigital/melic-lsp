"""The vocabulary shared by every module: coordinate spaces, stress, syllables.

The three coordinate spaces are the reason this file exists. Every position bug in
a project like this is the same bug — an integer used in the wrong space — so the
spaces are distinct types and each hop between them has exactly one bridge.

    WordCol  --WordSpan.lyric_col-->  LyricCol  --SpanMap.to_source-->  SrcCol

Prosodic reports syllable offsets in word space. Chords are stripped in lyric space.
The editor draws in source space. Skipping a hop is a type error, not a highlight
that lands one character to the left.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NewType, Sequence

# --- The three coordinate spaces ---------------------------------------------

SrcCol = NewType("SrcCol", int)
"""A column in the document line exactly as typed, chords included."""

LyricCol = NewType("LyricCol", int)
"""A column in the line with every [chord] token removed."""

WordCol = NewType("WordCol", int)
"""An offset within a single token, which is the space prosodic speaks."""


@dataclass(frozen=True)
class SrcRange:
    """A half-open column range within one source line."""

    start: SrcCol
    end: SrcCol


# --- Lyric space -> source space ---------------------------------------------


@dataclass(frozen=True)
class Span:
    """One run of lyric text that survived chord stripping."""

    lyric: LyricCol
    source: SrcCol
    length: int


@dataclass(frozen=True)
class SpanMap:
    """The only way out of lyric space.

    A chord may interrupt a word, so one lyric range can map to several source
    ranges: in ``chari[D]ot`` the lyric word is ``chariot`` and its final syllable
    straddles the chord. Callers get a list and are expected to handle all of it —
    semantic tokens emit one token per range, and a syllable a chord lands inside is
    marked from the first range's start to the last one's end.
    """

    spans: tuple[Span, ...]

    def to_source(self, start: LyricCol, end: LyricCol) -> list[SrcRange]:
        """Map a half-open lyric range onto the source runs that carry it."""
        out: list[SrcRange] = []
        for span in self.spans:
            lo = max(start, span.lyric)
            hi = min(end, span.lyric + span.length)
            if lo < hi:
                offset = span.source + (lo - span.lyric)
                out.append(SrcRange(SrcCol(offset), SrcCol(offset + hi - lo)))
        return out

    def to_lyric(self, column: SrcCol) -> LyricCol | None:
        """Map a source column back into lyric space, for "what is under the cursor".

        Returns None inside a chord token, which has no lyric column because it is
        not sung — the caller should treat that as a hover on the chord instead.
        """
        for span in self.spans:
            if span.source <= column < span.source + span.length:
                return LyricCol(span.lyric + (column - span.source))
        return None


# --- Word space -> lyric space -----------------------------------------------


@dataclass(frozen=True)
class WordSpan:
    """A token located in lyric space; the only way out of word space."""

    token: str
    start: LyricCol

    def lyric_col(self, offset: WordCol) -> LyricCol:
        return LyricCol(self.start + offset)

    @property
    def end(self) -> LyricCol:
        return LyricCol(self.start + len(self.token))


# --- Stress ------------------------------------------------------------------


class Stress(Enum):
    """Carries its own glyph so the signature format lives in one place."""

    PRIMARY = "+"
    SECONDARY = "^"
    NONE = "-"

    @classmethod
    def parse(cls, code: str) -> Stress:
        """Parse prosodic's 'P'/'S'/'U'. Anything unexpected reads as unstressed."""
        return {"P": cls.PRIMARY, "S": cls.SECONDARY}.get(code, cls.NONE)


# --- Syllables ---------------------------------------------------------------


@dataclass(frozen=True)
class RawSyllable:
    """A syllable as prosodic reports it, before we know where it sits."""

    text: str
    ipa: str
    stress: Stress


@dataclass(frozen=True)
class Syllable(RawSyllable):
    """A syllable that knows its place within its token."""

    start: WordCol

    @property
    def end(self) -> WordCol:
        return WordCol(self.start + len(self.text))


@dataclass(frozen=True)
class Tiled:
    """Syllables that provably tile their token, so their offsets are sound.

    Holding one of these *means* the offsets were checked. There is no assert to
    forget at a call site because the unchecked value is not constructible.
    """

    token: str
    syllables: tuple[Syllable, ...]


@dataclass(frozen=True)
class WholeWord:
    """Syllables that do not tile their token — the honest degraded case.

    Numerals ("3" -> "three") and some espeak output do not partition the token, so
    no syllable can be placed on a character. The count and the stress pattern are
    still true, which is why they are kept: the signature stays correct while
    highlighting steps back to the whole token. Callers that want positions have to
    say what they do here, because this type simply has none to offer.
    """

    token: str
    syllables: tuple[RawSyllable, ...]


type Syllabified = Tiled | WholeWord
"""Both cases expose ``.syllables`` with a ``.stress``, so counting and signature
rendering work on either without a match; only positions need the distinction."""


def tile(token: str, parts: Sequence[RawSyllable]) -> Syllabified:
    """Smart constructor: place syllables on the token, or admit that we cannot.

    Prosodic guarantees syllable texts join back to the token, so cumulative
    lengths are enough to locate each one. We compare lengths rather than text
    because the g2p path skips ``fix_recasing`` and may hand back a lowercased
    token that is still a correct partition.
    """
    if not parts or sum(len(p.text) for p in parts) != len(token):
        return WholeWord(token, tuple(parts))

    placed: list[Syllable] = []
    cursor = 0
    for part in parts:
        placed.append(Syllable(part.text, part.ipa, part.stress, WordCol(cursor)))
        cursor += len(part.text)
    return Tiled(token, tuple(placed))


# --- Tier state --------------------------------------------------------------


@dataclass(frozen=True)
class Ready[T]:
    value: T


@dataclass(frozen=True)
class Warming:
    """Tier 0 has not finished importing prosodic and loading the dictionary."""


@dataclass(frozen=True)
class Unavailable:
    """Prosodic cannot answer for this input — usually an OOV word with no espeak."""

    reason: str


type Analysis[T] = Ready[T] | Warming | Unavailable
"""Kept distinct from an empty result so the UI never renders a confident ``0σ``
for a line that merely has not been analysed yet."""
