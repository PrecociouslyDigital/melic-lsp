"""Tests for the prosodic adapter.

These test *my guard*, not prosodic's linguistics. Whether "chariot" has three
syllables is upstream's business and upstream's test suite; whether a syllable list
that does not partition its token can ever produce a character range is mine.
"""

from __future__ import annotations

import pytest

from melic_lsp import prosody
from melic_lsp.types import (
    RawSyllable,
    Ready,
    Stress,
    Tiled,
    Unavailable,
    Warming,
    WholeWord,
    tile,
)


def raw(*texts: str) -> list[RawSyllable]:
    return [RawSyllable(text, "", Stress.NONE) for text in texts]


# --- The guard, tested without prosodic --------------------------------------


def test_tile_places_syllables_that_partition_the_token() -> None:
    result = tile("chariot", raw("cha", "ri", "ot"))
    assert isinstance(result, Tiled)
    assert [s.start for s in result.syllables] == [0, 3, 5]
    assert "".join(s.text for s in result.syllables) == "chariot"


def test_tile_compares_lengths_not_text() -> None:
    """The g2p path skips fix_recasing, so a correct partition may be lowercased."""
    assert isinstance(tile("Home", raw("home")), Tiled)


@pytest.mark.parametrize(
    "token,parts",
    [
        ("3", ("three",)),  # numerals expand to something else entirely
        ("chariot", ("cha", "ri")),  # short
        ("cha", ("cha", "ri", "ot")),  # long
        ("anything", ()),  # nothing at all
    ],
)
def test_tile_refuses_to_place_what_does_not_partition(
    token: str, parts: tuple[str, ...]
) -> None:
    assert isinstance(tile(token, raw(*parts)), WholeWord)


def test_whole_word_keeps_the_count_it_can_still_vouch_for() -> None:
    """Degrading loses positions, not the syllable count or the stress pattern."""
    result = tile("3", raw("three"))
    assert isinstance(result, WholeWord)
    assert len(result.syllables) == 1


# --- Against the real dictionary ---------------------------------------------

pytestmark_prosodic = pytest.mark.requires_prosodic


@pytest.fixture(scope="session")
def warm() -> None:
    prosody.warm_up()
    if not prosody.is_ready():
        pytest.skip("prosodic could not be loaded")


@pytest.mark.requires_prosodic
@pytest.mark.parametrize(
    "token",
    [
        "chariot", "swing", "low", "sweet", "home", "carry", "angels",
        "runnin'", "augustus'", "don't", "fire", "hour", "every", "heaven",
        "Home", "SWING", "jordan", "comin'", "over", "band",
    ],
)
def test_dictionary_words_tile_exactly(warm: None, token: str) -> None:
    result = prosody.syllabify(token)
    assert isinstance(result, Ready), f"{token}: {result}"
    syllabified = result.value.syllables
    assert isinstance(syllabified, Tiled), f"{token} did not tile"
    assert "".join(s.text for s in syllabified.syllables) == token


@pytest.mark.requires_prosodic
@pytest.mark.parametrize("token", ["3", "42", "blorptastic", "zzzxqq", "xyzzy"])
def test_unpronounceable_tokens_degrade_instead_of_raising(
    warm: None, token: str
) -> None:
    """The real path on this machine: no espeak, so the dictionary is all there is."""
    result = prosody.syllabify(token)
    assert isinstance(result, (Ready, Unavailable))
    if isinstance(result, Unavailable):
        assert "espeak" in result.reason or "pronounce" in result.reason


@pytest.mark.requires_prosodic
def test_warming_is_never_memoised(warm: None) -> None:
    """The one caching bug that would survive every other test.

    Caching a ``Warming`` answer would pin a word to "still loading" for the life
    of the server. The cache deliberately sits behind the readiness check.
    """
    prosody._ready.clear()
    try:
        assert isinstance(prosody.syllabify("chariot"), Warming)
    finally:
        prosody._ready.set()
    assert isinstance(prosody.syllabify("chariot"), Ready)


@pytest.mark.requires_prosodic
@pytest.mark.parametrize(
    "first,second,expected",
    [("home", "roam", True), ("see", "me", True), ("chariot", "home", False)],
)
def test_rhyme_needs_no_text_construction(
    warm: None, first: str, second: str, expected: bool
) -> None:
    left, right = prosody.syllabify(first), prosody.syllabify(second)
    assert isinstance(left, Ready) and isinstance(right, Ready)
    assert prosody.rhymes(left.value.syllables, right.value.syllables) is expected
