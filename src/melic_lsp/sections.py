"""Grouping lines into sections, and lining parallel sections up against each other.

Explicit environments win where they exist; otherwise blank lines mark stanzas,
because most songs are written without a single directive. Comparison is only ever
between sections of the same kind — verses against verses — since a chorus is not
supposed to scan like a verse.
"""

from __future__ import annotations

from dataclasses import dataclass

from .chordpro import Blank, Directive, Document, EnvKind, Lyric

IMPLICIT = "stanza"


@dataclass(frozen=True)
class Section:
    kind: str
    """The environment name — "verse", "chorus", "bridge" — or "stanza"."""
    label: str | None
    """Whatever ``{start_of_verse: Verse 1}`` named it."""
    lines: tuple[Lyric, ...]

    @property
    def title(self) -> str:
        return self.label or self.kind.capitalize()

    @property
    def start_row(self) -> int:
        return self.lines[0].row

    @property
    def end_row(self) -> int:
        return self.lines[-1].row


def group(document: Document) -> list[Section]:
    """Split a document into sections, explicit environments taking precedence."""
    sections: list[Section] = []
    current: list[Lyric] = []
    env: tuple[str, str | None] | None = None

    def flush(kind: str, label: str | None) -> None:
        if current:
            sections.append(Section(kind, label, tuple(current)))
            current.clear()

    for line in document.lines:
        match line:
            case Directive(spec=spec, value=value) if spec is not None and spec.env:
                role = spec.env
                if role.kind is not EnvKind.LYRIC:
                    continue
                if role.opens:
                    flush(*(env or (IMPLICIT, None)))
                    env = (role.env, value)
                else:
                    flush(*(env or (IMPLICIT, None)))
                    env = None
            case Blank() if env is None:
                # Blank lines separate stanzas, but only outside an environment,
                # where a blank is just breathing room in the middle of a verse.
                flush(IMPLICIT, None)
            case Lyric() if line.lyric.strip():
                current.append(line)
            case _:
                pass

    flush(*(env or (IMPLICIT, None)))
    return sections


@dataclass(frozen=True)
class Stack:
    """Every section of one kind, lined up so that first lines sit above first lines."""

    kind: str
    sections: tuple[Section, ...]

    @property
    def rows(self) -> list[tuple[Lyric | None, ...]]:
        """Aligned by index within the section.

        A ragged tail is left ragged, as ``None``: a verse with an extra line is
        exactly the divergence worth looking at, not something to pad away.
        """
        height = max(len(section.lines) for section in self.sections)
        return [
            tuple(
                section.lines[index] if index < len(section.lines) else None
                for section in self.sections
            )
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
