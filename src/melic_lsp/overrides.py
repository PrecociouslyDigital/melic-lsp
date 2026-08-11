"""Manual syllable and stress annotations, so the tool can be told it is wrong.

Inference is good but not right, and a songwriter knows how they sing a word. These
directives let the file say so:

    {x_melic_word: chariot = +cha -ri -ot}          the whole document
    {x_melic_word_section: fire = +fi -re}          the enclosing section
    {x_melic_word_line: fire = +fire}               the next lyric line

Precedence runs line, then section, then document, then anything inferred.

No prosodic here — this is parsing and scoping only, so it stays fast to test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

from .chordpro import Directive, Document, Lyric
from .sections import Section
from .types import Stress

DOCUMENT = "x_melic_word"
SECTION = "x_melic_word_section"
LINE = "x_melic_word_line"

_GLYPHS = {stress.value: stress for stress in Stress}


class Scope(Enum):
    DOCUMENT = auto()
    SECTION = auto()
    LINE = auto()


@dataclass(frozen=True)
class Override:
    """One hand-written reading of a word."""

    token: str
    texts: tuple[str, ...]
    stresses: tuple[Stress, ...] | None
    """None when no glyphs were written, meaning "keep the stress, fix the split"."""
    row: int
    """Where it was declared, so hover and diagnostics can point back at it."""


@dataclass(frozen=True)
class Problem:
    row: int
    message: str


@dataclass(frozen=True)
class Overrides:
    scoped: dict[int, dict[str, Override]]
    """Lyric row -> overrides, with line beating section already resolved."""
    document: dict[str, Override]
    problems: tuple[Problem, ...]

    def find(self, token: str, row: int) -> Override | None:
        key = token.casefold()
        nearby = self.scoped.get(row)
        if nearby is not None and key in nearby:
            return nearby[key]
        return self.document.get(key)

    @property
    def empty(self) -> bool:
        return not self.scoped and not self.document


EMPTY = Overrides({}, {}, ())


def collect(document: Document, sections: Sequence[Section]) -> Overrides:
    """Read every annotation in a document and work out which rows each covers."""
    by_row: dict[int, dict[str, Override]] = {}
    globals_: dict[str, Override] = {}
    problems: list[Problem] = []

    # Section overrides first, so a line-scoped one written inside a section wins.
    for scope in (Scope.SECTION, Scope.LINE):
        for row, payload in _annotations(document, scope):
            parsed = _parse(row, payload)
            if isinstance(parsed, Problem):
                problems.append(parsed)
                continue
            covered = _rows_covered(scope, row, document, sections)
            if not covered:
                problems.append(
                    Problem(row, "This override covers no lyric line, so it does nothing.")
                )
                continue
            for target in covered:
                by_row.setdefault(target, {})[parsed.token] = parsed

    for row, payload in _annotations(document, Scope.DOCUMENT):
        parsed = _parse(row, payload)
        if isinstance(parsed, Problem):
            problems.append(parsed)
        else:
            globals_[parsed.token] = parsed

    return Overrides(by_row, globals_, tuple(problems))


def _annotations(document: Document, scope: Scope) -> list[tuple[int, str]]:
    """Find the annotations of one scope, as (row, payload).

    **This is the swappable part.** Everything else works on payload strings, so
    moving annotations out of ``x_`` directives — into ``#`` comments, say, which
    ChordPro renderers drop rather than display — means changing this function and
    nothing else.
    """
    wanted = {Scope.DOCUMENT: DOCUMENT, Scope.SECTION: SECTION, Scope.LINE: LINE}[scope]
    return [
        (line.row, line.value or "")
        for line in document.lines
        if isinstance(line, Directive) and line.name == wanted
    ]


def _rows_covered(
    scope: Scope, row: int, document: Document, sections: Sequence[Section]
) -> list[int]:
    if scope is Scope.LINE:
        following = [line.row for line in document.lyrics() if line.row > row]
        return following[:1]
    enclosing = [s for s in sections if s.start_row <= row <= s.end_row]
    if enclosing:
        return [line.row for line in enclosing[0].lines]
    # Declared between sections: take the next one, which is what "this verse"
    # means when you write it on the line above the verse.
    later = [s for s in sections if s.start_row > row]
    return [line.row for line in later[0].lines] if later else []


def _parse(row: int, payload: str) -> Override | Problem:
    """Parse ``token = +syl -syl`` into an override, or say why it will not."""
    token, separator, spelling = payload.partition("=")
    token = token.strip()
    if not separator or not token:
        return Problem(row, "Expected 'word = syl syl', e.g. 'chariot = +cha -ri -ot'.")

    texts: list[str] = []
    stresses: list[Stress] = []
    marked = False
    for part in spelling.split():
        stress = _GLYPHS.get(part[0])
        if stress is not None:
            marked = True
            part = part[1:]
        if not part:
            return Problem(row, f"A stress mark in '{token}' has no syllable after it.")
        texts.append(part)
        stresses.append(stress if stress is not None else Stress.NONE)

    if not texts:
        return Problem(row, f"No syllables given for '{token}'.")

    # Deliberately stricter than the tiling check used for prosodic's own output,
    # which only compares lengths. That is sound for a source guaranteed to
    # partition the token, but a hand-typed word of the right length and the wrong
    # letters would sail straight through it.
    if "".join(texts).casefold() != token.casefold():
        return Problem(
            row,
            f"'{' '.join(texts)}' spells '{''.join(texts)}', not '{token}'.",
        )

    return Override(
        token.casefold(), tuple(texts), tuple(stresses) if marked else None, row
    )
