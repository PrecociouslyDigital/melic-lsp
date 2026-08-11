"""The prosodic adapter — the only module that imports prosodic.

Everything crosses this seam as an ``Analysis``: a result, "still warming", or an
honest reason it cannot be answered. Prosodic raises rather than guessing when a
word misses the dictionary and espeak is absent, and that is a normal Tuesday for
song lyrics, so the exception is turned into ``Unavailable`` here and nowhere else.

If import time ever proves painful, this seam is where prosodic moves into a worker
process; nothing outside this file would change.
"""

from __future__ import annotations

import contextlib
import sys
import threading
import warnings
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .types import (
    Analysis,
    RawSyllable,
    Ready,
    Stress,
    Syllabified,
    Unavailable,
    Warming,
    tile,
)

# --- What the adapter hands back ---------------------------------------------


@dataclass(frozen=True)
class Word:
    """How a token is said, with the alternates hover wants."""

    token: str
    variants: tuple[Syllabified, ...]
    guessed: bool
    """True when the pronunciation came from espeak rather than the dictionary."""

    @property
    def syllables(self) -> Syllabified:
        """Prosodic's preferred reading."""
        return self.variants[0]


@dataclass(frozen=True)
class Scansion:
    """Tier 2: the result of a genuine metrical search."""

    meter: str
    stress: str
    foot_type: str
    feet: tuple[str, ...]
    num_sylls: int


# --- Warm-up -----------------------------------------------------------------

_lock = threading.Lock()
_ready = threading.Event()
_failure: str | None = None


def warm_up(lang: str = "en") -> None:
    """Import prosodic and load the dictionary. Blocks; call it on a thread.

    Importing takes ~1.5s warm and far longer on a cold bytecode cache, which is
    the whole reason this is not done at first request.
    """
    global _failure
    with _lock:
        if _ready.is_set() or _failure is not None:
            return
        try:
            # Prosodic warns about missing espeak on stderr, which is fine, but a
            # single stray print to stdout from any of its ~30 dependencies would
            # corrupt the JSON-RPC stream and be miserable to diagnose. Cheap guard.
            #
            # SyntaxWarning is silenced for the same reason one layer up: panphon
            # has a docstring holding an unescaped ``\w``, so compiling it emits a
            # warning the user can do nothing about. It fires only when the
            # bytecode cache is cold — once per install — and lands in the editor's
            # output channel looking like something broke.
            with contextlib.redirect_stdout(sys.stderr), warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                from prosodic.langs import get_word

                get_word("the", lang)
        except Exception as exc:  # noqa: BLE001 - degrade, never take the server down
            _failure = f"prosodic unavailable: {exc}"
            return
        _ready.set()


def prewarm_scansion(lang: str = "en") -> None:
    """Build one throwaway ``Text`` so the first hover is not a 5s stall.

    Constructing a ``Text`` loads prosodic's syntax models and costs seconds the
    first time — far more than the metrical search it precedes. Run after
    ``warm_up`` on the same background thread, where the time is free.
    """
    with contextlib.suppress(Exception):
        with contextlib.redirect_stdout(sys.stderr):
            _text_model("the sun is warm", lang)


def is_ready() -> bool:
    return _ready.is_set()


def status() -> Analysis[None]:
    """Tier 0 state, for features that must say why they have nothing to show."""
    if _failure is not None:
        return Unavailable(_failure)
    return Ready(None) if _ready.is_set() else Warming()


def _pending() -> Analysis[Any] | None:
    """The tier-0 answer, or None if prosodic is ready to be asked."""
    if _failure is not None:
        return Unavailable(_failure)
    return None if _ready.is_set() else Warming()


# --- Tier 1: syllables, stress, rhyme ----------------------------------------


def syllabify(token: str, lang: str = "en") -> Analysis[Word]:
    """Split a token into stressed syllables. The workhorse of every feature."""
    pending = _pending()
    return pending if pending is not None else _syllabify(token, lang)


