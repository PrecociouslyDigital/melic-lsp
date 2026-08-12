"""Manual annotation: payload parsing, scope resolution, and the validation.

No prosodic needed. Scope resolution is worth testing because getting it wrong is
silent — an override would simply apply to the wrong lines, and the counts it
produced would look perfectly plausible.
"""

from __future__ import annotations

import pytest

from melic_lsp.chordpro import parse_document
from melic_lsp.overrides import Override, Problem, collect, _parse, _parse_scheme
from melic_lsp.sections import group
from melic_lsp.types import Stress


def table(text: str):
    document = parse_document(text)
    return collect(document, group(document))


# --- Payload grammar ---------------------------------------------------------


def test_syllables_without_stress_leave_it_to_be_inherited() -> None:
    parsed = _parse(0, "chariot = cha ri ot")
    assert isinstance(parsed, Override)
    assert parsed.texts == ("cha", "ri", "ot")
    assert parsed.stresses is None


def test_stress_glyphs_are_the_same_ones_the_signature_prints() -> None:
    parsed = _parse(0, "chariot = +cha -ri ^ot")
    assert isinstance(parsed, Override)
    assert parsed.stresses == (Stress.PRIMARY, Stress.NONE, Stress.SECONDARY)


def test_a_partly_marked_word_treats_the_rest_as_unstressed() -> None:
    parsed = _parse(0, "chariot = +cha ri ot")
    assert isinstance(parsed, Override)
    assert parsed.stresses == (Stress.PRIMARY, Stress.NONE, Stress.NONE)


def test_lookup_is_case_insensitive() -> None:
    overrides = table("{x_melic_word: Chariot = cha ri ot}\nsweet chariot\n")
    assert overrides.find("CHARIOT", 1) is not None


@pytest.mark.parametrize(
    "payload",
    [
        "chariot cha ri ot",  # no '='
        "= cha ri ot",  # no word
        "chariot = ",  # no syllables
        "chariot = + cha",  # a mark with nothing after it
    ],
)
def test_malformed_payloads_are_reported_not_guessed(payload: str) -> None:
    assert isinstance(_parse(0, payload), Problem)


def test_a_misspelling_is_caught_even_at_the_right_length() -> None:
    """Stricter than the length-only tiling check, which this would sail through."""
    parsed = _parse(0, "chariot = cha ri to")
    assert isinstance(parsed, Problem)
    assert "charito" in parsed.message


# --- Scope -------------------------------------------------------------------

SONG = """\
{x_melic_word: fire = fi re}
{start_of_verse: One}
{x_melic_word_section: fire = +fire}
burning fire
still fire
{end_of_verse}
{start_of_verse: Two}
{x_melic_word_line: fire = fi re}
cold fire
last fire
{end_of_verse}
"""


def test_document_scope_reaches_everywhere() -> None:
    overrides = table("{x_melic_word: fire = fi re}\nburning fire\n")
    found = overrides.find("fire", 1)
    assert found is not None and found.texts == ("fi", "re")


def test_section_scope_beats_document_scope() -> None:
    overrides = table(SONG)
    inside = overrides.find("fire", 3)
    assert inside is not None and inside.texts == ("fire",)


def test_section_scope_does_not_leak_into_the_next_section() -> None:
    overrides = table(SONG)
    later = overrides.find("fire", 9)
    assert later is not None and later.texts == ("fi", "re")


def test_line_scope_binds_to_the_next_lyric_line_only() -> None:
    overrides = table(SONG)
    assert overrides.find("fire", 8) is not None  # "cold fire"
    on_the_line_after = overrides.find("fire", 9)  # "last fire"
    assert on_the_line_after is not None
    # Falls back to the document rule rather than the line one.
    assert on_the_line_after.row == 0


def test_an_override_covering_nothing_is_reported() -> None:
    overrides = table("burning fire\n{x_melic_word_line: fire = fi re}\n")
    assert any("covers no lyric line" in problem.message for problem in overrides.problems)


def test_a_document_with_no_annotations_costs_nothing() -> None:
    assert table("burning fire\n").empty


# --- Declared rhyme schemes ---------------------------------------------------

QUATRAIN = """\
The morning water running cold,
The windows rattling with the rain,
The willow turning brown and gold,
The furrows lying bare and plain,
"""

COUPLET = "Sing it low,\nSing it long,\n"

SONG_WITH_SECTIONS = (
    f"{{start_of_verse}}\n{QUATRAIN}{{end_of_verse}}\n\n"
    f"{{start_of_chorus}}\n{COUPLET}{{end_of_chorus}}\n"
)


@pytest.mark.parametrize(
    "payload,expected",
    [
        ("ABAB", (None, "ABAB")),
        ("abab", (None, "ABAB")),
        ("chorus = ABAB", ("chorus", "ABAB")),
        # Renamed into first-appearance order, so a declaration and a computed
        # scheme string are comparable as written.
        ("BABA", (None, "ABAB")),
        ("AABX", (None, "AAXX")),
    ],
)
def test_scheme_payloads(payload: str, expected: tuple[str | None, str]) -> None:
    assert _parse_scheme(0, payload) == expected


@pytest.mark.parametrize("payload", ["AB-AB", "AB AB", "", "= ABAB", "4 lines"])
def test_malformed_schemes_are_reported_not_guessed(payload: str) -> None:
    assert isinstance(_parse_scheme(0, payload), Problem)


VERSE = f"{{start_of_verse}}\n{QUATRAIN}{{end_of_verse}}\n"
CHORUS = f"{{start_of_chorus}}\n{COUPLET}{{end_of_chorus}}\n"


def test_a_bare_pattern_covers_the_stanzas_of_its_own_section() -> None:
    declared = table(f"{{start_of_verse}}\n{{x_melic_scheme: ABAB}}\n{QUATRAIN}{{end_of_verse}}\n")
    assert [(row, found.pattern) for row, found in declared.schemes.items()] == [
        (2, "ABAB")
    ]


def test_a_pattern_written_between_sections_covers_the_next_one() -> None:
    """Same rule as the word annotations: "this verse", written above the verse."""
    declared = table(f"{{x_melic_scheme: ABAB}}\n{VERSE}")
    assert 2 in declared.schemes


def test_the_kind_form_reaches_every_section_of_that_kind() -> None:
    declared = table(f"{{x_melic_scheme: chorus = AA}}\n{SONG_WITH_SECTIONS}{CHORUS}")
    assert [found.pattern for found in declared.schemes.values()] == ["AA", "AA"]


def test_a_stanza_of_another_length_is_not_covered() -> None:
    """Holding a couplet to ABAB would compare two things that were never the shape."""
    declared = table(f"{{x_melic_scheme: chorus = ABAB}}\n{SONG_WITH_SECTIONS}")
    assert not declared.schemes
    assert any("No 4-line stanza" in problem.message for problem in declared.problems)
