"""Directive hover — the half that needs no dictionary.

Words and lines are prosodic's answer to give, and ``smoke_lsp.py`` checks those
against the real server. What is worth pinning here is that our own directives say
what they do: they are registered in the directive table precisely so hover has
something better to show than the generic note about `x_` directives nothing reads.
"""

from __future__ import annotations

import pytest

from melic_lsp.chordpro import DIRECTIVES, Category, Directive, DirectiveSpec, parse_document
from melic_lsp.features.hover import _directive_docs

GENERIC = "passed through untouched"

OURS = [spec for spec in DIRECTIVES.values() if spec.category is Category.MELIC]


def docs(text: str) -> str:
    (line,) = parse_document(text).lines
    assert isinstance(line, Directive)
    return _directive_docs(line)


@pytest.mark.parametrize("spec", OURS, ids=lambda spec: spec.canonical)
def test_our_directives_hover_with_their_own_documentation(spec: DirectiveSpec) -> None:
    """Taken from the table, so a fifth directive is covered the day it is added."""
    written = docs(f"{{{spec.canonical}: whatever}}")
    assert spec.doc is not None and spec.doc in written
    assert GENERIC not in written


def test_a_strangers_custom_directive_still_gets_the_generic_note() -> None:
    assert GENERIC in docs("{x_songbook_flag: 1}")


def test_ordinary_directives_are_described_by_their_fields() -> None:
    written = docs("{soc}")
    assert "`{start_of_chorus}`" in written and "`soc`" in written
    assert "analysed as lyrics" in written
