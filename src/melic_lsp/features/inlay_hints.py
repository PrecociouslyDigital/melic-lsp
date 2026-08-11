"""Inlay hints: the line signature at the end of the line, and optional detail."""

from __future__ import annotations

from lsprotocol import types as lsp

from ..analysis import LineAnalysis
from ..settings import Settings
from ..signature import render


def build(
    analyses: list[LineAnalysis],
    settings: Settings,
    rhymes: dict[int, str] | None = None,
) -> list[lsp.InlayHint]:
    hints: list[lsp.InlayHint] = []
    for analysis in analyses:
        letter = (rhymes or {}).get(analysis.line.row) if settings.rhyme else None
        hints.extend(_for_line(analysis, settings, letter))
    return hints


def _for_line(
    analysis: LineAnalysis, settings: Settings, rhyme_letter: str | None
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
    if rhyme_letter and not analysis.warming:
        text = f"{text} {rhyme_letter}" if text else rhyme_letter
    if text:
        hints.append(
            lsp.InlayHint(
                position=lsp.Position(line=line.row, character=len(line.text)),
                label=text,
                padding_left=True,
                tooltip=_tooltip(analysis),
            )
        )
    return hints


def _tooltip(analysis: LineAnalysis) -> str:
    parts = [f"{analysis.count} syllables"]
    if analysis.line.chords:
        parts.append(f"{len(analysis.line.chords)} chord changes")
    parts.extend(f"“{u.span.token}” — {u.reason}" for u in analysis.unresolved)
    return "  \n".join(parts)
