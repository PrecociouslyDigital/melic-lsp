"""Rhyme labelling: the letters we hand out, and the quality we keep.

The scheme string is pure given labels, so most of this needs no dictionary. The
classification tests pin the mapping *we* own — which of prosodic's answers count as
rhyme, and that a repeated word is called out rather than silently counted perfect.
Whether "love" and "prove" really are a slant rhyme is prosodic's business.
"""

from __future__ import annotations

import pytest

from melic_lsp import prosody
from melic_lsp.chordpro import parse_lyric
from melic_lsp.rhyme import Chime, Rhyme, classify, scheme, scheme_string
from melic_lsp.types import Ready

# --- Labels and scheme strings, without prosodic ------------------------------


def lines(count: int) -> list:
    return [parse_lyric(row, f"line {row}") for row in range(count)]


def labelled(*labels: str | None) -> dict[int, Rhyme]:
    """Rhymes by row, spelled as the margin would show them: "A", "B~", None."""
    return {
        row: Rhyme(label[0], Chime(label[1:]))
        for row, label in enumerate(labels)
        if label is not None
    }


def test_the_label_is_the_letter_plus_the_mark() -> None:
    assert Rhyme("A", Chime.PERFECT).label == "A"
    assert Rhyme("A", Chime.SLANT).label == "A~"
    assert Rhyme("A", Chime.IDENTICAL).label == "A="


def test_the_scheme_reads_in_row_order() -> None:
    assert scheme_string(lines(4), labelled("A", "B", "A", "B")) == "ABAB"


def test_quality_marks_do_not_reach_the_scheme() -> None:
    """A slant rhyme is still that slot in the pattern; ABAB is about shape."""
    assert scheme_string(lines(4), labelled("A", "B", "A~", "B=")) == "ABAB"


def test_a_line_that_chimes_with_nothing_is_X() -> None:
    assert scheme_string(lines(4), labelled("A", None, "A", None)) == "AXAX"


def test_a_section_where_nothing_rhymes_says_nothing() -> None:
    """"XXXX" on every stanza of an unrhymed song is noise, not information."""
    assert scheme_string(lines(4), {}) == ""


# --- Classification, which needs the dictionary -------------------------------


@pytest.fixture(scope="session")
def warm() -> None:
    prosody.warm_up()
    if not prosody.is_ready():
        pytest.skip("prosodic could not be loaded")


def ending(token: str):
    result = prosody.syllabify(token)
    if not isinstance(result, Ready):
        pytest.skip(f"no pronunciation for {token!r}")
    return result.value.syllables


@pytest.mark.requires_prosodic
@pytest.mark.parametrize(
    "first,second,expected",
    [
        ("home", "roam", Chime.PERFECT),
        ("home", "home", Chime.IDENTICAL),
        ("Home", "home", Chime.IDENTICAL),
        ("love", "prove", Chime.SLANT),
        ("chariot", "home", None),
    ],
)
def test_classification(
    warm: None, first: str, second: str, expected: Chime | None
) -> None:
    assert classify(ending(first), ending(second)) is expected


@pytest.mark.requires_prosodic
def test_letters_are_handed_out_in_first_appearance_order(warm: None) -> None:
    quatrain = [
        parse_lyric(0, "Amazing grace, how sweet the sound,"),
        parse_lyric(1, "That saved a wretch like me."),
        parse_lyric(2, "I once was lost, but now am found,"),
        parse_lyric(3, "Was blind but now I see."),
    ]
    labels = scheme(quatrain)
    assert [labels[row].label for row in range(4)] == ["A", "B", "A", "B"]
    assert scheme_string(quatrain, labels) == "ABAB"


@pytest.mark.requires_prosodic
def test_a_repeated_ending_holds_the_slot_and_says_it_is_repeated(warm: None) -> None:
    """The refrain case: prosodic says a word does not rhyme with itself, which is
    right about rhyme and wrong about songs."""
    refrain = [
        parse_lyric(0, "Comin' for to carry me home."),
        parse_lyric(1, "A band of angels comin' after me,"),
        parse_lyric(2, "Comin' for to carry me home."),
    ]
    labels = scheme(refrain)
    assert labels[0].label == "A" and labels[2].label == "A="
    assert 1 not in labels
