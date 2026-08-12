"""Diagnostics: ChordPro syntax, plus per-line lints.

Deliberately absent: anything comparing one line to another. Two verses that
disagree on syllable count might be a mistake or might be the song, and a squiggle
cannot tell the difference. Divergence is shown on request in the compare view
instead, where it can be looked at rather than argued with.

``hints.py`` is the governed exception, and everything in that sentence still holds
there: each of its rules has its own ``melic.hints.*`` severity, refuses to fire
while any line it compares is warming or holds a word with no pronunciation, and
names the lines it was measured against. ``server.diagnostic`` concatenates the two.
"""

from __future__ import annotations

from difflib import get_close_matches

from lsprotocol import types as lsp

from ..analysis import Interruption, LineAnalysis
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
        found.extend(
            chord_mid_syllable(line.row, interruption)
            for interruption in analysis.interruptions()
        )

    for note in analysis.notes:
        found.extend(_span_hint(line, note.span.start, note.span.end, note.message))

    if settings.unknown_pronunciation == "hint":
        # Only words with no pronunciation at all, where the syllable count is a
        # floor rather than a total. A *guessed* pronunciation is not flagged: it
        # yields a real count, and marking every invented word in a lyric sheet is
        # noise you learn to ignore. If a guess is wrong, {x_melic_word} fixes it.
        for missing in analysis.unresolved:
            found.extend(_span_hint(line, missing.span.start, missing.span.end, missing.reason))

    return found


def chord_mid_syllable(row: int, interruption: Interruption) -> lsp.Diagnostic:
    """The mark on one syllable a chord lands inside — the singer changes mid-vowel.

    Public because ``code_actions`` attaches the fix to exactly this diagnostic, and
    a client pairs the two by comparing them: one built independently would drift
    from this one on the first word of its message.
    """
    return _at(
        row,
        interruption.source.start,
        interruption.source.end,
        f"Chord lands inside the syllable “{interruption.syllable.text}”.",
        lsp.DiagnosticSeverity.Information,
    )


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
