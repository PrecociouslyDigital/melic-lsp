"""ChordPro parsing and position mapping. No prosodic, no LSP, no I/O.

This module owns the highest-risk code in the project — turning ``chari[D]ot`` into
syllable ranges that land on the right characters — and it is deliberately isolated
so that risk is testable in milliseconds without loading a 2.75 MB dictionary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto

from .types import LyricCol, Span, SpanMap, SrcCol, SrcRange, WordSpan

# --- Directives --------------------------------------------------------------


class Category(Enum):
    META = auto()
    FORMATTING = auto()
    ENVIRONMENT = auto()
    FONT = auto()
    OUTPUT = auto()
    CUSTOM = auto()


class EnvKind(Enum):
    """Whether an environment's contents are lyrics we analyse."""

    LYRIC = auto()
    VERBATIM = auto()


class Value(Enum):
    NONE = auto()
    OPTIONAL = auto()
    REQUIRED = auto()


@dataclass(frozen=True)
class EnvRole:
    env: str
    kind: EnvKind
    opens: bool


@dataclass(frozen=True)
class DirectiveSpec:
    canonical: str
    aliases: tuple[str, ...]
    category: Category
    value: Value
    env: EnvRole | None = None

    @property
    def names(self) -> tuple[str, ...]:
        return (self.canonical, *self.aliases)


# Environments come in pairs, so one row describes both halves.
# (environment, start aliases, end aliases, kind)
_ENVIRONMENTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], EnvKind], ...] = (
    ("chorus", ("soc",), ("eoc",), EnvKind.LYRIC),
    ("verse", ("sov",), ("eov",), EnvKind.LYRIC),
    ("bridge", ("sob",), ("eob",), EnvKind.LYRIC),
    ("tab", ("sot",), ("eot",), EnvKind.VERBATIM),
    ("grid", ("sog",), ("eog",), EnvKind.VERBATIM),
    ("abc", (), (), EnvKind.VERBATIM),
    ("ly", (), (), EnvKind.VERBATIM),
    ("textblock", (), (), EnvKind.LYRIC),
)

# (canonical, aliases, category, takes a value?)
_SIMPLE: tuple[tuple[str, tuple[str, ...], Category, Value], ...] = (
    # Meta
    ("title", ("t",), Category.META, Value.REQUIRED),
    ("subtitle", ("st",), Category.META, Value.REQUIRED),
    ("artist", (), Category.META, Value.REQUIRED),
    ("composer", (), Category.META, Value.REQUIRED),
    ("lyricist", (), Category.META, Value.REQUIRED),
    ("copyright", (), Category.META, Value.REQUIRED),
    ("album", (), Category.META, Value.REQUIRED),
    ("year", (), Category.META, Value.REQUIRED),
    ("key", (), Category.META, Value.REQUIRED),
    ("time", (), Category.META, Value.REQUIRED),
    ("tempo", (), Category.META, Value.REQUIRED),
    ("duration", (), Category.META, Value.REQUIRED),
    ("capo", (), Category.META, Value.REQUIRED),
    ("meta", (), Category.META, Value.REQUIRED),
    ("sorttitle", (), Category.META, Value.REQUIRED),
    # Formatting
    ("comment", ("c",), Category.FORMATTING, Value.REQUIRED),
    ("comment_italic", ("ci",), Category.FORMATTING, Value.REQUIRED),
    ("comment_box", ("cb",), Category.FORMATTING, Value.REQUIRED),
    ("highlight", (), Category.FORMATTING, Value.REQUIRED),
    ("image", (), Category.FORMATTING, Value.REQUIRED),
    ("chorus", (), Category.FORMATTING, Value.OPTIONAL),
    # Chords
    ("define", (), Category.FORMATTING, Value.REQUIRED),
    ("chord", (), Category.FORMATTING, Value.REQUIRED),
    ("transpose", (), Category.FORMATTING, Value.OPTIONAL),
    ("chordfont", ("cf",), Category.FONT, Value.REQUIRED),
    ("chordsize", ("cs",), Category.FONT, Value.REQUIRED),
    ("chordcolour", ("chordcolor",), Category.FONT, Value.REQUIRED),
    # Fonts
    ("textfont", ("tf",), Category.FONT, Value.REQUIRED),
    ("textsize", ("ts",), Category.FONT, Value.REQUIRED),
    ("textcolour", ("textcolor",), Category.FONT, Value.REQUIRED),
    ("tabfont", (), Category.FONT, Value.REQUIRED),
    ("tabsize", (), Category.FONT, Value.REQUIRED),
    ("tabcolour", ("tabcolor",), Category.FONT, Value.REQUIRED),
    ("gridfont", (), Category.FONT, Value.REQUIRED),
    ("gridsize", (), Category.FONT, Value.REQUIRED),
    ("gridcolour", ("gridcolor",), Category.FONT, Value.REQUIRED),
    ("footerfont", (), Category.FONT, Value.REQUIRED),
    ("titlefont", (), Category.FONT, Value.REQUIRED),
    # Output
    ("new_page", ("np",), Category.OUTPUT, Value.NONE),
    ("new_physical_page", ("npp",), Category.OUTPUT, Value.NONE),
    ("column_break", ("colb",), Category.OUTPUT, Value.NONE),
    ("columns", ("col",), Category.OUTPUT, Value.REQUIRED),
    ("new_song", ("ns",), Category.OUTPUT, Value.NONE),
    ("pagetype", (), Category.OUTPUT, Value.REQUIRED),
    ("titles", (), Category.OUTPUT, Value.REQUIRED),
    ("grid", ("g",), Category.OUTPUT, Value.OPTIONAL),
    ("no_grid", ("ng",), Category.OUTPUT, Value.OPTIONAL),
    # Ours. Registered rather than left to the generic x_ rule so they get real
    # hover documentation and turn up in did-you-mean suggestions.
    ("x_melic_word", (), Category.CUSTOM, Value.REQUIRED),
    ("x_melic_word_section", (), Category.CUSTOM, Value.REQUIRED),
    ("x_melic_word_line", (), Category.CUSTOM, Value.REQUIRED),
)


