"""Grouping lines into sections and stanzas, and lining parallel ones up.

Section, stanza, line. A ``{start_of_verse}`` holding four quatrains is four
stanzas, not a sixteen-line verse: a rhyme scheme measured across all four is
noise, because a scheme is a property of a stanza. Explicit environments name the
sections; failing those, blank lines mark stanzas, because most songs are written
without a single directive. Comparison is only ever between sections of the same
kind — verses against verses — since a chorus is not supposed to scan like a verse.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .chordpro import Blank, Directive, Document, EnvKind, Lyric, env_label

IMPLICIT = "stanza"


@dataclass(frozen=True)
class Stanza:
    """A run of lyric lines with no blank line in it. What a scheme measures."""

    lines: tuple[Lyric, ...]

    @property
    def start_row(self) -> int:
        return self.lines[0].row

    @property
    def end_row(self) -> int:
        return self.lines[-1].row


@dataclass(frozen=True)
class Section:
    kind: str
    """The environment name — "verse", "chorus", "intro" — or "stanza"."""
    label: str | None
    """Whatever ``{start_of_verse: Verse 1}`` named it."""
    stanzas: tuple[Stanza, ...]

    @property
    def lines(self) -> tuple[Lyric, ...]:
        """Every line in the section, for the things that want it whole."""
        return tuple(line for stanza in self.stanzas for line in stanza.lines)

    @property
    def title(self) -> str:
        return self.label or self.kind.capitalize()

    @property
    def start_row(self) -> int:
        return self.stanzas[0].start_row

    @property
    def end_row(self) -> int:
        return self.stanzas[-1].end_row


def group(document: Document) -> list[Section]:
    """Split a document into sections, explicit environments taking precedence.

    One rule covers both levels: a blank line ends the stanza, and outside an
    environment it ends the section as well. Outside one there is nothing else to
    go on, so an unmarked song is a run of single-stanza sections — exactly the
    shape it had before stanzas existed.
    """
    sections: list[Section] = []
    stanzas: list[Stanza] = []
    current: list[Lyric] = []
    env: tuple[str, str | None] | None = None

    def end_stanza() -> None:
        if current:
            stanzas.append(Stanza(tuple(current)))
            current.clear()

    def flush(kind: str, label: str | None) -> None:
        end_stanza()
        if stanzas:
            sections.append(Section(kind, label, tuple(stanzas)))
            stanzas.clear()

    for line in document.lines:
        match line:
            case Directive(spec=spec, value=value) if spec is not None and spec.env:
                role = spec.env
                if role.kind is not EnvKind.LYRIC:
                    continue
                flush(*(env or (IMPLICIT, None)))
                env = (role.env, env_label(value)) if role.opens else None
            case Blank():
                end_stanza()
                if env is None:
                    # Inside an environment the author already said where the
                    # section ends, and a blank is the break between its stanzas.
                    flush(IMPLICIT, None)
            case Lyric() if line.lyric.strip():
                current.append(line)
            case _:
                pass

    flush(*(env or (IMPLICIT, None)))
    return sections


@dataclass(frozen=True)
class Stack:
    """Every section of one kind, lined up so parallel lines sit above each other."""

    kind: str
    sections: tuple[Section, ...]

    @property
    def blocks(self) -> list[list[tuple[Lyric | None, ...]]]:
        """Rows aligned stanza by stanza, then line by line within each stanza.

        Aligning on the flat line index instead would compare a sixteen-line verse
        against an eight-line one by pairing line 1 with line 1 and drifting from
        there. Ragged tails are left ragged, as ``None``: a stanza with an extra
        line is exactly the divergence worth looking at, not something to pad away.
        """
        depth = max(len(section.stanzas) for section in self.sections)
        return [
            _aligned([_nth(section.stanzas, index) for section in self.sections])
            for index in range(depth)
        ]


def _nth(stanzas: tuple[Stanza, ...], index: int) -> tuple[Lyric, ...]:
    return stanzas[index].lines if index < len(stanzas) else ()


def _aligned(columns: Sequence[tuple[Lyric, ...]]) -> list[tuple[Lyric | None, ...]]:
    height = max(len(column) for column in columns)
    return [
        tuple(column[index] if index < len(column) else None for column in columns)
        for index in range(height)
    ]


def stacks(sections: list[Section]) -> list[Stack]:
    """Group sections by kind, keeping only kinds that have something to compare."""
    kinds: dict[str, list[Section]] = {}
    for section in sections:
        kinds.setdefault(section.kind, []).append(section)
    return [
        Stack(kind, tuple(members))
        for kind, members in kinds.items()
        if len(members) > 1
    ]
