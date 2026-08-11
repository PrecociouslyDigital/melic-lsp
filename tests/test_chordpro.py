"""Tests for parsing and position mapping. No prosodic, so these run in milliseconds."""

from pathlib import Path

import pytest

from melic_lsp.chordpro import (
    Blank,
    Category,
    Comment,
    Directive,
    EnvKind,
    Lyric,
    Verbatim,
    lookup,
    parse_document,
    parse_lyric,
)
from melic_lsp.types import LyricCol

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_FILES = sorted(FIXTURES.glob("*.cho"))


def fixture_lyrics() -> list[Lyric]:
    return [
        line
        for path in FIXTURE_FILES
        for line in parse_document(path.read_text()).lyrics()
    ]


# --- The test that carries the project ---------------------------------------


def test_every_lyric_offset_maps_back_to_the_same_character() -> None:
    """Round-trip every single offset in every fixture lyric line.

    If this passes, the highest-risk code in the repo is correct: chord-split
    words, leading and trailing chords, chord-only lines, unicode and apostrophes
    are all covered by real text rather than by cases I thought to enumerate.
    """
    checked = 0
    for line in fixture_lyrics():
        for offset in range(len(line.lyric)):
            ranges = line.spans.to_source(LyricCol(offset), LyricCol(offset + 1))
            assert len(ranges) == 1, f"{line.text!r} offset {offset} split unexpectedly"
            got = line.text[ranges[0].start : ranges[0].end]
            assert got == line.lyric[offset], (
                f"line {line.row} offset {offset}: mapped to {got!r}, "
                f"expected {line.lyric[offset]!r} in {line.text!r}"
            )
            checked += 1
    assert checked > 200, "fixtures got thinner than the test expects"


def test_multi_character_ranges_reassemble_in_order() -> None:
    """A range crossing a chord yields several source ranges that still join back."""
    for line in fixture_lyrics():
        for start in range(len(line.lyric)):
            for end in range(start + 1, len(line.lyric) + 1):
                ranges = line.spans.to_source(LyricCol(start), LyricCol(end))
                joined = "".join(line.text[r.start : r.end] for r in ranges)
                assert joined == line.lyric[start:end]


def test_chord_splits_a_word_into_two_source_ranges() -> None:
    line = parse_lyric(0, "sweet [G]chari[D]ot,")
    assert line.lyric == "sweet chariot,"
    start = line.lyric.index("chariot")
    ranges = line.spans.to_source(LyricCol(start), LyricCol(start + len("chariot")))
    assert len(ranges) == 2, "the [D] interrupts the word, so it spans two runs"
    assert "".join(line.text[r.start : r.end] for r in ranges) == "chariot"


def test_empty_lyric_range_maps_to_nothing() -> None:
    line = parse_lyric(0, "Swing [D]low")
    assert line.spans.to_source(LyricCol(3), LyricCol(3)) == []


# --- Line classification -----------------------------------------------------


@pytest.mark.parametrize(
    "text,kind",
    [
        ("   ", Blank),
        ("# a comment", Comment),
        ("  # indented comment", Comment),
        ("{title: Song}", Directive),
        ("{soc}", Directive),
        ("Swing [D]low", Lyric),
        ("[D]", Lyric),
        ("no chords here", Lyric),
    ],
)
def test_line_classification(text: str, kind: type) -> None:
    (line,) = parse_document(text).lines
    assert isinstance(line, kind)


@pytest.mark.parametrize(
    "text,name,value",
    [
        ("{title: Swing Low}", "title", "Swing Low"),
        ("{t:Swing Low}", "t", "Swing Low"),
        ("{start_of_verse: Verse 1}", "start_of_verse", "Verse 1"),
        ("{soc}", "soc", None),
        ("{new_page}", "new_page", None),
        ("{comment: watch the D}", "comment", "watch the D"),
    ],
)
def test_directive_parsing(text: str, name: str, value: str | None) -> None:
    (line,) = parse_document(text).lines
    assert isinstance(line, Directive)
    assert (line.name, line.value) == (name, value)
    assert line.text[line.name_range.start : line.name_range.end].lower() == name


@pytest.mark.parametrize("sep", ["\n", "\r\n", "\r"])
def test_rows_track_editor_line_breaks(sep: str) -> None:
    doc = parse_document(sep.join(["Swing [D]low", "sweet [G]chariot"]))
    assert [line.row for line in doc.lines] == [0, 1]


