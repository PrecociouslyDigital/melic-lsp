"""User settings, parsed once from whatever the client sends.

Display is configurable rather than chosen: highlighting, the line signature,
per-syllable hints and rhyme letters are independent, because which of them helps
depends entirely on what you are working on at the time.

The cross-line hints are configurable for a stronger reason. Whether two verses
disagreeing is a mistake or the song is not something the tool can know, so each rule
carries its own severity — including ``off``, which is a supported answer — and the
two count-based rules carry the tolerance they fire past.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .rhyme import SlantScope
from .signature import Mode

type Severity = Literal["off", "hint", "info", "warning"]

SEVERITIES = ("off", "hint", "info", "warning")
"""Also the enum the extension offers, in the order it offers them."""


@dataclass(frozen=True)
class HintSettings:
    """One severity per rule, so a rule that does not suit a song can be silenced
    without taking the others with it.

    ``hint`` throughout by default: visible where the editor collects them, and not
    a squiggle over anybody's lyrics.
    """

    rhyme_scheme_mismatch: Severity = "hint"
    parallel_line_drift: Severity = "hint"
    parallel_line_tolerance: int = 1
    """One syllable apart is pickup-note territory; two between lines meant to share
    a melody is worth a mark."""
    chord_progression_drift: Severity = "hint"
    chord_progression_tolerance: int = 2
    """Looser, because lines sharing a progression need not share a melody."""


@dataclass(frozen=True)
class Settings:
    stress_highlight: bool = True
    signature: Mode = Mode.COUNT_ONLY
    """Count only by default: stress marks want a column to line up in, and the
    margin has none. The panels are where patterns are compared."""
    per_syllable_hints: bool = False
    rhyme: bool = True
    slant_scope: SlantScope = "contextual"
    """Whether the rhyme solver may admit a near rhyme the song's structure supports."""
    chord_aware_syllables: bool = True
    """Let chord placement pick between a word's pronunciations."""
    chordpro_diagnostics: bool = True
    chord_mid_syllable: bool = True
    unknown_pronunciation: Literal["hint", "off"] = "hint"
    hints: HintSettings = HintSettings()
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

        def get(path: str, default: Any = None) -> Any:
            node: Any = config
            for key in path.split("."):
                if not isinstance(node, dict) or key not in node:
                    return default
                node = node[key]
            return node if node is not None else default

        return cls(
            stress_highlight=bool(get("stressHighlight.enabled", True)),
            signature=_mode(get("lineSignature.mode", Mode.COUNT_ONLY.value)),
            per_syllable_hints=bool(get("inlayHints.perSyllable", False)),
            rhyme=bool(get("rhyme.enabled", True)),
            slant_scope="strict" if get("rhyme.slantScope") == "strict" else "contextual",
            chord_aware_syllables=bool(get("chordAwareSyllables", True)),
            chordpro_diagnostics=bool(get("diagnostics.chordpro", True)),
            chord_mid_syllable=bool(get("diagnostics.chordMidSyllable", True)),
            unknown_pronunciation=(
                "off" if get("diagnostics.unknownPronunciation", "hint") == "off" else "hint"
            ),
            hints=HintSettings(
                rhyme_scheme_mismatch=_severity(
                    get("hints.rhymeSchemeMismatch.severity"), "hint"
                ),
                parallel_line_drift=_severity(
                    get("hints.parallelLineDrift.severity"), "hint"
                ),
                parallel_line_tolerance=_count(get("hints.parallelLineDrift.tolerance"), 1),
                chord_progression_drift=_severity(
                    get("hints.chordProgressionDrift.severity"), "hint"
                ),
                chord_progression_tolerance=_count(
                    get("hints.chordProgressionDrift.tolerance"), 2
                ),
            ),
            lang=str(get("lang", "en")) or "en",
        )


def _mode(value: Any) -> Mode:
    try:
        return Mode(value)
    except ValueError:
        return Mode.COUNT_ONLY


def _severity(value: Any, default: Severity) -> Severity:
    return value if value in SEVERITIES else default


def _count(value: Any, default: int) -> int:
    """A tolerance is a number of syllables, so below zero it means nothing."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
