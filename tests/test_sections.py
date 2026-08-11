"""Section grouping. Pure, prosodic-free, and worth testing because getting it
wrong is silent: the outline and the compare view would simply line up the wrong
lines against each other."""

from __future__ import annotations

from melic_lsp.chordpro import parse_document
from melic_lsp.sections import IMPLICIT, group, stacks


def sections(text: str):
    return group(parse_document(text))


def test_explicit_environments_become_labelled_sections() -> None:
    found = sections(
        "{start_of_verse: Verse 1}\nfirst\nsecond\n{end_of_verse}\n"
        "{start_of_chorus}\nrefrain\n{end_of_chorus}\n"
    )
    assert [(s.kind, s.title, len(s.lines)) for s in found] == [
        ("verse", "Verse 1", 2),
        ("chorus", "Chorus", 1),
    ]


def test_blank_lines_split_stanzas_when_there_are_no_directives() -> None:
    found = sections("one\ntwo\n\nthree\nfour\n")
    assert [s.kind for s in found] == [IMPLICIT, IMPLICIT]
    assert [len(s.lines) for s in found] == [2, 2]


def test_a_blank_line_inside_an_environment_is_just_breathing_room() -> None:
    """Inside {sov}...{eov} the author said where the section ends; believe them."""
    found = sections("{sov}\none\n\ntwo\n{eov}\n")
    assert len(found) == 1 and len(found[0].lines) == 2


def test_verbatim_blocks_never_reach_a_section() -> None:
    found = sections("{sot}\ne|--0--|\n{eot}\n\nsung line\n")
    assert [line.lyric for s in found for line in s.lines] == ["sung line"]


def test_stacks_keep_only_kinds_with_something_to_compare() -> None:
    found = sections(
        "{sov: A}\none\n{eov}\n{soc}\nrefrain\n{eoc}\n{sov: B}\ntwo\nthree\n{eov}\n"
    )
    grouped = stacks(found)
    assert [s.kind for s in grouped] == ["verse"]
    assert [section.title for section in grouped[0].sections] == ["A", "B"]


def test_ragged_sections_stay_ragged() -> None:
    """An extra line is the divergence worth seeing, not something to pad away."""
    found = sections("{sov: A}\none\n{eov}\n{sov: B}\ntwo\nthree\n{eov}\n")
    rows = stacks(found)[0].rows
    assert len(rows) == 2
    assert rows[1][0] is None
    assert rows[1][1] is not None and rows[1][1].lyric == "three"
