"""Syllable highlighting via semantic tokens.

A syllable interrupted by a chord occupies two source ranges, and semantic tokens
handle that natively: emit one token per range, both carrying the same stress. So
``chari[D]ot`` colours as one word split across the chord rather than as two
mysterious fragments.
"""

from __future__ import annotations

from lsprotocol import types as lsp

from ..analysis import LineAnalysis
from ..types import Stress

TOKEN_TYPES = ["melicSyllable"]
MODIFIERS = ["stressed", "secondary", "unstressed", "alternate"]

LEGEND = lsp.SemanticTokensLegend(
    token_types=TOKEN_TYPES, token_modifiers=MODIFIERS
)

_STRESS_BIT = {
    Stress.PRIMARY: 1 << MODIFIERS.index("stressed"),
    Stress.SECONDARY: 1 << MODIFIERS.index("secondary"),
    Stress.NONE: 1 << MODIFIERS.index("unstressed"),
}
_ALTERNATE_BIT = 1 << MODIFIERS.index("alternate")


def encode(analyses: list[LineAnalysis]) -> lsp.SemanticTokens:
    """Encode syllables as LSP's delta-packed quintuples."""
    data: list[int] = []
    previous_row = 0
    previous_start = 0

    for analysis in analyses:
        for index, syllable in enumerate(analysis.syllables):
            if not syllable.exact:
                # A syllable we could not tile has no character range of its own;
                # every syllable of that word would claim the whole word. Leave it
                # uncoloured rather than colour it wrongly.
                continue
            modifiers = _STRESS_BIT[syllable.stress] | (
                _ALTERNATE_BIT if index % 2 else 0
            )
            for span in analysis.line.spans.to_source(syllable.start, syllable.end):
                row = analysis.line.row
                delta_row = row - previous_row
                delta_start = span.start - (previous_start if delta_row == 0 else 0)
                data.extend(
                    [delta_row, delta_start, span.end - span.start, 0, modifiers]
                )
                previous_row, previous_start = row, span.start

    return lsp.SemanticTokens(data=data)
