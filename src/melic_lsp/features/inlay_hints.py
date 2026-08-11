"""Inlay hints: the line signature at the end of the line, and optional detail.

Hints sit flush against text of varying length, so nothing in this margin lines up
vertically with anything else. That is why the default carries the syllable count
and the rhyme rather than the stress marks: comparing patterns line against line is
exactly what an unaligned margin cannot do, and the panels do it in columns.
"""

from __future__ import annotations

from lsprotocol import types as lsp

from ..analysis import LineAnalysis
from ..rhyme import DESCRIPTION, Rhyme
from ..settings import Settings
from ..signature import render


def build(
    analyses: list[LineAnalysis],
    settings: Settings,
    rhymes: dict[int, Rhyme] | None = None,
) -> list[lsp.InlayHint]:
    hints: list[lsp.InlayHint] = []
    for analysis in analyses:
        rhyme = (rhymes or {}).get(analysis.line.row) if settings.rhyme else None
        hints.extend(_for_line(analysis, settings, rhyme))
    return hints


def _for_line(
    analysis: LineAnalysis, settings: Settings, rhyme: Rhyme | None
) -> list[lsp.InlayHint]:
    hints: list[lsp.InlayHint] = []
    line = analysis.line

    if settings.per_syllable_hints:
        # Placed before each syllable so the marks line up with what they describe.
        hints.extend(
            lsp.InlayHint(
                position=lsp.Position(line=line.row, character=source.start),
                label=syllable.stress.value,
                padding_right=False,
                tooltip=f"{syllable.text} /{syllable.ipa}/",
            )
            for syllable in analysis.syllables
            if syllable.exact
            for source in line.spans.to_source(syllable.start, syllable.end)[:1]
        )

    text = render(analysis, settings.signature)
    if rhyme is not None and not analysis.warming:
        text = f"{text} {rhyme.label}" if text else rhyme.label
    if text:
        hints.append(
            lsp.InlayHint(
                position=lsp.Position(line=line.row, character=len(line.text)),
                label=text,
                padding_left=True,
                tooltip=_tooltip(analysis, rhyme),
            )
        )
    return hints


def _tooltip(analysis: LineAnalysis, rhyme: Rhyme | None) -> str:
    """The margin has room for a glyph; here there is room to say what it means."""
    parts = [f"{analysis.count} syllables"]
    if analysis.line.chords:
        parts.append(f"{len(analysis.line.chords)} chord changes")
    if rhyme is not None and not analysis.warming:
        parts.append(f"rhyme {rhyme.letter} — {DESCRIPTION[rhyme.chime]}")
    parts.extend(f"“{u.span.token}” — {u.reason}" for u in analysis.unresolved)
    return "  \n".join(parts)
