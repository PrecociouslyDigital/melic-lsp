"""Manual annotations, so the tool can be told what it could not work out.

Inference is good but not right, and a songwriter knows how they sing a word. These
directives let the file say so:

    {x_melic_word: chariot = +cha -ri -ot}          the whole document
    {x_melic_word_section: fire = +fi -re}          the enclosing section
    {x_melic_word_line: fire = +fire}               the next lyric line

Precedence runs line, then section, then document, then anything inferred.

A song can also declare the shape it means to have:

    {x_melic_scheme: ABAB}                          the enclosing section
    {x_melic_scheme: chorus = ABAB}                 every chorus in the song

That one is an expectation rather than a correction: it tells the solver which
near rhymes the song is reaching for, and gives the hints something to hold a stanza
to. It cannot make two words rhyme that do not.

No prosodic here — this is parsing and scoping only, so it stays fast to test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

from .chordpro import Directive, Document, Lyric
from .rhyme import canonical_pattern
from .sections import Section
from .types import Stress

DOCUMENT = "x_melic_word"
SECTION = "x_melic_word_section"
LINE = "x_melic_word_line"
SCHEME = "x_melic_scheme"

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
class SchemeDeclaration:
    """A rhyme pattern the file declares, and the line that declared it."""

    pattern: str
    row: int
    """So a hint can point back at the declaration it is holding the stanza to."""


@dataclass(frozen=True)
class Problem:
    row: int
    message: str


@dataclass(frozen=True)
class Overrides:
    scoped: dict[int, dict[str, Override]]
    """Lyric row -> overrides, with line beating section already resolved."""
    document: dict[str, Override]
    schemes: dict[int, SchemeDeclaration]
    """Stanza start row -> the pattern declared for it. Keyed by stanza because that
    is the scope a scheme is measured in, whatever the declaration was written on."""
    problems: tuple[Problem, ...]

    def find(self, token: str, row: int) -> Override | None:
        key = token.casefold()
        nearby = self.scoped.get(row)
        if nearby is not None and key in nearby:
            return nearby[key]
        return self.document.get(key)

    @property
    def empty(self) -> bool:
        return not self.scoped and not self.document and not self.schemes


EMPTY = Overrides({}, {}, {}, ())


def collect(document: Document, sections: Sequence[Section]) -> Overrides:
    """Read every annotation in a document and work out what each one covers."""
    by_row: dict[int, dict[str, Override]] = {}
    globals_: dict[str, Override] = {}
    problems: list[Problem] = []

    # Section overrides first, so a line-scoped one written inside a section wins.
    for scope in (Scope.SECTION, Scope.LINE):
        for row, payload in _annotations(document, _NAMES[scope]):
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

    for row, payload in _annotations(document, _NAMES[Scope.DOCUMENT]):
        parsed = _parse(row, payload)
        if isinstance(parsed, Problem):
            problems.append(parsed)
        else:
            globals_[parsed.token] = parsed

    schemes, declared = _schemes(document, sections)
    problems.extend(declared)

    return Overrides(by_row, globals_, schemes, tuple(problems))


_NAMES = {Scope.DOCUMENT: DOCUMENT, Scope.SECTION: SECTION, Scope.LINE: LINE}


def _annotations(document: Document, name: str) -> list[tuple[int, str]]:
    """Find the annotations of one directive, as (row, payload).

    **This is the swappable part.** Everything else works on payload strings, so
    moving annotations out of ``x_`` directives — into ``#`` comments, say, which
    ChordPro renderers drop rather than display — means changing this function and
    nothing else.
    """
    return [
        (line.row, line.value or "")
        for line in document.lines
        if isinstance(line, Directive) and line.name == name
    ]


def _rows_covered(
    scope: Scope, row: int, document: Document, sections: Sequence[Section]
) -> list[int]:
    if scope is Scope.LINE:
        following = [line.row for line in document.lyrics() if line.row > row]
        return following[:1]
    return [
        line.row for section in _sections_covered(row, sections) for line in section.lines
    ]


def _sections_covered(row: int, sections: Sequence[Section]) -> list[Section]:
    """The section an annotation written at this row speaks for, if any.

    The enclosing one — or, written between sections, the next one, which is what
    "this verse" means when you write it on the line above the verse.
    """
    enclosing = [s for s in sections if s.start_row <= row <= s.end_row]
    if enclosing:
        return enclosing[:1]
    later = [s for s in sections if s.start_row > row]
    return later[:1]


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


# --- Declared rhyme schemes ---------------------------------------------------


def _schemes(
    document: Document, sections: Sequence[Section]
) -> tuple[dict[int, SchemeDeclaration], list[Problem]]:
    """Resolve every ``{x_melic_scheme}`` to the stanzas it speaks for.

    A declaration covers a section — or every section of a kind, written
    ``chorus = ABAB`` — but it lands on *stanzas*, since a stanza is what a scheme
    is measured over. Only stanzas of the pattern's own length are covered: holding
    a six-line stanza to a four-letter pattern would compare two things that were
    never the same shape, and the sibling stanza it would otherwise be measured
    against is the better reference anyway.
    """
    found: dict[int, SchemeDeclaration] = {}
    problems: list[Problem] = []

    for row, payload in _annotations(document, SCHEME):
        parsed = _parse_scheme(row, payload)
        if isinstance(parsed, Problem):
            problems.append(parsed)
            continue
        kind, pattern = parsed
        covered = (
            [section for section in sections if section.kind == kind]
            if kind is not None
            else _sections_covered(row, sections)
        )
        stanzas = [
            stanza
            for section in covered
            for stanza in section.stanzas
            if len(stanza.lines) == len(pattern)
        ]
        if not stanzas:
            where = f"any {kind} section" if kind is not None else "this section"
            problems.append(
                Problem(
                    row,
                    f"No {len(pattern)}-line stanza in {where} to hold to '{pattern}'.",
                )
            )
            continue
        for stanza in stanzas:
            found[stanza.start_row] = SchemeDeclaration(pattern, row)

    return found, problems


def _parse_scheme(row: int, payload: str) -> tuple[str | None, str] | Problem:
    """Parse ``ABAB``, or ``chorus = ABAB``, into the kind it targets and the shape.

    The two forms mirror the word grammar's ``name = value``; without an ``=`` the
    declaration speaks for the section it was written in.
    """
    target, separator, rest = payload.partition("=")
    kind = target.strip().lower() if separator else None
    pattern = canonical_pattern((rest if separator else target).strip())
    if pattern is None or kind == "":
        return Problem(
            row,
            "Expected a rhyme pattern like 'ABAB', or 'chorus = ABAB' to give every "
            "chorus the same one. X marks a line that rhymes with nothing.",
        )
    return kind, pattern
