"""Document outline: sections, each labelled with its syllable profile and scheme.

The profile is the point. "Verse 1 · 8,6,8,6σ · ABAB" tells you the shape of a
section from the outline alone, which is exactly what you want when checking whether
verse three still matches the tune you wrote for verse one.
"""

from __future__ import annotations

from lsprotocol import types as lsp

from ..analysis import LineAnalysis
from ..rhyme import Rhyme, scheme_string
from ..sections import Section
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
    analysed = [by_row[line.row] for line in section.lines if line.row in by_row]
    profile = ",".join(str(a.count) for a in analysed[:MAX_PROFILE_LINES])
    if len(analysed) > MAX_PROFILE_LINES:
        profile += ",…"
    if any(a.unresolved for a in analysed):
        # Some count in here is a floor, not a total; say so rather than imply
        # a section is shorter than it sings.
        profile += "?"

    scheme = scheme_string(list(section.lines), rhymes)
    detail = SEPARATOR.join(
        part for part in (f"{profile}σ" if profile else "", scheme) if part
    )

    extent = lsp.Range(
        start=lsp.Position(line=section.start_row, character=0),
        end=lsp.Position(line=section.end_row, character=len(section.lines[-1].text)),
    )
    return lsp.DocumentSymbol(
        name=section.title,
        detail=detail,
        kind=lsp.SymbolKind.Namespace,
        range=extent,
        selection_range=extent,
        children=[
            lsp.DocumentSymbol(
                name=line.lyric.strip()[:60],
                detail=count_label(by_row[line.row]) if line.row in by_row else "",
                kind=lsp.SymbolKind.String,
                range=_line_range(line.row, len(line.text)),
                selection_range=_line_range(line.row, len(line.text)),
            )
            for line in section.lines
        ],
    )


def _line_range(row: int, length: int) -> lsp.Range:
    return lsp.Range(
        start=lsp.Position(line=row, character=0),
        end=lsp.Position(line=row, character=length),
    )
