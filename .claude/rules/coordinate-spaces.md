---
paths:
  - "src/melic_lsp/types.py"
  - "src/melic_lsp/chordpro.py"
  - "src/melic_lsp/analysis.py"
  - "src/melic_lsp/features/**/*.py"
  - "scripts/coordinate_space_violations.py"
---

# Three coordinate spaces — the one invariant worth being pedantic about

Every position bug in this project is the same bug: an integer used in the wrong space.
There are three, they are distinct `NewType`s, and the chain runs one way.

```
WordCol  --WordSpan.lyric_col-->  LyricCol  --SpanMap.to_source-->  SrcCol
```

- **`WordCol`** — offset within a single token. The space prosodic speaks.
- **`LyricCol`** — column in the line with every `[chord]` removed.
- **`SrcCol`** — column in the document line exactly as typed. What the editor draws.

**Each hop has exactly one bridge, and there are no others.** `SpanMap.to_source` is the
only way out of lyric space; `WordSpan.lyric_col` the only way out of word space.
`SpanMap.to_lyric` is the inverse, for "what is under the cursor".

Skipping a hop is a type error, not a highlight one character off. Wrapping —
`SrcCol(x)` — is the price, and it is only paid at I/O boundaries and inside the bridges
themselves, where the arithmetic is allowed to be plain `int`.

## Prove it still bites

`scripts/coordinate_space_violations.py` is never imported and never run. It exists so
`./scripts/check_types.sh` can assert the type checker **rejects** it. Newtypes that
nothing enforces are pure noise, so if you add a bridge, add a violation there too.

## One lyric range can be several source ranges

`to_source` returns a **list**, and callers must handle all of it. In `chari[D]ot` the
lyric word is `chariot`, but a chord interrupts it, so a syllable spanning the chord maps
to two source ranges. Semantic tokens emit one token per range; the chord-mid-syllable
lint marks from the first range's start to the last one's end, and its quick fix moves
the chord to that same start.

## Positions you cannot have

`Tiled` carries syllables whose offsets are sound by construction; `WholeWord` is the
honest degraded case with no per-syllable offsets at all. Callers that want positions
must handle both — that is the type doing its job. `PlacedSyllable.exact` carries the
same distinction into lyric space: when `False`, the range covers the whole token and
only the count and stress are trustworthy, so semantic tokens skip it rather than colour
it wrongly.
