"""End-rhyme detection, using only cached word data — no Text, no metrical parse.

Prosodic's own calibration counts perfect and slant as rhyme and leaves assonance
out: including it buys almost no extra recall for three times the false positives.
:func:`scheme` follows that to the letter, so a label from it means the two lines
really do chime.

:func:`solve` is the sanctioned relaxation, and it needs the whole song to be one.
Read alone, *pterodactyl* against *fractal* is a near miss not worth calling a
rhyme — same vowel, a coda a little off — and counting every such pair is the
false-positive flood the calibration warns about. Read against a stanza that already
rhymes, or a shape its sibling stanzas spell too, the same pair is the obvious
reading. So a near miss is admitted only where the structure around it vouches for
one, and it is marked ``≈`` rather than quietly promoted to perfect.

How two lines chime is kept, not collapsed to a boolean: "B~" says the pairing is a
slant rhyme, "B=" that the line simply ends on the same word again.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from string import ascii_uppercase
from typing import Literal

from . import prosody
from .chordpro import Lyric
from .types import Ready, Syllabified

UNRHYMED = "X"
"""Stands in for a line that chimes with nothing, in a scheme string."""

type SlantScope = Literal["strict", "contextual"]
"""Which pass labels a document: the calibrated one alone, or the solver on top."""


class Chime(Enum):
    """How closely two endings sound alike."""

    PERFECT = ""
    """The clean case carries no mark; it is the default reading of a letter."""
    SLANT = "~"
    CONTEXTUAL = "≈"
    """A near miss the song's structure vouches for. Kept apart from SLANT because
    the reason to believe it is different, and so is how far to trust it."""
    IDENTICAL = "="
    """The same word again. Rime riche, and in a refrain, usually the point."""


@dataclass(frozen=True)
class Rhyme:
    letter: str
    chime: Chime

    @property
    def label(self) -> str:
        """What the margin shows: "A", "A~", "A="."""
        return f"{self.letter}{self.chime.value}"


DESCRIPTION = {
    Chime.PERFECT: "perfect rhyme",
    Chime.SLANT: "slant rhyme",
    Chime.CONTEXTUAL: "near rhyme, admitted by the song's structure",
    Chime.IDENTICAL: "the same word repeated",
}
"""The mark in words, for tooltips and hover — anywhere with room for more than a glyph."""


def _ending(line: Lyric, lang: str) -> Syllabified | None:
    """The line's last word, which is what an end-rhyme is made of."""
    words = line.words()
    if not words:
        return None
    result = prosody.syllabify(words[-1].token, lang)
    return result.value.syllables if isinstance(result, Ready) else None


def classify(first: Syllabified, second: Syllabified) -> Chime | None:
    """How two endings chime, or None if they do not.

    Prosodic reports that a word does not rhyme with itself, which is right about
    rhyme and wrong about songs: a refrain that ends "home" every time is still the
    same slot in the pattern. A repeated ending counts here, and says so.
    """
    if first.token.casefold() == second.token.casefold():
        return Chime.IDENTICAL
    match prosody.rhyme_type(first, second):
        case "perfect":
            return Chime.PERFECT
        case "slant":
            return Chime.SLANT
        case _:
            return None


# --- The strict pass ----------------------------------------------------------


@dataclass(frozen=True)
class _Group:
    """Lines that chime, and the ending the rest of them are measured against."""

    opener: Syllabified
    members: tuple[tuple[int, Chime], ...]

    @property
    def row(self) -> int:
        """Where the group opens — the order letters are handed out in.

        Not simply the first member: the solver may add a line that sits above the
        one the group was built around.
        """
        return min(row for row, _ in self.members)


def _strict(lines: Sequence[Lyric], lang: str) -> list[_Group]:
    """The calibrated pass, singletons and all.

    Every line joins the first group it chimes with, measured against the line that
    opened it — the natural reference, which wears the bare letter, and every later
    member says how it relates to it. Lines chiming with nothing come back as groups
    of one: :func:`scheme` drops them, and :func:`solve` starts from them.
    """
    openers: list[Syllabified] = []
    members: list[list[tuple[int, Chime]]] = []

    for line in lines:
        ending = _ending(line, lang)
        if ending is None:
            continue
        for index, opener in enumerate(openers):
            chime = classify(ending, opener)
            if chime is not None:
                members[index].append((line.row, chime))
                break
        else:
            openers.append(ending)
            members.append([(line.row, Chime.PERFECT)])

    return [_Group(opener, tuple(rows)) for opener, rows in zip(openers, members)]


def _label(groups: Sequence[_Group]) -> dict[int, Rhyme]:
    """Hand out letters, so a repeated letter means those lines rhyme.

    In opening order, giving the familiar ABAB. Lines that chime with nothing are
    simply absent: an annotation on every line saying "this one is unlike the others"
    would be noise on most of them. The sort is what the strict pass gets for free
    and the solver does not — a contextual group can open above a strict one.
    """
    letters = iter(ascii_uppercase)
    return {
        row: Rhyme(letter, chime)
        for group in sorted(
            (group for group in groups if len(group.members) > 1),
            key=lambda group: group.row,
        )
        for letter in [next(letters, "?")]
        for row, chime in group.members
    }


