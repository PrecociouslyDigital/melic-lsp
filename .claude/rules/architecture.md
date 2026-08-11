---
paths:
  - "src/melic_lsp/**/*.py"
---

# Architecture — the seams, and which way dependencies point

```
features/*        semantic_tokens, inlay_hints, hover, diagnostics, symbols, views
   ↓
analysis.py       joins parsing to prosody; decides each word's reading
   ↓        ↘
chordpro.py       prosody.py        sections.py  rhyme.py  overrides.py  signature.py
(no prosodic)     (only prosodic)
   ↓
types.py          coordinate newtypes + ADTs; imported by everything
```

**`chordpro.py` must never import prosodic, directly or transitively.** All the
position-mapping logic — the highest-risk code in the repo — lives there precisely so it
is testable in milliseconds without loading a 2.75 MB dictionary. `test_chordpro.py`
runs in ~0.05s and that is the point.

**`prosody.py` is the only module that imports prosodic**, and it must stay
ChordPro-ignorant: it knows nothing of chords, lines or directives. When something needs
both — like choosing a pronunciation based on chord placement — it belongs in
`analysis.py`, which exists to join them. This seam is also the escape hatch: if
prosodic's import cost ever forces it into a worker process, only `prosody.py` changes.

`overrides.py` is likewise prosodic-free: it parses and scopes annotations, nothing more.

## Two tiers, and what may live in each

| Tier | Work | When |
|---|---|---|
| 0 | import prosodic + load dictionary | background thread after `initialize`; requests meanwhile answer `Warming`, then one refresh |
| 1 | syllables, stress, chord grouping, counts, rhyme | on demand, every request |
| 2 | `line.parse()` metrical scan | on demand **only** — hover and commands |

Tier 2 is not just "slower". Constructing a `prosodic.Text` costs ~5s the first time
(it loads syntax models); the parse itself is ~13ms. That is why `prewarm_scansion`
runs on the background thread after tier 1 is ready — background time is free, and a
first hover that stalls for five seconds is not.

## Caching: word level only

Prosodic memoises `get_word`; we memoise the derived offsets on top (`_syllabify`).
**There is no line cache, no document cache, no version keying and no invalidation
logic**, and adding one is a regression unless the benchmark says otherwise.

This is measured, not assumed: `scripts/bench_tier1.py` runs full tier 1 over a 200-line
song with a realistic vocabulary (~150 unique tokens). ~3 ms locally, ~8 ms on CI,
against a 10 ms budget. Only if it exceeds **50 ms** should line-level memoisation keyed
by lyric hash be added — and nothing more than that.

## Degradation is a type, not a convention

`Analysis[T] = Ready[T] | Warming | Unavailable` exists because "this line has no
syllables", "prosodic is still loading" and "this word has no pronunciation" are three
different things the UI must say differently. Never collapse them into an empty result:
a signature rendering a confident `0σ` for a line that simply has not been analysed yet
is the exact bug this type prevents.
