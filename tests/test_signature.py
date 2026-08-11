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
from melic_lsp.rhyme import Chime, Rhyme
from melic_lsp.settings import Settings
from melic_lsp.signature import SYLLABLE, Mode, count_label, render
from melic_lsp.types import LyricCol, Stress, WordSpan

FIXTURE = Path(__file__).parent / "fixtures" / "swing_low.cho"

GOLDEN = [
    # Chord-grouped is no longer the default — the margin shows the count and the
    # rhyme — but it is still what the Scansion Panel and Compare Sections print,
    # so the format is pinned here and asked for explicitly.
    #
    # "chari[D]ot" reads as cha-ri-ot, not cha-riot: the chord picks the reading
    # that puts the change on a syllable boundary. See test_chord_placement_* below.
    "6σ · + [D]++ [G]+- [D]-",
    "8σ · +---+-- [A7]+",
    "6σ · + [D]++ [G]+- [D]-",
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


def lyrics() -> list:
    return [
        line
        for line in parse_document(FIXTURE.read_text()).lyrics()
        if line.lyric.strip()
    ]


@pytest.mark.requires_prosodic
def test_golden_signatures(warm: None) -> None:
    grouped = [render(analyse_line(line), Mode.CHORD_GROUPED) for line in lyrics()]
    assert grouped == GOLDEN


@pytest.mark.requires_prosodic
def test_the_shipped_default_is_just_the_count(warm: None) -> None:
    """What the margin shows now: no marks to line up where nothing lines up."""
    default = [render(analyse_line(line), Settings().signature) for line in lyrics()]
    assert default[:2] == ["6σ", "8σ"]


@pytest.mark.requires_prosodic
def test_chord_placement_picks_the_reading_that_fits_it(warm: None) -> None:
    """``chari[D]ot`` chooses cha-ri-ot, so the D lands on a boundary and covers ``ot``.

    Prosodic prefers cha-riot knowing nothing about the music; the chord says
    otherwise, and the chord is the better evidence about how it is sung.
    """
    analysis = analyse_line(parse_lyric(0, "sweet [G]chari[D]ot,"))
    groups = analysis.groups()
    assert groups[-1].chord is not None and groups[-1].chord.name == "D"
    assert [s.text for s in groups[-1].syllables] == ["ot"]


@pytest.mark.requires_prosodic
def test_without_a_chord_inside_it_the_dictionary_reading_stands(warm: None) -> None:
    """The tie-break is what keeps this from changing behaviour everywhere else."""
    analysis = analyse_line(parse_lyric(0, "sweet [G]chariot,"))
    assert [s.text for s in analysis.syllables[1:]] == ["cha", "riot"]


@pytest.mark.requires_prosodic
def test_the_choice_can_be_turned_off(warm: None) -> None:
    analysis = analyse_line(parse_lyric(0, "sweet [G]chari[D]ot,"), chord_aware=False)
    assert [s.text for s in analysis.syllables[1:]] == ["cha", "riot"]


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


def test_the_rhyme_shows_even_with_the_signature_off() -> None:
    """Two independent settings: turning the marks off is not turning rhyme off."""
    analysis = build("ab[D]cd", "++-")
    assert render(analysis, Mode.OFF, Rhyme("A", Chime.SLANT)) == "A~"
    assert render(analysis, Mode.COUNT_ONLY, Rhyme("A", Chime.SLANT)) == "3σ A~"


def test_a_rhyme_never_pushes_the_count_out_of_its_column() -> None:
    """The panels are read down the σ column, so the letter pads to the right of it."""
    rhymed = count_label(build("a", "+"), Rhyme("A", Chime.PERFECT), width=4)
    plain = count_label(build("abcdefghijk", "+" * 11), None, width=4)
    assert rhymed.index(SYLLABLE) == plain.index(SYLLABLE)


def test_warming_never_renders_a_confident_count() -> None:
    analysis = build("abc", "++-")
    warming = LineAnalysis(analysis.line, (), (), warming=True)
    assert render(warming, Mode.CHORD_GROUPED) == "…"
    assert "0σ" not in render(warming, Mode.CHORD_GROUPED)


def test_an_unpronounceable_word_marks_the_count_uncertain() -> None:
    signature = render(build("ab[D]cd", "++-", unresolved=True), Mode.CHORD_GROUPED)
    assert signature.startswith("3σ?")


def test_a_line_with_no_lyrics_renders_nothing() -> None:
    assert render(build("[D][G]", ""), Mode.CHORD_GROUPED) == ""