def scheme(lines: list[Lyric], lang: str = "en") -> dict[int, Rhyme]:
    """Label one stanza's rhymes, counting only what prosodic's calibration counts."""
    return _label(_strict(lines, lang))


def scheme_string(lines: list[Lyric], labels: dict[int, Rhyme]) -> str:
    """The section's shape as the familiar ``ABAB``, or "" when nothing rhymes.

    The letters are the ones the margin shows, minus their quality marks: a slant
    rhyme still fills that slot, and ``ABAB`` is about shape.
    """
    if not any(line.row in labels for line in lines):
        return ""
    return "".join(
        labels[line.row].letter if line.row in labels else UNRHYMED
        for line in lines
    )


_PATTERN = re.compile(r"[A-Za-z]+")


def canonical_pattern(text: str) -> str | None:
    """Read a written rhyme pattern — ``ABAB``, ``abab``, ``BABA`` — as one shape.

    The letters are renamed into first-appearance order, so that a pattern someone
    wrote and a scheme string we computed can simply be compared. ``X`` marks a line
    rhyming with nothing, and so does any letter used only once: a group of one is
    never lettered, so no stanza could ever spell such a shape. None when the text is
    not a pattern at all.
    """
    if _PATTERN.fullmatch(text) is None:
        return None
    written = text.upper()
    letters = iter(ascii_uppercase)
    renamed = {
        slot: letter
        for slot in dict.fromkeys(written)
        if slot != UNRHYMED and written.count(slot) > 1
        for letter in [next(letters, "?")]
    }
    return "".join(renamed.get(slot, UNRHYMED) for slot in written)


# --- The solver ---------------------------------------------------------------

CONTEXTUAL_NUC_MAX = 0.05
"""Nucleus identity: the bound prosodic sets for perfect rhyme and for assonance
alike. A weak edge may forgive a consonant; it never forgives a drifted vowel."""

CONTEXTUAL_CODA_MAX = 0.25
"""How far past the perfect region's coda bound (0.15) a near miss may still sit.
Measured: pterodactyl/fractal 0.23, time/line 0.21 and crazy/baby 0.19 are in;
body/probably 0.40 and day/late 1.0 are out."""

MAX_FREE_LINES = 6
"""Bounds the pairs to measure: every unrhymed line is compared with every other one
and with every strict group, so a stanza with more than this keeps its strict scheme
rather than being solved."""

MAX_CANDIDATES = 256
"""Bounds the shapes to weigh, which the free-line count alone does not: a line with
a weak edge to several groups multiplies the readings rather than adding to them.
Real stanzas produce a handful — a dozen at the outside — and one that produces
hundreds has no obvious reading to find, so it keeps its strict scheme too."""


def contextual_chime(first: Syllabified, second: Syllabified) -> Chime | None:
    """The solver's one admission rule: same nucleus, near coda."""
    return None if _weak_cost(first, second) is None else Chime.CONTEXTUAL


def _weak_cost(first: Syllabified, second: Syllabified) -> float | None:
    """What this weak edge costs to use, or None when it is not on offer.

    The cost is the coda distance — how far the near miss actually missed — so that
    between two otherwise equally good readings, the closer chime wins.
    """
    distance = prosody.rime_distance_nc(first, second)
    if distance is None:
        return None
    nucleus, coda = distance
    return coda if nucleus <= CONTEXTUAL_NUC_MAX and coda <= CONTEXTUAL_CODA_MAX else None


@dataclass(frozen=True)
class _Candidate:
    """One reading of a stanza, and what the weak edges in it cost."""

    groups: tuple[_Group, ...]
    shape: str
    cost: float

    @property
    def labelled(self) -> int:
        return sum(1 for slot in self.shape if slot != UNRHYMED)


def _candidate(lines: Sequence[Lyric], groups: Sequence[_Group], cost: float) -> _Candidate:
    return _Candidate(tuple(groups), scheme_string(list(lines), _label(groups)), cost)


