"""Diagnostics: ChordPro syntax, plus per-line lints.

Deliberately absent: anything comparing one line to another. Two verses that
disagree on syllable count might be a mistake or might be the song, and a squiggle
cannot tell the difference. Divergence is shown on request in the compare view
instead, where it can be looked at rather than argued with.
"""

from __future__ import annotations

from difflib import get_close_matches

from lsprotocol import types as lsp

from ..analysis import LineAnalysis
from ..chordpro import DIRECTIVES, Directive, Document, Lyric
from ..overrides import EMPTY, Overrides
from ..settings import Settings
from ..types import LyricCol, SrcCol

SOURCE = "melic"


def build(
    document: Document,
    analyses: list[LineAnalysis],
    settings: Settings,
    annotations: Overrides = EMPTY,
) -> list[lsp.Diagnostic]:
    found: list[lsp.Diagnostic] = []
    if settings.chordpro_diagnostics:
        found.extend(_syntax(document))
        found.extend(
            _at(
                problem.row, SrcCol(0), SrcCol(len(_text(document, problem.row))),
                problem.message, lsp.DiagnosticSeverity.Warning,
            )
            for problem in annotations.problems
        )
    for analysis in analyses:
        found.extend(_lints(analysis, settings))
    return found


def _text(document: Document, row: int) -> str:
    return next((line.text for line in document.lines if line.row == row), "")


# --- ChordPro syntax ---------------------------------------------------------


def _syntax(document: Document) -> list[lsp.Diagnostic]:
    found: list[lsp.Diagnostic] = []

    for line in document.lines:
        match line:
            case Directive(closed=False):
                found.append(
                    _at(
                        line.row, SrcCol(0), SrcCol(len(line.text)),
                        "Directive is missing its closing brace.",
                        lsp.DiagnosticSeverity.Error,
                    )
                )
            case Directive(spec=None, name=name):
                found.append(_unknown_directive(line, name))
            case Lyric(unclosed=column) if column is not None:
                found.append(
                    _at(
                        line.row, column, SrcCol(len(line.text)),
                        "Unclosed '[': the rest of the line is sung, not played.",
                        lsp.DiagnosticSeverity.Error,
                    )
                )
            case _:
                pass

    for problem in document.problems:
        text = (
            f"'{problem.env}' environment is never closed."
            if problem.opened
            else f"Closing a '{problem.env}' environment that was never opened."
        )
        found.append(
            _at(problem.row, SrcCol(0), SrcCol(80), text, lsp.DiagnosticSeverity.Error)
        )

    return found


def _unknown_directive(line: Directive, name: str) -> lsp.Diagnostic:
    suggestions = get_close_matches(name, DIRECTIVES, n=1, cutoff=0.7)
    hint = f" Did you mean '{suggestions[0]}'?" if suggestions else ""
    return _at(
        line.row,
        line.name_range.start,
        line.name_range.end,
        f"Unknown directive '{name}'.{hint}",
        lsp.DiagnosticSeverity.Warning,
    )


# --- Per-line lints ----------------------------------------------------------


def _lints(analysis: LineAnalysis, settings: Settings) -> list[lsp.Diagnostic]:
    found: list[lsp.Diagnostic] = []
    line = analysis.line

    if settings.chord_mid_syllable:
        for syllable in analysis.syllables:
            ranges = line.spans.to_source(syllable.start, syllable.end)
            if len(ranges) > 1:
                # More than one source range means a chord token sits inside the
                # syllable — the singer has to change chord mid-vowel.
                found.append(
                    _at(
                        line.row, ranges[0].start, ranges[-1].end,
                        f"Chord lands inside the syllable “{syllable.text}”.",
                        lsp.DiagnosticSeverity.Information,
                    )
                )

    for note in analysis.notes:
        found.extend(_span_hint(line, note.span.start, note.span.end, note.message))

    if settings.unknown_pronunciation == "hint":
        for missing in analysis.unresolved:
            found.extend(_span_hint(line, missing.span.start, missing.span.end, missing.reason))
        for span in analysis.guessed:
            found.extend(
                _span_hint(
                    line, span.start, span.end,
                    f"“{span.token}” is not in the dictionary; "
                    "its pronunciation was guessed.",
                )
            )

    return found


def _span_hint(
    line: Lyric, start: LyricCol, end: LyricCol, message: str
) -> list[lsp.Diagnostic]:
    return [
        _at(line.row, source.start, source.end, message, lsp.DiagnosticSeverity.Hint)
        for source in line.spans.to_source(start, end)
    ]


def _at(
    row: int, start: SrcCol, end: SrcCol, message: str, severity: lsp.DiagnosticSeverity
) -> lsp.Diagnostic:
    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(line=row, character=start),
            end=lsp.Position(line=row, character=end),
        ),
        message=message,
        severity=severity,
        source=SOURCE,
    )
