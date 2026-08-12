"""Settings parsing: what ships by default, and what a malformed value costs.

Clients send whatever they like, and the rule is that one bad value costs that one
setting and nothing else. Worth pinning because the failure would be silent — a rule
quietly reading "off" looks exactly like a rule that found nothing to say.
"""

from __future__ import annotations

from typing import Any

import pytest

from melic_lsp.settings import HintSettings, Settings
from melic_lsp.signature import Mode


def parsed(config: dict[str, Any]) -> Settings:
    return Settings.parse({"melic": config})


def test_the_shipped_defaults() -> None:
    """Every rule visible but silent-by-nature, and the solver on."""
    settings = Settings()
    assert settings.hints == HintSettings(
        rhyme_scheme_mismatch="hint",
        parallel_line_drift="hint",
        parallel_line_tolerance=1,
        chord_progression_drift="hint",
        chord_progression_tolerance=2,
    )
    assert settings.slant_scope == "contextual"


def test_an_empty_config_is_the_defaults() -> None:
    assert parsed({}) == Settings()


def test_every_hint_key_parses() -> None:
    settings = parsed(
        {
            "hints": {
                "rhymeSchemeMismatch": {"severity": "warning"},
                "parallelLineDrift": {"severity": "info", "tolerance": 3},
                "chordProgressionDrift": {"severity": "off", "tolerance": 0},
            }
        }
    )
    assert settings.hints == HintSettings(
        rhyme_scheme_mismatch="warning",
        parallel_line_drift="info",
        parallel_line_tolerance=3,
        chord_progression_drift="off",
        chord_progression_tolerance=0,
    )


def test_a_malformed_severity_costs_only_that_rule() -> None:
    settings = parsed(
        {
            "hints": {
                "parallelLineDrift": {"severity": "shout"},
                "rhymeSchemeMismatch": {"severity": "off"},
            }
        }
    )
    assert settings.hints.parallel_line_drift == "hint"
    assert settings.hints.rhyme_scheme_mismatch == "off"


@pytest.mark.parametrize("value,expected", [("two", 1), (None, 1), (-4, 0), (2.9, 2)])
def test_a_tolerance_that_is_not_a_count(value: Any, expected: int) -> None:
    settings = parsed({"hints": {"parallelLineDrift": {"tolerance": value}}})
    assert settings.hints.parallel_line_tolerance == expected


@pytest.mark.parametrize(
    "value,expected",
    [("strict", "strict"), ("contextual", "contextual"), ("loose", "contextual")],
)
def test_slant_scope(value: str, expected: str) -> None:
    assert parsed({"rhyme": {"slantScope": value}}).slant_scope == expected


def test_the_older_settings_still_parse_alongside() -> None:
    """The hints blob is new; nothing about reading the rest of it changed."""
    settings = parsed({"lineSignature": {"mode": "flat"}, "rhyme": {"enabled": False}})
    assert settings.signature is Mode.FLAT and settings.rhyme is False
