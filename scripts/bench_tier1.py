"""Gates the caching decision: full tier 1 over a 200-line song, warm.

The performance model says no line cache and no document cache are needed, because
prosodic memoises per word and our own derived offsets are memoised on top. That
rests on reading decorators rather than on a stopwatch, so this is the stopwatch.

    under  10 ms  the model holds; change nothing
    over   50 ms  add line-level memoisation keyed by lyric hash, and nothing more
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from melic_lsp import prosody  # noqa: E402
from melic_lsp.analysis import analyse_line  # noqa: E402
from melic_lsp.chordpro import parse_document  # noqa: E402
from melic_lsp.signature import Mode, render  # noqa: E402

BUDGET_MS = 10.0
CEILING_MS = 50.0
TARGET_LINES = 200


def build_song() -> str:
    """A 200-line song with a realistic vocabulary.

    Drawn from several traditional songs rather than one repeated verse: a
    benchmark whose 200 lines share two dozen words would mostly be measuring the
    per-word cache hit rate, which is the very thing under test.
    """
    fixtures = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    lyric_lines = [
        line.text
        for path in sorted(fixtures.glob("*.cho"))
        for line in parse_document(path.read_text()).lyrics()
        if line.lyric.strip()
    ]
    repeated = (lyric_lines * (TARGET_LINES // len(lyric_lines) + 1))[:TARGET_LINES]
    return "\n".join(repeated)


def tier1(document_text: str) -> int:
    """Everything the editor asks for on every request."""
    marks = 0
    for line in parse_document(document_text).lyrics():
        analysis = analyse_line(line)
        render(analysis, Mode.CHORD_GROUPED)  # the costliest mode, not the default
        marks += analysis.count
    return marks


def main() -> int:
    song = build_song()
    lyrics = parse_document(song).lyrics()
    tokens = [word.token for line in lyrics for word in line.words()]

    started = time.perf_counter()
    prosody.warm_up()
    warm_up_s = time.perf_counter() - started
    if not prosody.is_ready():
        print(f"prosodic unavailable: {prosody.status()}", file=sys.stderr)
        return 2

    tier1(song)  # prime the per-word caches, as a live server would be

    timings: list[float] = []
    for _ in range(20):
        started = time.perf_counter()
        syllables = tier1(song)
        timings.append((time.perf_counter() - started) * 1000)

    timings.sort()
    median = timings[len(timings) // 2]
    print(
        f"warm-up        {warm_up_s * 1000:8.0f} ms\n"
        f"lines          {len(lyrics):8d}\n"
        f"word tokens    {len(tokens):8d}  ({len(set(tokens))} unique)\n"
        f"syllables      {syllables:8d}\n"
        f"tier 1 median  {median:8.2f} ms   (best {timings[0]:.2f}, worst {timings[-1]:.2f})"
    )

    if median > CEILING_MS:
        print(f"\nOVER {CEILING_MS:.0f} ms — add line-level memoisation.", file=sys.stderr)
        return 1
    verdict = "within" if median <= BUDGET_MS else "above"
    print(f"\n{verdict} the {BUDGET_MS:.0f} ms budget; no line cache needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