def _build_directives() -> dict[str, DirectiveSpec]:
    specs: list[DirectiveSpec] = [
        DirectiveSpec(name, aliases, category, value)
        for name, aliases, category, value in _SIMPLE
    ]
    for env, start_aliases, end_aliases, kind in _ENVIRONMENTS:
        specs.append(
            DirectiveSpec(
                f"start_of_{env}",
                start_aliases,
                Category.ENVIRONMENT,
                # {start_of_verse: Verse 1} names the section.
                Value.OPTIONAL,
                EnvRole(env, kind, opens=True),
            )
        )
        specs.append(
            DirectiveSpec(
                f"end_of_{env}",
                end_aliases,
                Category.ENVIRONMENT,
                Value.NONE,
                EnvRole(env, kind, opens=False),
            )
        )
    return {name: spec for spec in specs for name in spec.names}


DIRECTIVES: dict[str, DirectiveSpec] = _build_directives()


def lookup(name: str) -> DirectiveSpec | None:
    """Resolve a directive name or alias. ``x_*`` is reserved for custom use.

    The table is consulted first: our own ``x_melic_*`` directives are registered
    there, and the generic ``x_`` rule would otherwise shadow them with a
    documentation-free stub.
    """
    key = name.strip().lower()
    known = DIRECTIVES.get(key)
    if known is not None:
        return known
    if key.startswith("x_"):
        return DirectiveSpec(key, (), Category.CUSTOM, Value.OPTIONAL)
    return None


# --- Line kinds --------------------------------------------------------------


@dataclass(frozen=True)
class Chord:
    """A ``[chord]`` token: where it was typed, and the syllable it lands on."""

    name: str
    source: SrcRange
    """Covers the brackets too, so the whole token can be highlighted."""
    lyric: LyricCol
    """The lyric column the chord precedes — its onset."""


@dataclass(frozen=True)
class _Located:
    row: int
    text: str


@dataclass(frozen=True)
class Blank(_Located):
    pass


@dataclass(frozen=True)
class Comment(_Located):
    """A ``#`` line: not rendered by ChordPro, not analysed by us."""


@dataclass(frozen=True)
class Directive(_Located):
    name: str
    value: str | None
    spec: DirectiveSpec | None
    """None when the directive is unknown — diagnostics suggest a near match."""
    name_range: SrcRange
    closed: bool
    """False when the closing brace is missing."""


@dataclass(frozen=True)
class Verbatim(_Located):
    """A line inside a tab, grid, abc or ly environment.

    Excluded from analysis structurally rather than by a check someone forgets:
    it simply is not a ``Lyric`` and so never reaches the analyser.
    """

    env: str


@dataclass(frozen=True)
class Lyric(_Located):
    lyric: str
    spans: SpanMap
    chords: tuple[Chord, ...]
    unclosed: SrcCol | None = None
    """Where a '[' was opened and never closed, so the rest reads as literal text."""

    def words(self) -> list[WordSpan]:
        """Tokens of the chord-free lyric, located in lyric space."""
        return [
            WordSpan(m.group(), LyricCol(m.start()))
            for m in _WORD.finditer(self.lyric)
        ]


type Line = Blank | Comment | Directive | Verbatim | Lyric

