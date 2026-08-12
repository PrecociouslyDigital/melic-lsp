"""The cross-line rules, with syllable counts dictated rather than measured.

Every rule is arithmetic over counts and rhyme labels, so this file builds its own
analyses and never loads the dictionary. That is not only for speed: made-up counts
sit exactly on a tolerance boundary, which is where these rules are worth testing,
and the refusals — a word with no pronunciation, a line still warming — can be posed
directly instead of arranged for.

The lyric text is written for the tests, and says nothing the counts do not.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import pytest
from lsprotocol import types as lsp

from melic_lsp.analysis import (
    DocumentAnalysis,
    LineAnalysis,
    PlacedSyllable,
    Unresolved,
)
from melic_lsp.chordpro import parse_document
from melic_lsp.features import hints
from melic_lsp.overrides import EMPTY, Overrides, SchemeDeclaration
from melic_lsp.rhyme import Chime, Rhyme
from melic_lsp.sections import group
from melic_lsp.settings import HintSettings
from melic_lsp.types import LyricCol, Stress, WordSpan

URI = "file:///song.cho"

SILENT = HintSettings(
    rhyme_scheme_mismatch="off", parallel_line_drift="off", chord_progression_drift="off"
)


def analysed(
    text: str,
    counts: dict[int, int],
    *,
    unresolved: Sequence[int] = (),
    warming: Sequence[int] = (),
    rhymes: dict[int, Rhyme] | None = None,
    schemes: dict[int, SchemeDeclaration] | None = None,
) -> DocumentAnalysis:
    """A whole-document analysis whose counts are whatever the test says they are."""
    document = parse_document(text)
    lines = tuple(
        LineAnalysis(
            line,
            tuple(
                PlacedSyllable(
                    "a", "", Stress.NONE, LyricCol(index), LyricCol(index + 1), True
                )
                for index in range(counts.get(line.row, 0))
            ),
            (Unresolved(WordSpan("x", LyricCol(0)), "no espeak"),)
            if line.row in unresolved
            else (),
            warming=line.row in warming,
        )
        for line in document.lyrics()
    )
    return DocumentAnalysis(
        document,
        tuple(group(document)),
        lines,
        rhymes or {},
        Overrides({}, {}, schemes, ()) if schemes else EMPTY,
    )


def only(model: DocumentAnalysis, rule: str, **settings: object) -> list[lsp.Diagnostic]:
    """Run one rule with the others off, so a case tests what it says it tests."""
    return hints.build(model, replace(SILENT, **{rule: "hint"} | settings), URI)


def rows(items: Sequence[lsp.Diagnostic]) -> list[int]:
    return [item.range.start.line for item in items]


def evidence(item: lsp.Diagnostic) -> list[int]:
    return [
        related.location.range.start.line for related in item.related_information or []
    ]


def rhyming(*labels: str | None, start: int) -> dict[int, Rhyme]:
    """Rhyme labels by row, spelled as the margin shows them: "A", "B≈", None."""
    return {
        start + offset: Rhyme(label[0], Chime(label[1:]))
        for offset, label in enumerate(labels)
        if label is not None
    }


# --- Parallel lines -----------------------------------------------------------

TWO_CHORUSES = """\
{start_of_chorus}
Sing it low, sing it slow,
Carry it home,
{end_of_chorus}

{start_of_chorus}
Sing it low, sing it slow,
Carry it all the long way home,
{end_of_chorus}
"""
"""Choruses at rows 1-2 and 6-7."""


def test_a_line_that_will_not_fit_the_slot_it_matches() -> None:
    items = only(analysed(TWO_CHORUSES, {1: 6, 2: 4, 6: 6, 7: 8}), "parallel_line_drift")
    assert rows(items) == [7]
    assert evidence(items[0]) == [2]
    assert items[0].code == hints.PARALLEL_LINE_DRIFT


def test_one_syllable_is_pickup_note_territory() -> None:
    assert only(analysed(TWO_CHORUSES, {1: 6, 2: 4, 6: 6, 7: 5}), "parallel_line_drift") == []


def test_a_raised_tolerance_silences_it() -> None:
    model = analysed(TWO_CHORUSES, {1: 6, 2: 4, 6: 6, 7: 8})
    assert only(model, "parallel_line_drift", parallel_line_tolerance=4) == []


@pytest.mark.parametrize("floor", [2, 7])
def test_a_word_with_no_pronunciation_refuses_the_comparison(floor: int) -> None:
    """Either side being a floor rather than a total is enough to stay quiet — which
    is also what keeps the CI leg without espeak silent."""
    model = analysed(TWO_CHORUSES, {1: 6, 2: 4, 6: 6, 7: 8}, unresolved=[floor])
    assert only(model, "parallel_line_drift") == []


def test_a_line_still_warming_refuses_the_comparison() -> None:
    model = analysed(TWO_CHORUSES, {1: 6, 2: 4, 6: 6, 7: 8}, warming=[7])
    assert only(model, "parallel_line_drift") == []


def test_stanzas_nobody_named_are_never_stacked() -> None:
    """Without directives every stanza is one implicit kind, and a chorus-shaped
    stanza would be held against a verse-shaped one."""
    undirected = (
        "Sing it low, sing it slow,\nCarry it home,\n\n"
        "Sing it low, sing it slow,\nCarry it all the long way home,\n"
    )
    model = analysed(undirected, {0: 6, 1: 4, 3: 6, 4: 8})
    assert only(model, "parallel_line_drift") == []


def test_a_slot_with_no_counterpart_is_left_alone() -> None:
    ragged = """\
{start_of_chorus}
Carry it home,
{end_of_chorus}

