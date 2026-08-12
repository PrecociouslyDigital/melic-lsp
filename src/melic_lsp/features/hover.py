"""Hover: what is under the cursor, in as much detail as it deserves.

Three targets, three answers. A word gives its pronunciation, which is tier 1 and
instant. Blank space on a lyric line gives the metrical scan of the whole line,
which is tier 2 and genuinely slow — putting it behind a deliberate hover is how it
stays off the hot path. A directive gives its ChordPro documentation.
"""

from __future__ import annotations

from lsprotocol import types as lsp

from .. import prosody
from ..chordpro import Category, Directive, Line, Lyric, Value
from ..overrides import EMPTY, Override, Overrides
from ..rhyme import DESCRIPTION, Rhyme
from ..types import Ready, SrcCol, Syllabified, Tiled, Unavailable, Warming

SYLLABLE_SEP = "·"


def build(
    line: Line,
    column: SrcCol,
    siblings: list[Lyric],
    lang: str,
    rhymes: dict[int, Rhyme],
    annotations: Overrides = EMPTY,
) -> lsp.Hover | None:
    """``rhymes`` is the document's labels, already computed.

    Hover takes them rather than working the scheme out again, so that what it names
    as a partner is exactly what the margin lettered — including a near rhyme the
    solver admitted, which a second strict pass here would deny.
    """
    match line:
        case Directive():
            return _markdown(_directive_docs(line))
        case Lyric():
            return _lyric_hover(line, column, siblings, lang, rhymes, annotations)
        case _:
            return None


def _override_docs(override: Override) -> str:
    """Say plainly that this reading was written by hand, not looked up."""
    split = SYLLABLE_SEP.join(override.texts)
    marks = (
        "".join(stress.value for stress in override.stresses)
        if override.stresses is not None
        else "taken from the dictionary reading of the same length"
    )
    return "\n\n".join(
        [
            f"**{split}** — {len(override.texts)} syllables",
            f"Stress `{marks}`",
            f"<sub>set by hand on line {override.row + 1}, not inferred</sub>",
        ]
    )


def _lyric_hover(
    line: Lyric,
    column: SrcCol,
    siblings: list[Lyric],
    lang: str,
    rhymes: dict[int, Rhyme],
    annotations: Overrides,
) -> lsp.Hover | None:
    for chord in line.chords:
        if chord.source.start <= column < chord.source.end:
            return _markdown(f"**Chord `{chord.name}`**")

    lyric_column = line.spans.to_lyric(column)
    if lyric_column is not None:
        for word in line.words():
            if word.start <= lyric_column < word.end:
                override = annotations.find(word.token, line.row)
                if override is not None:
                    return _markdown(_override_docs(override))
                return _markdown(_word_docs(word.token, lang))

    return _markdown(_line_docs(line, siblings, lang, rhymes))


# --- Words -------------------------------------------------------------------


def _word_docs(token: str, lang: str) -> str:
    match prosody.syllabify(token, lang):
        case Warming():
            return f"**{token}** — still loading the pronunciation dictionary…"
        case Unavailable(reason):
            return f"**{token}**\n\n{reason}"
        case Ready(word):
            pass

    lines = [f"**{_split(word.syllables)}**", ""]
    lines.append(_stress_table(word.syllables))

    if len(word.variants) > 1:
        alternates = ", ".join(
            f"`{_split(variant)}` ({len(variant.syllables)}σ)"
            for variant in word.variants[1:]
        )
        lines += ["", f"*Also said* {alternates}"]

    origin = "guessed by espeak" if word.guessed else "from the dictionary"
    if isinstance(word.syllables, Tiled):
        lines += ["", f"<sub>{origin}</sub>"]
    else:
        lines += [
            "",
            f"<sub>{origin}; syllables do not line up with the spelling, "
            "so they are counted but not highlighted</sub>",
        ]
    return "\n".join(lines)


def _split(syllabified: Syllabified) -> str:
    return SYLLABLE_SEP.join(syllable.text for syllable in syllabified.syllables)


def _stress_table(syllabified: Syllabified) -> str:
    heaviness = prosody.weights(syllabified)
    header = "| syllable | IPA | stress | weight |\n|---|---|---|---|"
    rows = [
        f"| {syllable.text} | /{syllable.ipa}/ | {syllable.stress.name.lower()} | "
        f"{'heavy' if index < len(heaviness) and heaviness[index] else 'light'} |"
        for index, syllable in enumerate(syllabified.syllables)
    ]
    return "\n".join([header, *rows])


# --- Lines -------------------------------------------------------------------


def _line_docs(
    line: Lyric, siblings: list[Lyric], lang: str, rhymes: dict[int, Rhyme]
) -> str:
    parts = [f"**{line.lyric.strip()}**", ""]

    match prosody.scan_line(line.lyric, lang):
        case Ready(scansion):
            parts += [
                f"- **{scansion.foot_type}**, {scansion.num_sylls} syllables",
                f"- metre `{scansion.meter}`",
                f"- stress `{scansion.stress}`",
            ]
            if scansion.feet:
                parts.append(f"- feet `{' | '.join(scansion.feet)}`")
        case Unavailable(reason):
            parts.append(f"*No metrical scan: {reason}*")
        case Warming():
            parts.append("*Still loading…*")

    partners = _rhyme_partners(line, siblings, rhymes)
    if partners:
        parts += ["", f"**Rhymes with** {partners}"]
    return "\n".join(parts)


def _rhyme_partners(line: Lyric, siblings: list[Lyric], labels: dict[int, Rhyme]) -> str:
    """The rest of this line's rhyme group, each with how it chimes.

    The quality is the one the scheme measured — against the line that opened the
    group — which is what the margin's `~`, `≈` and `=` marks mean too. Siblings are
    the enclosing stanza's lines, which is the scope the letters were handed out in,
    so a row-keyed lookup over them cannot pick up a letter from another stanza.
    """
    mine = labels.get(line.row)
    if mine is None:
        return ""

    partners = []
    for other in siblings:
        label = labels.get(other.row)
        if other.row == line.row or label is None or label.letter != mine.letter:
            continue
        partners.append(
            f"line {other.row + 1} (“{other.lyric.strip()}”) — "
            f"{DESCRIPTION[label.chime]}"
        )
    return ", ".join(partners)


# --- Directives --------------------------------------------------------------


def _directive_docs(directive: Directive) -> str:
    spec = directive.spec
    if spec is None:
        return f"**`{{{directive.name}}}`** — not a ChordPro directive."

    lines = [f"**`{{{spec.canonical}}}`** — {spec.category.name.lower()}"]
    if spec.aliases:
        lines.append(f"Also written {', '.join(f'`{a}`' for a in spec.aliases)}.")
    if spec.value is Value.REQUIRED:
        lines.append("Takes a value: `{" + spec.canonical + ": …}`")
    elif spec.value is Value.OPTIONAL:
        lines.append("May take a value.")
    if spec.env is not None:
        role = "Opens" if spec.env.opens else "Closes"
        analysed = "analysed as lyrics" if spec.env.kind.name == "LYRIC" else "left verbatim"
        lines.append(f"{role} the `{spec.env.env}` environment, {analysed}.")
    if spec.category is Category.CUSTOM:
        lines.append("A custom `x_` directive, passed through untouched.")
    return "\n\n".join(lines)


def _markdown(value: str) -> lsp.Hover:
    return lsp.Hover(
        contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=value)
    )
