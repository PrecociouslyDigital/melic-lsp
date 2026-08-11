"""The two on-demand panels, rendered as monospace text for a read-only document.

Cross-line divergence lives here and only here. A verse that runs a syllable long
against its neighbour may be a slip or may be the song, and a diagnostic that
cannot tell the difference would just be a squiggle you learn to ignore. Shown on
request, side by side, it is information instead of an accusation.
"""

from __future__ import annotations

from ..analysis import DocumentAnalysis, LineAnalysis
from ..rhyme import Rhyme, scheme_string
from ..sections import Section, Stack, stacks
from ..signature import count_label, marks

RULE = "─"
WIDTH = 78


def compare_sections(model: DocumentAnalysis) -> str:
    """Stack same-kind sections so parallel lines sit on top of each other."""
    groups = stacks(list(model.sections))
    if not groups:
        return _page(
            "Compare Sections",
            ["Nothing to compare: this song has no two sections of the same kind.",
             "",
             "Sections come from {start_of_verse} / {start_of_chorus} directives,",
             "or from stanzas separated by blank lines."],
        )

    body: list[str] = []
    for stack in groups:
        body.extend(_stack_block(stack, model))
    return _page("Compare Sections", body)


def _stack_block(stack: Stack, model: DocumentAnalysis) -> list[str]:
    names = " · ".join(_titled(section, model.rhymes) for section in stack.sections)
    out = [f"{stack.kind.upper()}  ({len(stack.sections)})  {names}", RULE * WIDTH]

    for index, row in enumerate(stack.rows, start=1):
        out.append(f"{index:>3}.")
        compared: list[LineAnalysis] = []
        for line, section in zip(row, stack.sections):
            if line is None:
                out.append(f"{'':>5}{'—':>4}   {section.title}: (no line here)")
                continue
            analysis = model.by_row(line.row)
            if analysis is None:
                continue
            compared.append(analysis)
            out.append(f"{'':>5}{count_label(analysis):>4}   {line.lyric.strip()}")
            out.append(f"{'':>12}{marks(analysis)}")
        out.append(f"{'':>5}{_verdict(compared)}")
        out.append("")
    return out


def _titled(section: Section, rhymes: dict[int, Rhyme]) -> str:
    """Name plus rhyme scheme, so a verse rhyming unlike its siblings shows here."""
    scheme = scheme_string(list(section.lines), rhymes)
    return f"{section.title} ({scheme})" if scheme else section.title


def _verdict(analyses: list[LineAnalysis]) -> str:
    """Say whether these lines agree — and refuse to, when a count is a floor."""
    if len(analyses) < 2:
        return ""

    unknown = sorted(
        {missing.span.token for a in analyses for missing in a.unresolved}
    )
    if unknown:
        # Comparing floors would manufacture a difference out of a missing
        # dictionary entry, which is the opposite of useful.
        words = ", ".join(f"“{word}”" for word in unknown)
        return f"? not comparable — no pronunciation for {words}"

    counts = [analysis.count for analysis in analyses]
    spread = max(counts) - min(counts)
    if spread == 0:
        return f"✓ all {counts[0]} syllables"
    return (
        f"✗ {spread} syllable{'s' if spread > 1 else ''} apart"
        f"  ({', '.join(map(str, counts))})"
    )


def scansion_panel(model: DocumentAnalysis) -> str:
    """A grid of chord, syllable and stress, one column per syllable."""
    body: list[str] = []
    for analysis in model.lines:
        if not analysis.syllables:
            continue
        body.extend(_grid(analysis))
        body.append("")
    if not body:
        return _page("Scansion", ["No analysed lyric lines in this document."])
    return _page("Scansion", body)


def _grid(analysis: LineAnalysis) -> list[str]:
    """One line as three aligned rows: chord over syllable over stress."""
    chords: list[str] = []
    syllables: list[str] = []
    stresses: list[str] = []

    for group in analysis.groups():
        name = f"[{group.chord.name}]" if group.chord else ""
        if not group.syllables:
            # A chord with nothing under it still gets a column, or it would vanish.
            chords.append(name)
            syllables.append("")
            stresses.append("")
            continue
        for index, syllable in enumerate(group.syllables):
            chords.append(name if index == 0 else "")
            syllables.append(syllable.text)
            stresses.append(syllable.stress.value)

    widths = [
        max(len(chord), len(text), 1)
        for chord, text in zip(chords, syllables)
    ]
    def row(label: str, cells: list[str]) -> str:
        padded = " ".join(cell.ljust(width) for cell, width in zip(cells, widths))
        return f"  {label:<9}{padded.rstrip()}"

    return [
        f"{analysis.line.row + 1:>4}  {analysis.line.text}",
        row("chord", chords),
        row("syllable", syllables),
        row("stress", stresses),
    ]


def _page(title: str, body: list[str]) -> str:
    return "\n".join([f"Melic — {title}", "=" * WIDTH, "", *body])
