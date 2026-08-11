"""User settings, parsed once from whatever the client sends.

Display is configurable rather than chosen: highlighting, the line signature,
per-syllable hints and rhyme letters are independent, because which of them helps
depends entirely on what you are working on at the time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .signature import Mode


@dataclass(frozen=True)
class Settings:
    stress_highlight: bool = True
    signature: Mode = Mode.CHORD_GROUPED
    per_syllable_hints: bool = False
    rhyme: bool = True
    chord_aware_syllables: bool = True
    """Let chord placement pick between a word's pronunciations."""
    chordpro_diagnostics: bool = True
    chord_mid_syllable: bool = True
    unknown_pronunciation: Literal["hint", "off"] = "hint"
    lang: str = "en"

    @classmethod
    def parse(cls, raw: Any) -> Settings:
        """Read a `melic.*` config blob, falling back to defaults key by key.

        Clients disagree about whether settings arrive nested or flattened, and a
        malformed value should cost you that one setting rather than the server.
        """
        config = raw.get("melic", raw) if isinstance(raw, dict) else {}
        if not isinstance(config, dict):
            return cls()

        def get(path: str, default: Any) -> Any:
            node: Any = config
            for key in path.split("."):
                if not isinstance(node, dict) or key not in node:
                    return default
                node = node[key]
            return node if node is not None else default

        return cls(
            stress_highlight=bool(get("stressHighlight.enabled", True)),
            signature=_mode(get("lineSignature.mode", Mode.CHORD_GROUPED.value)),
            per_syllable_hints=bool(get("inlayHints.perSyllable", False)),
            rhyme=bool(get("rhyme.enabled", True)),
            chord_aware_syllables=bool(get("chordAwareSyllables", True)),
            chordpro_diagnostics=bool(get("diagnostics.chordpro", True)),
            chord_mid_syllable=bool(get("diagnostics.chordMidSyllable", True)),
            unknown_pronunciation=(
                "off" if get("diagnostics.unknownPronunciation", "hint") == "off" else "hint"
            ),
            lang=str(get("lang", "en")) or "en",
        )


def _mode(value: Any) -> Mode:
    try:
        return Mode(value)
    except ValueError:
        return Mode.CHORD_GROUPED
