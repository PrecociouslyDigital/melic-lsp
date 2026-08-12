"""Cross-line hints — the governed exception to "diagnostics compare nothing".

``diagnostics.py`` refuses to compare one line with another, and the reason still
stands: two verses disagreeing on syllable count might be a mistake or might be the
song, and a squiggle cannot tell. So each rule here carries its own severity,
``melic.hints.<rule>.severity``, ``off`` is a supported answer, and the two
count-based rules carry the tolerance they fire past. The compare view remains the
place to go looking; these only speak where the song has already said what it means.

That is what earns them a place. A rule fires only against evidence the writer put
there: sections they named, a scheme the file declares, three lines agreeing before a
fourth is called out. Each hint names the lines it was measured against in its
related information, so the claim can be checked rather than argued with.

Two silences worth knowing about. Nothing fires while a compared line is warming or
holds a word with no pronunciation — its count is a floor, and comparing a floor
against a total would manufacture a difference out of a missing dictionary entry,
which is also what keeps the CI leg without espeak quiet. And a ``{chorus}`` recall
directive produces no section, so it is passed over: a recall *is* the chorus, and
has nothing to diverge from.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from lsprotocol import types as lsp

from ..analysis import DocumentAnalysis, LineAnalysis
from ..chordpro import Lyric
from ..rhyme import scheme_string
from ..sections import IMPLICIT, Stanza, stacks
from ..settings import HintSettings, Severity
from ..types import SrcCol
from . import diagnostics

RHYME_SCHEME_MISMATCH = "rhymeSchemeMismatch"
PARALLEL_LINE_DRIFT = "parallelLineDrift"
CHORD_PROGRESSION_DRIFT = "chordProgressionDrift"

MIN_PROGRESSION_GROUP = 3
"""Two lines disagreeing is a disagreement. Three have a norm to disagree with."""

RELATED_CAP = 4
"""Past about this many, a list of partners stops being an affordance."""

SEVERITIES: dict[Severity, lsp.DiagnosticSeverity] = {
    "hint": lsp.DiagnosticSeverity.Hint,
    "info": lsp.DiagnosticSeverity.Information,
    "warning": lsp.DiagnosticSeverity.Warning,
}


@dataclass(frozen=True)
class Finding:
    """One rule's claim about one place, before it is dressed as a diagnostic."""

    code: str
    start_row: int
    end_row: int
    """The same row as ``start_row`` for the line-level rules."""
    message: str
    partners: tuple[tuple[int, str], ...] = ()
    """(row, what that row contributes) — the evidence, named."""


def build(
    model: DocumentAnalysis, settings: HintSettings, uri: str
) -> list[lsp.Diagnostic]:
    """Every cross-line hint the settings ask for."""
    by_row = {analysis.line.row: analysis for analysis in model.lines}
    found: list[lsp.Diagnostic] = []

    if settings.rhyme_scheme_mismatch != "off":
        found += _render(
            _scheme_drift(model, by_row), settings.rhyme_scheme_mismatch, model, uri
        )

    claimed: set[int] = set()
    if settings.parallel_line_drift != "off":
        parallel = _parallel_drift(model, by_row, settings.parallel_line_tolerance)
        claimed = {finding.start_row for finding in parallel}
        found += _render(parallel, settings.parallel_line_drift, model, uri)

    if settings.chord_progression_drift != "off":
        progression = _progression_drift(
            model, by_row, settings.chord_progression_tolerance
        )
        found += _render(
            # The more specific claim wins. A line already measured against the line
            # it is meant to match does not also need telling about its chords.
            [f for f in progression if f.start_row not in claimed],
            settings.chord_progression_drift,
            model,
            uri,
        )

    return found


# --- Rhyme scheme -------------------------------------------------------------


@dataclass(frozen=True)
class _Reference:
    """The shape a stanza is held to, and where that came from."""

    pattern: str
    source: str
    """Named in the message: "Chorus", or the scheme the file declares."""
    row: int
    """The line to point at — the declaration, or the sibling stanza."""
    note: str
    """What that line contributes, for the related information."""
    evidence: tuple[int, ...] = ()
    """Rows that must have been analysed through before this comparison means
    anything. A declaration needs none: it is written, not measured."""


