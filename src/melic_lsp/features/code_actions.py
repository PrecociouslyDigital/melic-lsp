"""Quick fixes for the per-line lints.

One rule so far, and it is the one with an unambiguous answer: a chord landing
inside a syllable moves to that syllable's first character. Nothing else here
rewrites a lyric, because nothing else here knows what the writer meant — a line
two syllables longer than its sibling has no fix, only a question.

The edit moves the chord as it was typed and never retypes the lyric around it.
"""

from __future__ import annotations

from collections.abc import Sequence

from lsprotocol import types as lsp

from ..analysis import Interruption, LineAnalysis
from ..chordpro import Chord, Lyric
from ..settings import Settings
from . import diagnostics


def build(
    analyses: Sequence[LineAnalysis],
    settings: Settings,
    uri: str,
    context: lsp.CodeActionContext,
) -> list[lsp.CodeAction]:
    """Every fix on offer over the requested lines.

    Offered per line rather than per character: the cursor is usually at the end of
    the line being written, and a fix you have to go and stand on is one you will
    not find.
    """
    if not settings.chord_mid_syllable or not _asked_for(context.only):
        return []
    return [
        _move_chord(analysis.line, interruption, chord, uri)
        for analysis in analyses
        for interruption in analysis.interruptions()
        for chord in interruption.chords
    ]


def _asked_for(only: Sequence[lsp.CodeActionKind | str] | None) -> bool:
    """Honour ``context.only``: a client's fix-all-on-save must not move chords.

    Kinds are hierarchical, so a request for ``quickfix`` asks for every fix beneath
    it and one for ``source.fixAll`` asks for none of them. Compared by value, since
    a ``CodeActionKind`` renders as its member name rather than as its kind.
    """
    if only is None:
        return True
    kind = lsp.CodeActionKind.QuickFix.value
    asked = [getattr(wanted, "value", wanted) for wanted in only]
    return any(kind == wanted or kind.startswith(f"{wanted}.") for wanted in asked)


def _move_chord(
    line: Lyric, interruption: Interruption, chord: Chord, uri: str
) -> lsp.CodeAction:
    """``char[D]iot`` -> ``cha[D]riot``: the same chord, on a syllable it can be sung on.

    Two edits rather than one rewritten span. The chord is carried across exactly as
    typed, and the lyric between the two positions is never touched — so a fix cannot
    lose a character of anybody's words.
    """
    token = line.text[chord.source.start : chord.source.end]
    onset = lsp.Position(line=line.row, character=interruption.source.start)
    return lsp.CodeAction(
        title=f"Move {token} to the start of “{interruption.syllable.text}”",
        kind=lsp.CodeActionKind.QuickFix,
        diagnostics=[diagnostics.chord_mid_syllable(line.row, interruption)],
        # Only when it is the sole answer: two chords inside one syllable are two
        # fixes, and the editor should not pick between them on the user's behalf.
        is_preferred=len(interruption.chords) == 1,
        edit=lsp.WorkspaceEdit(
            changes={
                uri: [
                    lsp.TextEdit(range=lsp.Range(start=onset, end=onset), new_text=token),
                    lsp.TextEdit(range=_range(line.row, chord), new_text=""),
                ]
            }
        ),
    )


def _range(row: int, chord: Chord) -> lsp.Range:
    return lsp.Range(
        start=lsp.Position(line=row, character=chord.source.start),
        end=lsp.Position(line=row, character=chord.source.end),
    )