# Letters or digits, allowing internal apostrophes and hyphens plus a trailing
# apostrophe, so "don't", "runnin'" and "augustus'" each stay one token.
_WORD = re.compile(r"\w+(?:['’-]\w+)*['’]?")


# --- Parsing -----------------------------------------------------------------


@dataclass(frozen=True)
class EnvProblem:
    """An environment that never closed, or a close with nothing open."""

    row: int
    env: str
    opened: bool


@dataclass(frozen=True)
class Document:
    lines: tuple[Line, ...]
    problems: tuple[EnvProblem, ...]

    def lyrics(self) -> list[Lyric]:
        return [line for line in self.lines if isinstance(line, Lyric)]


_DIRECTIVE = re.compile(r"^\s*\{\s*([^:}]*?)\s*(?::\s*(.*?))?\s*(\})?\s*$")

# Deliberately not str.splitlines(), which also breaks on \v, \f, \x1c-\x1e, \x85,
# U+2028 and U+2029. Editors break only on these three, and a row index that
# disagrees with the editor's silently misplaces every annotation below it.
_NEWLINE = re.compile(r"\r\n|\r|\n")


def parse_document(text: str) -> Document:
    """Classify every line, tracking environments so verbatim blocks are excluded."""
    lines: list[Line] = []
    problems: list[EnvProblem] = []
    stack: list[tuple[int, EnvRole]] = []

    for row, raw in enumerate(_NEWLINE.split(text)):
        line = _classify(row, raw, verbatim_env=_innermost_verbatim(stack))
        if isinstance(line, Directive) and line.spec is not None:
            role = line.spec.env
            if role is not None and role.opens:
                stack.append((row, role))
            elif role is not None:
                if stack and stack[-1][1].env == role.env:
                    stack.pop()
                else:
                    problems.append(EnvProblem(row, role.env, opened=False))
        lines.append(line)

    problems.extend(EnvProblem(row, role.env, opened=True) for row, role in stack)
    return Document(tuple(lines), tuple(problems))


def _innermost_verbatim(stack: list[tuple[int, EnvRole]]) -> str | None:
    for _, role in reversed(stack):
        if role.kind is EnvKind.VERBATIM:
            return role.env
    return None


def _classify(row: int, raw: str, verbatim_env: str | None) -> Line:
    stripped = raw.strip()
    if not stripped:
        return Blank(row, raw)
    if stripped.startswith("#"):
        return Comment(row, raw)
    if stripped.startswith("{"):
        return _parse_directive(row, raw)
    if verbatim_env is not None:
        return Verbatim(row, raw, verbatim_env)
    return parse_lyric(row, raw)


def _parse_directive(row: int, raw: str) -> Line:
    match = _DIRECTIVE.match(raw)
    if match is None:
        # A '{' that does not form a directive at all; treat the text as lyrics so
        # the line still gets analysed, and let diagnostics flag the brace.
        return parse_lyric(row, raw)
    name, value, brace = match.group(1), match.group(2), match.group(3)
    start = raw.index("{") + 1
    offset = start + (len(raw[start:]) - len(raw[start:].lstrip()))
    return Directive(
        row,
        raw,
        name.lower(),
        value,
        lookup(name),
        SrcRange(SrcCol(offset), SrcCol(offset + len(name))),
        closed=brace is not None,
    )


def parse_lyric(row: int, raw: str) -> Lyric:
    """Split a lyric line into its chords and the text between them.

    The spans are what make position mapping reversible: each records where a run
    of surviving text sits in both lyric and source space, so a lyric range can
    always be projected back onto the characters the user actually typed.
    """
    spans: list[Span] = []
    chords: list[Chord] = []
    parts: list[str] = []
    lyric_len = 0
    pos = 0
    unclosed: SrcCol | None = None

    def keep(run_start: int, run_end: int) -> None:
        nonlocal lyric_len
        if run_end > run_start:
            spans.append(
                Span(LyricCol(lyric_len), SrcCol(run_start), run_end - run_start)
            )
            parts.append(raw[run_start:run_end])
            lyric_len += run_end - run_start

    while pos < len(raw):
        open_at = raw.find("[", pos)
        if open_at == -1:
            keep(pos, len(raw))
            break
        close_at = raw.find("]", open_at)
        if close_at == -1:
            # Unclosed '[': the rest is literal text. Diagnostics flag the bracket.
            unclosed = SrcCol(open_at)
            keep(pos, len(raw))
            break
        keep(pos, open_at)
        chords.append(
            Chord(
                raw[open_at + 1 : close_at],
                SrcRange(SrcCol(open_at), SrcCol(close_at + 1)),
                LyricCol(lyric_len),
            )
        )
        pos = close_at + 1

    return Lyric(
        row, raw, "".join(parts), SpanMap(tuple(spans)), tuple(chords), unclosed
    )