@pytest.mark.parametrize("oddity", ["\x0c", "\x0b", " ", ""])
def test_rows_ignore_characters_editors_do_not_break_on(oddity: str) -> None:
    """str.splitlines() would split here and drift every row below it."""
    doc = parse_document(f"a{oddity}b\nsecond line")
    assert [line.row for line in doc.lines] == [0, 1]


def test_unknown_directive_has_no_spec() -> None:
    (line,) = parse_document("{titel: typo}").lines
    assert isinstance(line, Directive) and line.spec is None


def test_custom_directives_pass_through() -> None:
    (line,) = parse_document("{x_melic_note: anything}").lines
    assert isinstance(line, Directive)
    assert line.spec is not None and line.spec.category is Category.CUSTOM


def test_unclosed_directive_is_flagged_not_dropped() -> None:
    (line,) = parse_document("{title: Swing Low").lines
    assert isinstance(line, Directive) and not line.closed


# --- Environments ------------------------------------------------------------


def test_tab_contents_are_verbatim_and_lyrics_resume_after() -> None:
    doc = parse_document("{sot}\ne|--0--2--|\n{eot}\nBack to [C]lyrics.")
    kinds = [type(line) for line in doc.lines]
    assert kinds == [Directive, Verbatim, Directive, Lyric]
    assert doc.problems == ()


def test_trailing_newline_leaves_the_final_empty_line_the_editor_shows() -> None:
    doc = parse_document("Swing [D]low\n")
    assert [type(line) for line in doc.lines] == [Lyric, Blank]


def test_chorus_contents_are_analysed() -> None:
    doc = parse_document("{soc}\nSwing [D]low\n{eoc}\n")
    assert isinstance(doc.lines[1], Lyric)


@pytest.mark.parametrize(
    "text,count",
    [
        ("{soc}\nline\n{eoc}\n", 0),
        ("{soc}\nline\n", 1),
        ("{eoc}\n", 1),
        ("{sot}\ntab\n{eoc}\n", 2),
    ],
)
def test_unmatched_environments_are_reported(text: str, count: int) -> None:
    assert len(parse_document(text).problems) == count


def test_alias_and_canonical_resolve_to_one_spec() -> None:
    assert lookup("soc") is lookup("start_of_chorus")
    assert lookup("t") is lookup("title")
    spec = lookup("sot")
    assert spec is not None and spec.env is not None
    assert spec.env.kind is EnvKind.VERBATIM


# --- Chords ------------------------------------------------------------------


def test_chord_positions_and_onsets() -> None:
    line = parse_lyric(0, "Swing [D]low, sweet [G]chari[D]ot,")
    assert [c.name for c in line.chords] == ["D", "G", "D"]
    for chord in line.chords:
        assert line.text[chord.source.start : chord.source.end] == f"[{chord.name}]"
        # The onset is the lyric column the chord sits in front of.
        assert line.lyric[chord.lyric : chord.lyric + 3] in ("low", "cha", "ot,")


@pytest.mark.parametrize(
    "chord_column,split",
    [(0, False), (3, False), (7, False), (1, True), (2, True)],
)
def test_a_chord_on_a_syllable_boundary_does_not_split_it(
    chord_column: int, split: bool
) -> None:
    """The off-by-one the chord-aware reading turns on.

    A chord landing *between* syllables is the good case — that is the whole point
    of preferring it — so only strictly-interior columns may count as a split.
    """
    from melic_lsp.analysis import _splits
    from melic_lsp.types import RawSyllable, Stress, tile

    # "cat" + "nip": boundaries at 0, 3 and 6, offset to lyric column 1.
    word = tile("catnip", [RawSyllable(t, "", Stress.NONE) for t in ("cat", "nip")])
    counted = _splits(word, LyricCol(1), [LyricCol(chord_column + 1)])
    assert bool(counted) is split


def test_words_are_located_in_lyric_space() -> None:
    line = parse_lyric(0, "Comin' for to [A7]carry me [D]home.")
    words = line.words()
    assert [w.token for w in words] == ["Comin'", "for", "to", "carry", "me", "home"]
    for word in words:
        assert line.lyric[word.start : word.end] == word.token