{start_of_chorus}
Carry it home,
Carry it all the long way home,
{end_of_chorus}
"""
    model = analysed(ragged, {1: 4, 5: 4, 6: 12})
    assert only(model, "parallel_line_drift") == []


# --- Severities and the shape of a hint ---------------------------------------


def test_a_rule_set_to_off_does_not_run() -> None:
    model = analysed(TWO_CHORUSES, {1: 6, 2: 4, 6: 6, 7: 8})
    assert hints.build(model, HintSettings(parallel_line_drift="off"), URI) == []


def test_the_severity_is_the_one_the_rule_was_given() -> None:
    model = analysed(TWO_CHORUSES, {1: 6, 2: 4, 6: 6, 7: 8})
    items = only(model, "parallel_line_drift", parallel_line_drift="warning")
    assert items[0].severity is lsp.DiagnosticSeverity.Warning


def test_every_hint_says_where_it_came_from() -> None:
    """The code is the settings key, so a hint you disagree with says where to go."""
    model = analysed(TWO_CHORUSES, {1: 6, 2: 4, 6: 6, 7: 8})
    items = hints.build(model, HintSettings(), URI)
    assert items and all(item.source == "melic" and item.code in RULE_CODES for item in items)


RULE_CODES = {
    hints.RHYME_SCHEME_MISMATCH,
    hints.PARALLEL_LINE_DRIFT,
    hints.CHORD_PROGRESSION_DRIFT,
}


# --- Rhyme scheme -------------------------------------------------------------

FOUR_LINE_CHORUSES = """\
{start_of_chorus}
The morning water running cold,
The windows rattling with the rain,
The willow turning brown and gold,
The furrows lying bare and plain,
{end_of_chorus}

