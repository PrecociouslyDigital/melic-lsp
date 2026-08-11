"""Manual annotation: payload parsing, scope resolution, and the validation.

No prosodic needed. Scope resolution is worth testing because getting it wrong is
silent — an override would simply apply to the wrong lines, and the counts it
produced would look perfectly plausible.
"""

from __future__ import annotations

import pytest

from melic_lsp.chordpro import parse_document
from melic_lsp.overrides import Override, Problem, collect, _parse
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
