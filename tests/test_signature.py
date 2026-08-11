"""Golden signatures, plus the rendering modes.

One fixture only. Goldens rot, and their job here is narrow: make a change to the
signature format loud rather than silent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from melic_lsp import prosody
from melic_lsp.analysis import LineAnalysis, PlacedSyllable, Unresolved
from melic_lsp.analysis import analyse_line
from melic_lsp.chordpro import parse_lyric, parse_document
from melic_lsp.signature import Mode, render
from melic_lsp.types import LyricCol, Stress, WordSpan

FIXTURE = Path(__file__).parent / "fixtures" / "swing_low.cho"

GOLDEN = [
    "5σ · + [D]++ [G]+- [D]",
    "8σ · +---+-- [A7]+",
    "5σ · + [D]++ [G]+- [D]",
    "8σ · +--- [A7]+-- [D]+",
    "11σ · - [D]++-+-- [G]--- [D]+",
    "8σ · +---+-- [A7]+",
    "10σ · - [D]+-+- [G]+-+- [D]-",
    "8σ · +--- [A7]+-- [D]+",
]


@pytest.fixture(scope="session")
def warm() -> None:
    prosody.warm_up()
    if not prosody.is_ready():
        pytest.skip("prosodic could not be loaded")


@pytest.mark.requires_prosodic
def test_golden_signatures(warm: None) -> None:
    lyrics = [
        line
        for line in parse_document(FIXTURE.read_text()).lyrics()
        if line.lyric.strip()
    ]
    assert [render(analyse_line(line)) for line in lyrics] == GOLDEN


@pytest.mark.requires_prosodic
def test_a_chord_inside_a_syllable_leaves_its_group_empty(warm: None) -> None:
    """``chari[D]ot`` reads as cha-riot, so the D lands mid-syllable and covers none.

    The empty group is the honest rendering, and the same condition is what the
    chord-mid-syllable diagnostic reports.
    """
    analysis = analyse_line(parse_lyric(0, "sweet [G]chari[D]ot,"))
    groups = analysis.groups()
    assert groups[-1].chord is not None and groups[-1].chord.name == "D"
    assert groups[-1].syllables == ()


# --- Modes, without prosodic -------------------------------------------------


def build(text: str, stresses: str, unresolved: bool = False) -> LineAnalysis:
    """A LineAnalysis with syllables placed one per character, for format tests."""
    line = parse_lyric(0, text)
    syllables = tuple(
        PlacedSyllable(
            line.lyric[index], "", Stress(mark), LyricCol(index), LyricCol(index + 1), True
        )
        for index, mark in enumerate(stresses)
    )
    missing = (
        (Unresolved(WordSpan("x", LyricCol(0)), "no espeak"),) if unresolved else ()
    )
    return LineAnalysis(line, syllables, missing, warming=False)


@pytest.mark.parametrize(
    "mode,expected",
    [
        (Mode.CHORD_GROUPED, "3σ · ++ [D]-"),
        (Mode.FLAT, "3σ · ++-"),
        (Mode.COUNT_ONLY, "3σ"),
        (Mode.OFF, ""),
    ],
)
def test_modes(mode: Mode, expected: str) -> None:
    assert render(build("ab[D]cd", "++-"), mode) == expected


def test_warming_never_renders_a_confident_count() -> None:
    analysis = build("abc", "++-")
    warming = LineAnalysis(analysis.line, (), (), warming=True)
    assert render(warming) == "…"
    assert "0σ" not in render(warming)


def test_an_unpronounceable_word_marks_the_count_uncertain() -> None:
    assert render(build("ab[D]cd", "++-", unresolved=True)).startswith("3σ?")


def test_a_line_with_no_lyrics_renders_nothing() -> None:
    assert render(build("[D][G]", "")) == ""
