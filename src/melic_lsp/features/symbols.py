"""Document outline: sections, their stanzas, and each one's syllable profile.

The profile is the point. "Verse 1 · 8,6,8,6σ · ABAB" tells you the shape of a
stanza from the outline alone, which is exactly what you want when checking whether
verse three still matches the tune you wrote for verse one.

A section holding several stanzas says so and lets you open them one at a time; a
section that is a single stanza wears the profile itself, because a lone "Stanza 1"
node between a verse and its lines is a click for nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

from lsprotocol import types as lsp

from ..analysis import LineAnalysis
from ..chordpro import Lyric
from ..rhyme import Rhyme, scheme_string
from ..sections import Section, Stanza
from ..signature import SEPARATOR, count_label

MAX_PROFILE_LINES = 8


def build(
    sections: list[Section],
    analyses: list[LineAnalysis],
    rhymes: dict[int, Rhyme] | None = None,
) -> list[lsp.DocumentSymbol]:
    by_row = {analysis.line.row: analysis for analysis in analyses}
    return [_symbol(section, by_row, rhymes or {}) for section in sections]


def _symbol(
    section: Section, by_row: dict[int, LineAnalysis], rhymes: dict[int, Rhyme]
) -> lsp.DocumentSymbol:
    stanzas = section.stanzas
    if len(stanzas) == 1:
        detail = _profile(stanzas[0], by_row, rhymes)
        children = _lines(stanzas[0], by_row, rhymes)
    else:
        detail = f"{len(stanzas)} stanzas"
        children = [
            _node(
                f"Stanza {number}",
                _profile(stanza, by_row, rhymes),
                lsp.SymbolKind.Object,
                stanza.lines,
                _lines(stanza, by_row, rhymes),
            )
            for number, stanza in enumerate(stanzas, start=1)
        ]
    return _node(
        section.title, detail, lsp.SymbolKind.Namespace, section.lines, children
    )


def _profile(
    stanza: Stanza, by_row: dict[int, LineAnalysis], rhymes: dict[int, Rhyme]
) -> str:
    """The stanza's shape: line counts, then the scheme those lines make."""
    analysed = [by_row[line.row] for line in stanza.lines if line.row in by_row]
    profile = ",".join(str(a.count) for a in analysed[:MAX_PROFILE_LINES])
    if len(analysed) > MAX_PROFILE_LINES:
        profile += ",…"
    if any(a.unresolved for a in analysed):
        # Some count in here is a floor, not a total; say so rather than imply
        # a stanza is shorter than it sings.
        profile += "?"

    scheme = scheme_string(list(stanza.lines), rhymes)
    return SEPARATOR.join(
        part for part in (f"{profile}σ" if profile else "", scheme) if part
    )


def _lines(
    stanza: Stanza, by_row: dict[int, LineAnalysis], rhymes: dict[int, Rhyme]
) -> list[lsp.DocumentSymbol]:
    return [
        _node(
            line.lyric.strip()[:60],
            count_label(by_row[line.row], rhymes.get(line.row))
            if line.row in by_row
            else "",
            lsp.SymbolKind.String,
            (line,),
            [],
        )
        for line in stanza.lines
    ]


def _node(
    name: str,
    detail: str,
    kind: lsp.SymbolKind,
    lines: Sequence[Lyric],
    children: list[lsp.DocumentSymbol],
) -> lsp.DocumentSymbol:
    extent = lsp.Range(
        start=lsp.Position(line=lines[0].row, character=0),
        end=lsp.Position(line=lines[-1].row, character=len(lines[-1].text)),
    )
    return lsp.DocumentSymbol(
        name=name,
        detail=detail,
        kind=kind,
        range=extent,
        selection_range=extent,
        children=children,
    )
