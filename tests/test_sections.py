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


def test_a_blank_line_inside_an_environment_splits_stanzas_not_sections() -> None:
    """Inside {sov}...{eov} the author said where the section ends; believe them.

    The blank still means something — it is where one stanza stops and the next
    begins, which is the scope a rhyme scheme is measured over.
    """
    (found,) = sections("{sov}\none\n\ntwo\n{eov}\n")
    assert [len(stanza.lines) for stanza in found.stanzas] == [1, 1]
    assert len(found.lines) == 2


def test_a_blank_line_outside_an_environment_still_splits_sections() -> None:
    """With no directive there is nothing else to go on, so a stanza is a section."""
    found = sections("one\n\ntwo\n")
    assert [len(s.stanzas) for s in found] == [1, 1]


def test_a_four_quatrain_verse_is_four_stanzas_in_one_section() -> None:
    """The case this exists for: a rhyme scheme across all sixteen lines is noise."""
    quatrains = "\n\n".join("\n".join("abcd") for _ in range(4))
    (found,) = sections(f"{{sov: Verse 1}}\n{quatrains}\n{{eov}}\n")
    assert found.title == "Verse 1"
    assert [len(stanza.lines) for stanza in found.stanzas] == [4, 4, 4, 4]
    assert (found.start_row, found.end_row) == (1, 19)


def test_a_custom_environment_names_its_own_section() -> None:
    """{start_of_intro} is as legal as a verse, and just as comparable."""
    found = sections("{start_of_intro}\none\n{end_of_intro}\n")
    assert [(s.kind, s.title) for s in found] == [("intro", "Intro")]


def test_the_modern_label_syntax_is_unwrapped() -> None:
    found = sections('{sov: label="Verse 1"}\none\n{eov}\n')
    assert [s.title for s in found] == ["Verse 1"]


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
    (block,) = stacks(found)[0].blocks
    assert [_lyrics(row) for row in block] == [("one", "two"), (None, "three")]


def test_stanzas_line_up_against_stanzas() -> None:
    """A long verse and a short one compare stanza 2 against stanza 2.

    Aligning on the flat line index would pair "b1" with "a2" and drift from
    there — which is the whole reason a verse holds stanzas.
    """
    found = sections(
        "{sov: A}\na1\na2\n\nb1\nb2\n{eov}\n{sov: B}\nc1\n\nd1\nd2\n{eov}\n"
    )
    blocks = stacks(found)[0].blocks
    assert [[_lyrics(row) for row in block] for block in blocks] == [
        [("a1", "c1"), ("a2", None)],
        [("b1", "d1"), ("b2", "d2")],
    ]


def _lyrics(row: tuple) -> tuple[str | None, ...]:
    return tuple(line.lyric if line is not None else None for line in row)
