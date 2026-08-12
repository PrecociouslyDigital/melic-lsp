"""Rhyme labelling: the letters we hand out, and the quality we keep.

The scheme string is pure given labels, so most of this needs no dictionary. The
classification tests pin the mapping *we* own — which of prosodic's answers count as
rhyme, and that a repeated word is called out rather than silently counted perfect.
Whether "love" and "prove" really are a slant rhyme is prosodic's business.
"""

from __future__ import annotations

import pytest

from melic_lsp import prosody, rhyme
from melic_lsp.chordpro import parse_lyric
from melic_lsp.rhyme import (
    Chime,
    Rhyme,
    classify,
    contextual_chime,
    scheme,
    scheme_string,
    solve,
)
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
        # Assonance: same vowel, a coda that misses. Prosodic's calibration leaves
        # it out and so does the strict pass — the solver is where it may come back.
        ("pterodactyl", "fractal", None),
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


# --- The solver ---------------------------------------------------------------
#
# Every stanza below is written for the test rather than quoted, so the endings can
# be chosen to sit either side of the thresholds and nothing here is anyone's song.


def stanza(*texts: str, start: int = 0) -> list:
    return [parse_lyric(start + offset, text) for offset, text in enumerate(texts)]


def near_miss_quatrain() -> list:
    """fire/wire rhymes outright; pterodactyl/fractal is the near miss (coda 0.23)."""
    return stanza(
        "Watch the last light leave the fire,",
        "Bones of some old pterodactyl,",
        "Fences running down to wire,",
        "Every branch of it a fractal,",
    )


@pytest.mark.requires_prosodic
@pytest.mark.parametrize(
    "first,second,admitted",
    [
        ("pterodactyl", "fractal", True),  # coda 0.23
        ("time", "line", True),  # coda 0.21
        ("body", "probably", False),  # coda 0.40
        ("day", "late", False),  # coda 1.0 — the textbook assonance
        ("fire", "wire", False),  # the vowel drifts, which a weak edge never forgives
    ],
)
def test_the_weak_edge_bounds(
    warm: None, first: str, second: str, admitted: bool
) -> None:
    chime = contextual_chime(ending(first), ending(second))
    assert (chime is Chime.CONTEXTUAL) is admitted


@pytest.mark.requires_prosodic
def test_a_stanza_that_rhymes_vouches_for_its_own_near_miss(warm: None) -> None:
    """The motivating case. fire/wire carries the stanza, so the two lines left over
    read as the pair answering each other rather than as loose ends."""
    quatrain = near_miss_quatrain()
    labels = solve([quatrain])
    assert [labels[row].label for row in range(4)] == ["A", "B", "A~", "B≈"]
    assert scheme_string(quatrain, labels) == "ABAB"


@pytest.mark.requires_prosodic
def test_the_strict_pass_is_untouched_by_any_of_this(warm: None) -> None:
    """Which is what ``melic.rhyme.slantScope: strict`` still buys."""
    quatrain = near_miss_quatrain()
    assert sorted(scheme(quatrain)) == [0, 2]


@pytest.mark.requires_prosodic
def test_a_couplet_with_nothing_to_vouch_for_it_gets_nothing(warm: None) -> None:
    """Free verse never sprouts ≈. Alone, a near miss is only a near miss."""
    couplet = stanza(
        "Bones of some old pterodactyl,",
        "Every branch of it a fractal,",
    )
    assert solve([couplet]) == {}


@pytest.mark.requires_prosodic
def test_a_sibling_stanza_can_vouch_for_what_a_stanza_cannot(warm: None) -> None:
    """Song corroboration: the couplet rhymes because the song is made of couplets.

    Nothing inside the second couplet changed between these two calls — only whether
    another stanza in the song could spell the same shape.
    """
    answered = stanza("We walked the road at fall of night,", "A lantern gave us light,")
    weak = stanza(
        "The bell was rung a second time,",
        "And every stone along the line,",
        start=3,
    )
    together = solve([answered, weak])
    assert [together[row].label for row in (3, 4)] == ["A", "A≈"]
    assert solve([weak]) == {}


@pytest.mark.requires_prosodic
def test_a_strict_group_is_never_reshuffled(warm: None) -> None:
    """night/light is prosodic's call and stays whole; time/line is left to pair up,
    and time is never pulled into the group it does not belong to."""
    quatrain = stanza(
        "We walked the road at fall of night,",
        "The bell was rung a second time,",
        "A lantern gave us light,",
        "And every stone along the line,",
    )
    labels = solve([quatrain])
    assert labels[0].letter == labels[2].letter
    assert labels[1].letter == labels[3].letter != labels[0].letter
    assert labels[1].chime is Chime.PERFECT and labels[3].chime is Chime.CONTEXTUAL


@pytest.mark.requires_prosodic
def test_a_stanza_whose_near_misses_are_tangled_keeps_its_strict_scheme(
    warm: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bound on the search, without which one stanza can cost seconds.

    Posed rather than found: every pair of endings is made to offer a weak edge,
    which real phonetics never do, and which is exactly why the bound has to be on
    the number of readings rather than on the words.
    """
    monkeypatch.setattr(rhyme, "_weak_cost", lambda first, second: 0.1)
    tangled = stanza(
        "We walked the road at fall of night,",
        "A lantern gave us light,",
        "The morning water running cold,",
        "The last of it was fire,",
        "And then it turned to rain,",
        "A shadow on the tree,",
        "The pages of a book,",
        "And nothing but the wind,",
    )
    assert sum(1 for g in rhyme._strict(tangled, "en") if len(g.members) == 1) == 6
    assert len(rhyme._candidates(tangled, "en")) == 1
    assert solve([tangled]) == scheme(tangled)


@pytest.mark.requires_prosodic
def test_a_stanza_that_already_rhymes_throughout_adopts_nothing(warm: None) -> None:
    """No free lines, so there is no weak edge on offer and nothing to weigh."""
    quatrain = stanza(
        "The morning water running cold,",
        "The windows rattling with the rain,",
        "The willow turning brown and gold,",
        "The furrows lying bare and plain,",
    )
    assert solve([quatrain]) == scheme(quatrain)