def _scheme_drift(
    model: DocumentAnalysis, by_row: dict[int, LineAnalysis]
) -> list[Finding]:
    """Stanzas that do not rhyme the way the song says they do.

    Strongest reference first: a pattern the file declares, then the stanza in the
    same slot of the first section of this kind. A declaration needs no siblings at
    all, so a song with one verse can still be held to what it says it is.
    """
    if not model.rhymes:
        # Either rhyme labelling is off or nothing in this song rhymes; both leave
        # no shape to compare, and one squiggle per stanza saying so would be noise.
        return []

    siblings = _sibling_references(model)
    found: list[Finding] = []
    for section in model.sections:
        for stanza in section.stanzas:
            reference = _declared(model, stanza) or siblings.get(stanza.start_row)
            if reference is None or not reference.pattern:
                continue
            rows = [line.row for line in stanza.lines]
            if not _settled(rows + list(reference.evidence), by_row):
                continue
            shape = scheme_string(list(stanza.lines), model.rhymes)
            if shape == reference.pattern:
                continue
            found.append(
                Finding(
                    RHYME_SCHEME_MISMATCH,
                    stanza.start_row,
                    stanza.end_row,
                    f"Rhymes {shape or 'nothing'} here, "
                    f"{reference.pattern} in {reference.source}.",
                    ((reference.row, reference.note),),
                )
            )
    return found


def _declared(model: DocumentAnalysis, stanza: Stanza) -> _Reference | None:
    found = model.overrides.schemes.get(stanza.start_row)
    if found is None:
        return None
    return _Reference(
        found.pattern,
        "the scheme this file declares",
        found.row,
        f"{found.pattern} declared here.",
    )


def _sibling_references(model: DocumentAnalysis) -> dict[int, _Reference]:
    """Each stanza's counterpart in the first section of its kind, by start row.

    Only sections the writer named: in an undirected song every blank-line stanza
    lands in one stack, and a chorus-shaped stanza would be held against a
    verse-shaped one. A section with more stanzas than the first has is structure
    rather than drift, and those stanzas simply have nothing to be measured against.
    """
    found: dict[int, _Reference] = {}
    for stack in stacks(list(model.sections)):
        if stack.kind == IMPLICIT:
            continue
        first, *rest = stack.sections
        for section in rest:
            for index, stanza in enumerate(section.stanzas):
                if index >= len(first.stanzas):
                    continue
                counterpart = first.stanzas[index]
                pattern = scheme_string(list(counterpart.lines), model.rhymes)
                found[stanza.start_row] = _Reference(
                    pattern,
                    first.title,
                    counterpart.start_row,
                    f"{first.title} rhymes {pattern or 'nothing'}.",
                    tuple(line.row for line in counterpart.lines),
                )
    return found


# --- Parallel lines -----------------------------------------------------------


def _parallel_drift(
    model: DocumentAnalysis, by_row: dict[int, LineAnalysis], tolerance: int
) -> list[Finding]:
    """Lines filling the same slot in two sections of a kind, that will not fit it.

    The first section of the kind is the reference, because songs are written
    forwards. Stanzas line up against stanzas and lines against lines within them,
    so a section with an extra stanza does not shift everything below it out of
    alignment; a ragged slot has no counterpart and is left alone.
    """
    found: list[Finding] = []
    for stack in stacks(list(model.sections)):
        if stack.kind == IMPLICIT:
            continue
        title = stack.sections[0].title
        for block in stack.blocks:
            for aligned in block:
                reference = _comparable(aligned[0], by_row)
                if reference is None:
                    continue
                for line in aligned[1:]:
                    other = _comparable(line, by_row)
                    if other is None or abs(other.count - reference.count) <= tolerance:
                        continue
                    found.append(
                        Finding(
                            PARALLEL_LINE_DRIFT,
                            other.line.row,
                            other.line.row,
                            f"{other.count} syllables here, against {reference.count} "
                            f"in the line this one lines up with in {title}.",
                            ((reference.line.row, f"{reference.count} syllables here."),),
                        )
                    )
    return found


# --- Chord progressions -------------------------------------------------------


