"""The quick fix that moves a chord onto the syllable it landed inside.

The syllable splits are dictated rather than measured, as in ``test_hints``: what is
under test is where the chord ends up, not whether "chariot" is two syllables or
three. Every case therefore states the edit's effect as the line the editor would be
left holding, because that — not a pair of column numbers — is what the user sees.

One case does run the real pipeline, and answers the question the dictated ones
cannot: that a real reading of a real word maps onto the characters we claim.
"""

from __future__ import annotations

import pytest
from lsprotocol import types as lsp

from melic_lsp import prosody
from melic_lsp.analysis import LineAnalysis, PlacedSyllable, analyse_line
from melic_lsp.chordpro import Document, parse_lyric
from melic_lsp.features import code_actions, diagnostics
from melic_lsp.settings import Settings
from melic_lsp.types import LyricCol, Stress

URI = "file:///song.cho"


def analysed(text: str, *syllables: str, exact: bool = True) -> LineAnalysis:
    """A line split into the syllables named, located by finding them in order."""
    line = parse_lyric(0, text)
    placed: list[PlacedSyllable] = []
    cursor = 0
    for syllable in syllables:
        start = line.lyric.index(syllable, cursor)
        cursor = start + len(syllable)
        placed.append(
            PlacedSyllable(
                syllable, "", Stress.NONE, LyricCol(start), LyricCol(cursor), exact
            )
        )
    return LineAnalysis(line, tuple(placed), (), warming=False)


def fixes(
    analysis: LineAnalysis,
    settings: Settings = Settings(),
    only: list[lsp.CodeActionKind | str] | None = None,
) -> list[lsp.CodeAction]:
    context = lsp.CodeActionContext(diagnostics=[], only=only)
    return code_actions.build([analysis], settings, URI, context)


def applied(text: str, action: lsp.CodeAction) -> str:
    """The line as the editor would leave it: edits taken from the end backwards."""
    assert action.edit and action.edit.changes
    for edit in sorted(
        action.edit.changes[URI], key=lambda e: e.range.start.character, reverse=True
    ):
        start, end = edit.range.start.character, edit.range.end.character
        text = text[:start] + edit.new_text + text[end:]
    return text


# --- Moving the chord ---------------------------------------------------------


def test_a_chord_inside_a_syllable_moves_to_its_start() -> None:
    text = "char[D]iot rides"
    (fix,) = fixes(analysed(text, "cha", "riot", "rides"))
    assert fix.title == "Move [D] to the start of “riot”"
    assert applied(text, fix) == "cha[D]riot rides"


@pytest.mark.parametrize("text", ["cha[D]riot", "chari[D]ot", "[D]chariot", "chariot[D]"])
def test_a_chord_on_a_boundary_is_where_it_belongs(text: str) -> None:
    """The good case, and the one the strict comparison exists to pass over."""
    assert fixes(analysed(text, "cha", "ri", "ot")) == []


def test_the_chord_is_carried_across_exactly_as_typed() -> None:
    text = "char[Gsus4/B]iot"
    (fix,) = fixes(analysed(text, "cha", "riot"))
    assert applied(text, fix) == "cha[Gsus4/B]riot"


def test_only_the_chord_moves_when_the_line_is_full_of_them() -> None:
    text = "Swing [D]low, sweet [G]char[D]iot,"
    (fix,) = fixes(analysed(text, "Swing", "low", "sweet", "cha", "riot"))
    assert applied(text, fix) == "Swing [D]low, sweet [G]cha[D]riot,"


def test_each_chord_inside_one_syllable_is_a_fix_of_its_own() -> None:
    """``c[D]h[G]a`` is interrupted twice, and which to move first is not ours to say."""
    text = "c[D]h[G]ariot"
    first, second = fixes(analysed(text, "cha", "riot"))
    assert [fix.title for fix in (first, second)] == [
        "Move [D] to the start of “cha”",
        "Move [G] to the start of “cha”",
    ]
    assert applied(text, first) == "[D]ch[G]ariot"
    assert applied(text, second) == "[G]c[D]hariot"
    assert not any(fix.is_preferred for fix in (first, second))


def test_the_lone_answer_to_a_problem_is_the_preferred_one() -> None:
    (fix,) = fixes(analysed("char[D]iot", "cha", "riot"))
    assert fix.is_preferred


# --- What it refuses to offer -------------------------------------------------


def test_no_fix_where_the_syllable_positions_are_a_guess() -> None:
    """An inexact syllable spans its whole word, so there is no start to move to."""
    assert fixes(analysed("char[D]iot", "cha", "riot", exact=False)) == []


def test_turning_the_lint_off_withdraws_its_fix() -> None:
    quiet = Settings(chord_mid_syllable=False)
    assert fixes(analysed("char[D]iot", "cha", "riot"), quiet) == []


@pytest.mark.parametrize(
    ("only", "offered"),
    [
        (None, 1),
        (["quickfix"], 1),
        ([lsp.CodeActionKind.QuickFix], 1),
        (["quickfix.chord"], 0),
        (["source.fixAll"], 0),
    ],
)
def test_a_request_for_other_kinds_goes_unanswered(
    only: list[lsp.CodeActionKind | str], offered: int
) -> None:
    """Fixing everything on save must not silently rearrange a song. The kind arrives
    either as the enum or as the string it was sent as, and both have to be read."""
    assert len(fixes(analysed("char[D]iot", "cha", "riot"), only=only)) == offered


# --- The fix and the lint are one thing ---------------------------------------


def test_the_fix_carries_the_lint_it_answers() -> None:
    """A client pairs a fix with its problem by value, so both are built from one
    source: a message reworded on one side would strand the lightbulb on the other."""
    analysis = analysed("char[D]iot", "cha", "riot")
    (fix,) = fixes(analysis)
    published = diagnostics.build(Document((analysis.line,), ()), [analysis], Settings())
    assert fix.diagnostics == published


# --- Against the real dictionary ----------------------------------------------


@pytest.mark.requires_prosodic
def test_a_real_reading_lands_the_chord_on_a_real_character() -> None:
    """Whether prosodic reads "chariot" as cha-ri-ot or cha-riot, the chord it splits
    belongs at the same place: after "cha"."""
    prosody.warm_up("en")
    text = "char[D]iot"
    (fix,) = fixes(analyse_line(parse_lyric(0, text)))
    assert applied(text, fix) == "cha[D]riot"