{start_of_chorus}
The morning water running cold,
The windows rattling with the rain,
The willow turning brown and gold,
The furrows under falling snow,
{end_of_chorus}
"""
"""Choruses at rows 1-4 and 8-11."""

ABAB = rhyming("A", "B", "A", "B", start=1)


def test_a_chorus_that_stopped_rhyming_like_the_first_one() -> None:
    labels = ABAB | rhyming("A", "B", "A", None, start=8)
    items = only(analysed(FOUR_LINE_CHORUSES, {}, rhymes=labels), "rhyme_scheme_mismatch")
    assert rows(items) == [8]
    assert (items[0].range.start.line, items[0].range.end.line) == (8, 11)
    assert evidence(items[0]) == [1]
    assert "ABAX" in items[0].message and "ABAB" in items[0].message


def test_a_chorus_that_stopped_rhyming_at_all() -> None:
    items = only(analysed(FOUR_LINE_CHORUSES, {}, rhymes=ABAB), "rhyme_scheme_mismatch")
    assert rows(items) == [8] and "nothing" in items[0].message


def test_a_reference_that_never_rhymed_says_nothing() -> None:
    labels = rhyming("A", "B", "A", "B", start=8)
    assert only(analysed(FOUR_LINE_CHORUSES, {}, rhymes=labels), "rhyme_scheme_mismatch") == []


def test_with_rhyme_labelling_off_the_rule_has_nothing_to_read() -> None:
    assert only(analysed(FOUR_LINE_CHORUSES, {}, rhymes={}), "rhyme_scheme_mismatch") == []


def test_an_unresolved_word_refuses_the_comparison() -> None:
    labels = ABAB | rhyming("A", "B", "A", None, start=8)
    model = analysed(FOUR_LINE_CHORUSES, {}, unresolved=[11], rhymes=labels)
    assert only(model, "rhyme_scheme_mismatch") == []


def test_an_extra_stanza_is_structure_not_drift() -> None:
    song = FOUR_LINE_CHORUSES + "\nThe furrows under falling snow,\nAnd nothing left to sing,\n"
    model = analysed(song, {}, rhymes=ABAB | rhyming("A", "B", "A", "B", start=8))
    assert only(model, "rhyme_scheme_mismatch") == []


DECLARED_CHORUS = """\
{x_melic_scheme: ABAB}
{start_of_chorus}
The morning water running cold,
The windows rattling with the rain,
The willow turning brown and gold,
The furrows under falling snow,
{end_of_chorus}
"""


def test_a_declared_scheme_needs_no_siblings() -> None:
    """One chorus, and it can still be held to what the file says it is."""
    model = analysed(
        DECLARED_CHORUS,
        {},
        rhymes=rhyming("A", "B", "A", None, start=2),
        schemes={2: SchemeDeclaration("ABAB", 0)},
    )
    items = only(model, "rhyme_scheme_mismatch")
    assert rows(items) == [2] and evidence(items[0]) == [0]
    assert "declares" in items[0].message


def test_a_declaration_beats_the_sibling_it_would_otherwise_be_read_against() -> None:
    labels = ABAB | rhyming("A", "B", "A", "B", start=8)
    model = analysed(
        FOUR_LINE_CHORUSES,
        {},
        rhymes=labels,
        schemes={8: SchemeDeclaration("AABB", 12)},
    )
    items = only(model, "rhyme_scheme_mismatch")
    assert rows(items) == [8] and evidence(items[0]) == [12]
    assert "AABB" in items[0].message


# --- Chord progressions -------------------------------------------------------


def progression_song(count: int, kind: str = "verse", start: int = 0) -> str:
    """A section of identical ``[D]…[G]…[D]`` lines, for the group to form over."""
    body = "\n".join(f"[D]sing it {index} [G]all the [D]way," for index in range(count))
    return f"{{start_of_{kind}}}\n{body}\n{{end_of_{kind}}}\n"


FOUR_LINES = progression_song(4)
"""Lines at rows 1-4."""


def test_a_line_that_does_not_fit_the_shape_its_chords_usually_carry() -> None:
    items = only(analysed(FOUR_LINES, {1: 6, 2: 6, 3: 6, 4: 9}), "chord_progression_drift")
    assert rows(items) == [4]
    assert evidence(items[0]) == [1, 2, 3]
    assert items[0].code == hints.CHORD_PROGRESSION_DRIFT


def test_within_tolerance_the_group_says_nothing() -> None:
    model = analysed(progression_song(3), {1: 6, 2: 6, 3: 8})
    assert only(model, "chord_progression_drift") == []


def test_a_group_with_no_majority_has_no_norm() -> None:
    """6, 6, 7, 7 is two readings of the line, not a norm and an outlier."""
    model = analysed(FOUR_LINES, {1: 6, 2: 6, 3: 9, 4: 9})
    assert only(model, "chord_progression_drift") == []


def test_two_lines_are_a_disagreement_not_a_norm() -> None:
    model = analysed(progression_song(2), {1: 6, 2: 20})
    assert only(model, "chord_progression_drift") == []


def test_kinds_never_share_a_group() -> None:
    """A chorus hook and a verse line over the same chords are not the same line —
    which is exactly what the default fixture would trip over."""
    song = progression_song(2) + "\n" + progression_song(2, kind="chorus")
    model = analysed(song, {1: 6, 2: 6, 5: 6, 6: 20})
    assert only(model, "chord_progression_drift") == []


def test_stanzas_nobody_named_share_no_progression_either() -> None:
    """The same reason the stacks skip them: with no name on the section, a chorus
    hook and a verse line over the same chords are pooled as if they were one line."""
    undirected = "\n".join("[D]sing it [G]all the [D]way," for _ in range(4))
    model = analysed(f"{undirected}\n", {0: 6, 1: 6, 2: 6, 3: 20})
    assert only(model, "chord_progression_drift") == []


def test_lines_with_nothing_to_compare_are_excluded() -> None:
    """A chordless line joins no group; a chord-only line is not a short line."""
    song = progression_song(3) + (
        "{start_of_verse}\nno chords here at all,\n[D][G][D]\n{end_of_verse}\n"
    )
    model = analysed(song, {1: 6, 2: 6, 3: 6, 6: 20, 7: 0})
    assert only(model, "chord_progression_drift") == []


def test_the_more_specific_claim_wins() -> None:
    """A line already measured against the line it matches is not told twice."""
    song = progression_song(2) + "\n" + progression_song(2, kind="verse")
    model = analysed(song, {1: 6, 2: 6, 5: 6, 6: 12})
    both = hints.build(model, HintSettings(), URI)
    assert [(item.code, item.range.start.line) for item in both] == [
        (hints.PARALLEL_LINE_DRIFT, 6)
    ]
    assert rows(only(model, "chord_progression_drift")) == [6]