def _progression_drift(
    model: DocumentAnalysis, by_row: dict[int, LineAnalysis], tolerance: int
) -> list[Finding]:
    """Lines sung over the same chords, in sections of one kind, that do not fit.

    The group is keyed on the chord names in order, exactly as typed, with their
    positions ignored — so ``[D]`` and ``[D7]`` are different progressions. That
    loses a few real groups and invents none, and buys no chord theory to be wrong
    about. A group needs a norm before it can say anything: three lines, and a count
    more than half of them agree on.
    """
    kinds = {
        line.row: section.kind for section in model.sections for line in section.lines
    }
    groups: dict[tuple[str, tuple[str, ...]], list[LineAnalysis]] = {}
    for analysis in model.lines:
        kind = kinds.get(analysis.line.row)
        chords = tuple(chord.name.strip() for chord in analysis.line.chords)
        if kind is None or kind == IMPLICIT or not chords or _fit(analysis) is None:
            continue
        groups.setdefault((kind, chords), []).append(analysis)

    found: list[Finding] = []
    for (kind, chords), members in groups.items():
        if len(members) < MIN_PROGRESSION_GROUP:
            continue
        common, hits = Counter(analysis.count for analysis in members).most_common(1)[0]
        if hits * 2 <= len(members):
            # No majority is no norm: lines at 6, 6, 7 and 7 syllables are not
            # evidence about each other, and picking one side would be a coin toss.
            continue
        progression = " ".join(f"[{name}]" for name in chords)
        found += [
            Finding(
                CHORD_PROGRESSION_DRIFT,
                analysis.line.row,
                analysis.line.row,
                f"{analysis.count} syllables over {progression}, where {hits} other "
                f"{kind} lines on the same chords have {common}.",
                tuple(
                    (member.line.row, f"{common} syllables over {progression}.")
                    for member in members
                    if member.count == common
                ),
            )
            for analysis in members
            if abs(analysis.count - common) > tolerance
        ]
    return found


# --- Shared conservatism ------------------------------------------------------


def _fit(analysis: LineAnalysis | None) -> LineAnalysis | None:
    """The analysis of a line fit to be compared, or None if it is not.

    A line still warming, or holding a word with no pronunciation, has a count that
    is a floor rather than a total. A line with no syllables at all is not short —
    it is a line of chords, with nothing sung over it to compare.
    """
    if analysis is None or not analysis.complete or analysis.count == 0:
        return None
    return analysis


def _comparable(
    line: Lyric | None, by_row: dict[int, LineAnalysis]
) -> LineAnalysis | None:
    """The same, for a slot in an alignment, which may hold no line at all."""
    return _fit(by_row.get(line.row)) if line is not None else None


def _settled(rows: Iterable[int], by_row: dict[int, LineAnalysis]) -> bool:
    """True when every one of these lines has been analysed all the way through."""
    found = [by_row.get(row) for row in rows]
    return all(analysis is not None and analysis.complete for analysis in found)


# --- The I/O boundary ---------------------------------------------------------


def _render(
    findings: Sequence[Finding], severity: Severity, model: DocumentAnalysis, uri: str
) -> list[lsp.Diagnostic]:
    """Dress findings as diagnostics: the severity its rule was given, and a code.

    The code is the rule's own name, which is also the settings key that governs it,
    so a hint you disagree with says where to go and turn it off.
    """
    text = {line.row: line.text for line in model.document.lines}

    def span(start: int, end: int) -> lsp.Range:
        return lsp.Range(
            start=lsp.Position(line=start, character=SrcCol(0)),
            end=lsp.Position(line=end, character=SrcCol(len(text.get(end, "")))),
        )

    return [
        lsp.Diagnostic(
            range=span(finding.start_row, finding.end_row),
            message=finding.message,
            severity=SEVERITIES[severity],
            source=diagnostics.SOURCE,
            code=finding.code,
            related_information=[
                lsp.DiagnosticRelatedInformation(
                    location=lsp.Location(uri=uri, range=span(row, row)), message=note
                )
                for row, note in finding.partners[:RELATED_CAP]
            ]
            or None,
        )
        for finding in findings
    ]