def _candidates(lines: Sequence[Lyric], lang: str) -> list[_Candidate]:
    """Every reading of this stanza the phonetics allow, the strict one first.

    Strict groups are never split or reshuffled — they are what the calibration
    says — so the solver's business is only the lines left over. Each of those may
    stay free, join a strict group, or pair with another free line, wherever a weak
    edge exists. A line with no weak edge at all has one option, which is what keeps
    this enumeration small in practice.

    Nothing here consults another stanza, which is why the round that chooses
    between these has no ordering effects.
    """
    groups = _strict(lines, lang)
    strict = [group for group in groups if len(group.members) > 1]
    free = [group for group in groups if len(group.members) == 1]
    base = _candidate(lines, groups, 0.0)
    if not free or len(free) > MAX_FREE_LINES:
        return [base]

    to_group = {
        (spare, target): cost
        for spare, line in enumerate(free)
        for target, group in enumerate(strict)
        for cost in [_weak_cost(line.opener, group.opener)]
        if cost is not None
    }
    to_free = {
        (first, second): cost
        for first in range(len(free))
        for second in range(first + 1, len(free))
        for cost in [_weak_cost(free[first].opener, free[second].opener)]
        if cost is not None
    }

    found = [base]

    def build(joins: dict[int, int], pairs: tuple[tuple[int, int], ...]) -> list[_Group]:
        """Fold the accepted weak edges into the groups the strict pass left."""
        joined = [list(group.members) for group in strict]
        for spare, target in joins.items():
            joined[target].append((free[spare].row, Chime.CONTEXTUAL))
        paired = set(joins) | {index for pair in pairs for index in pair}
        return (
            [
                _Group(group.opener, tuple(members))
                for group, members in zip(strict, joined)
            ]
            + [
                # The earlier line opens the group and wears the bare letter, as it
                # does everywhere else.
                _Group(
                    free[first].opener,
                    free[first].members + ((free[second].row, Chime.CONTEXTUAL),),
                )
                for first, second in pairs
            ]
            + [line for index, line in enumerate(free) if index not in paired]
        )

    def extend(
        index: int, joins: dict[int, int], pairs: tuple[tuple[int, int], ...], cost: float
    ) -> None:
        """Walk the free lines in order, choosing what becomes of each."""
        if len(found) > MAX_CANDIDATES:
            return
        if index == len(free):
            if joins or pairs:
                found.append(_candidate(lines, build(joins, pairs), cost))
            return
        if any(index == second for _, second in pairs):
            extend(index + 1, joins, pairs, cost)  # already spoken for
            return
        extend(index + 1, joins, pairs, cost)  # stays free
        for target in range(len(strict)):
            edge = to_group.get((index, target))
            if edge is not None:
                extend(index + 1, {**joins, index: target}, pairs, cost + edge)
        for other in range(index + 1, len(free)):
            edge = to_free.get((index, other))
            if edge is not None:
                extend(index + 1, joins, pairs + ((index, other),), cost + edge)

    extend(0, {}, (), 0.0)
    # All of them or none: a truncated list would make the reading depend on the
    # order the shapes happened to be enumerated in.
    return found if len(found) <= MAX_CANDIDATES else [base]


def solve(
    stanzas: Sequence[Sequence[Lyric]],
    lang: str = "en",
    declared: Sequence[str | None] = (),
) -> dict[int, Rhyme]:
    """Label a whole song at once, letting its structure vouch for near rhymes.

    Two rounds and no iteration. First every stanza is read strictly and every
    reading a weak edge could reach is enumerated; then each stanza picks one, which
    is where the rest of the song gets a say. The strict reading is free and always
    on the table, so an admitted near rhyme is one that was both corroborated and
    strictly better — never a tie broken towards saying more.

    ``declared`` is the pattern each stanza was told to have, positionally, from
    ``{x_melic_scheme}``. It is an expectation, not an instruction: it corroborates
    an edge the phonetics already allow and cannot conjure one they refuse.
    """
    readings = [_candidates(list(stanza), lang) for stanza in stanzas]
    reachable = [
        {candidate.shape for candidate in stanza if candidate.shape}
        for stanza in readings
    ]

    labels: dict[int, Rhyme] = {}
    for index, candidates in enumerate(readings):
        pattern = declared[index] if index < len(declared) else None
        elsewhere = reachable[:index] + reachable[index + 1 :]
        labels.update(_label(_choose(candidates, pattern, elsewhere).groups))
    return labels


def _choose(
    candidates: Sequence[_Candidate],
    declared: str | None,
    elsewhere: Sequence[set[str]],
) -> _Candidate:
    """Pick one reading of a stanza: the most structure the song as a whole supports.

    A weak edge has to earn its place, so an augmented reading is considered at all
    only when something outside the pair vouches for it — the stanza demonstrably
    rhymes already, another stanza could spell the same shape, or the file declares
    it. Between those, the shape more of the song can spell wins, then the one
    labelling more lines, then the closer chime.

    A shape of "" says nothing rhymes here, which is not a structure to repeat, so
    it collects no votes; otherwise every unrhymed stanza in a song would vouch for
    every other one.
    """
    strict = candidates[0]
    votes = {
        shape: sum(shape in other for other in elsewhere)
        for shape in {candidate.shape for candidate in candidates}
        if shape
    }

    def supported(candidate: _Candidate) -> bool:
        return (
            candidate is strict
            or bool(strict.shape)
            or votes.get(candidate.shape, 0) > 0
            or candidate.shape == declared
        )

    return max(
        (candidate for candidate in candidates if supported(candidate)),
        key=lambda candidate: (
            candidate.shape == declared,
            votes.get(candidate.shape, 0),
            candidate.labelled,
            -candidate.cost,
        ),
    )