@lru_cache(maxsize=8192)
def _syllabify(token: str, lang: str) -> Ready[Word] | Unavailable:
    """Cached only once warm, so a ``Warming`` answer can never be memoised.

    Prosodic caches ``get_word`` itself; this cache holds the derived offsets so a
    re-scan of the document is dict lookups and nothing more.
    """
    from prosodic.langs import get_word
    from prosodic.utils import get_syll_ipa_stress

    try:
        with contextlib.redirect_stdout(sys.stderr):
            sylls_ll, meta = get_word(token, lang)
    except Exception as exc:  # noqa: BLE001 - OOV without espeak is routine
        return Unavailable(_explain(token, exc))

    variants = tuple(
        tile(
            token,
            [
                RawSyllable(text, ipa, Stress.parse(get_syll_ipa_stress(ipa)))
                for ipa, text in sylls
            ],
        )
        for sylls in sylls_ll
        if sylls
    )
    if not variants:
        return Unavailable(f"no pronunciation for {token!r}")
    return Ready(Word(token, variants, guessed=meta.get("ipa_origin") == "tts"))


def _explain(token: str, exc: Exception) -> str:
    if "espeak" in str(exc).lower():
        return (
            f"{token!r} is not in the pronunciation dictionary, and espeak "
            "(which would guess it) is not installed"
        )
    return f"cannot pronounce {token!r}: {exc}"


def rhyme_type(first: Syllabified, second: Syllabified) -> str | None:
    """Classify an end-rhyme as 'perfect', 'slant', 'assonance' or None.

    Prosodic's own calibration says to count perfect and slant as rhyme and to
    leave assonance out (counting it triples the false-positive rate), so callers
    that want a yes/no should use :func:`rhymes`.
    """
    left, right = _wordform(first), _wordform(second)
    if left is None or right is None:
        return None
    with contextlib.suppress(Exception):
        return left.rime_type(right)
    return None


def rhymes(first: Syllabified, second: Syllabified) -> bool:
    return rhyme_type(first, second) in ("perfect", "slant")


@lru_cache(maxsize=2048)
def _wordform_cached(token: str, ipas: tuple[str, ...], texts: tuple[str, ...]) -> Any:
    from prosodic.words.wordform import WordForm

    # A WordForm normally derives its key from its parent; we have no parent and
    # want none, so supply the key directly. Its rhyme methods are @cache'd and so
    # need the hash that key provides.
    return WordForm(
        txt=token,
        sylls_ipa=list(ipas),
        sylls_text=list(texts),
        key=f"melic.wordform.{token}",
    )


def weights(syllabified: Syllabified) -> tuple[bool, ...]:
    """Per-syllable heaviness, for hover. Empty when prosodic will not say.

    Reuses the WordForm the rhyme code already builds and caches, so this costs a
    dictionary lookup rather than any new analysis.
    """
    wordform = _wordform(syllabified)
    if wordform is None:
        return ()
    with contextlib.suppress(Exception):
        return tuple(bool(syllable.is_heavy) for syllable in wordform.children)
    return ()


def _wordform(syllabified: Syllabified) -> Any:
    sylls = syllabified.syllables
    if not sylls:
        return None
    with contextlib.suppress(Exception):
        return _wordform_cached(
            syllabified.token,
            tuple(s.ipa for s in sylls),
            tuple(s.text for s in sylls),
        )
    return None


# --- Tier 2: metrical scansion, on demand only -------------------------------


def scan_line(text: str, lang: str = "en") -> Analysis[Scansion]:
    """Run prosodic's metrical search over one line. Genuinely slow; never eager."""
    pending = _pending()
    if pending is not None:
        return pending
    return _scan_line(text.strip(), lang)


@lru_cache(maxsize=512)
def _scan_line(text: str, lang: str) -> Ready[Scansion] | Unavailable:
    if not text:
        return Unavailable("nothing to scan")
    try:
        with contextlib.redirect_stdout(sys.stderr):
            line = _text_model(text, lang).lines[0]
            line.parse()
            best = line.best_parse
    except Exception as exc:  # noqa: BLE001 - an OOV word anywhere sinks the parse
        return Unavailable(_explain(text, exc))
    if best is None:
        return Unavailable("no metrical parse found")
    return Ready(
        Scansion(
            meter=str(getattr(best, "meter_str", "")),
            stress=str(getattr(best, "stress_str", "")),
            foot_type=str(getattr(best, "foot_type", "")),
            feet=tuple(getattr(best, "feet", ()) or ()),
            num_sylls=int(getattr(best, "num_sylls", 0) or 0),
        )
    )


def _text_model(text: str, lang: str) -> Any:
    import prosodic

    return prosodic.Text(text, lang=lang)
