---
paths:
  - "tests/**"
  - "scripts/**"
  - ".github/workflows/*.yml"
---

# Testing — small on purpose

Bugs here are either **silent and wrong** (an offset lands the highlight on the wrong
character — you'd blame prosodic, not us) or **loud and obvious** (a feature doesn't
render, which F5 shows in two seconds). Only the first kind is worth automating. Please
keep it that way; the suite runs in ~1.5s and that is a feature.

## The test that carries the project

`test_every_lyric_offset_maps_back_to_the_same_character` — for every lyric offset in
every fixture line, `to_source` must point at the same character. Exhaustive over real
fixture text rather than generated input, and it subsumes every case worth enumerating by
hand: chord-splits-a-word, leading and trailing chords, chord-only lines, unicode,
apostrophes. **Adding a fixture strengthens it for free**, which is a good reason to add
one when you meet a new shape.

## What each file is for

| File | Tests | Needs prosodic |
|---|---|---|
| `test_chordpro.py` | position round-trip, line kinds, directives, environments | no |
| `test_sections.py` | grouping and stacking — silent when wrong | no |
| `test_overrides.py` | payload grammar, scope precedence, textual validation | no |
| `test_prosody.py` | **our guard** (`Tiled` vs `WholeWord`), graceful OOV | some |
| `test_signature.py` | golden signature strings | yes |
| `test_rhyme.py` | scheme strings (pure), which chime we call what, and every solver decision | some |
| `test_hints.py` | the three cross-line rules, on hand-built counts | no |
| `test_code_actions.py` | where the moved chord lands, and what the fix refuses | some |
| `test_settings.py` | defaults, and what one malformed value costs | no |

## Deliberately not tested

- **Prosodic itself.** Asserting that `chariot` has three syllables is a change-detector
  for someone else's code, and it has its own suite.
- **The pygls plumbing.** Testing that a decorator registers a handler tests pygls.
- **Hover markdown, the VS Code client.** Thin glue; `smoke_lsp.py` and F5 check it
  faster and more honestly than a mock would.
- **No coverage target**, which would only push toward the tests just argued against.

## Three checks that are not tests but matter more than most tests here

1. **`scripts/check_types.sh`** — `ty` clean, *and* the type checker must **reject**
   `scripts/coordinate_space_violations.py`. Add a violation when you add a bridge.
2. **`scripts/bench_tier1.py`** — gates the no-cache decision. Under 10 ms fine; over
   50 ms add line-level memoisation and nothing more. Keep the fixture vocabulary
   realistic (~150 unique tokens) or it just measures cache hit rate, and keep the song
   in stanzas — the rhyme solver reads one stanza at a time, and one 200-line stanza is
   both unlike any song and skipped outright. It times the **whole request**
   (`analyse_document` + `hints.build` + rendering), which is why the number stepped up
   from the ~3 ms it reported while it only timed per-line work.
3. **`scripts/smoke_lsp.py`** — real JSON-RPC against the real binary. Checks the warming
   → refresh → annotated sequence, and that server/palette command ids stay disjoint.
   When you add a feature, add a line here rather than a mock.

## CI

The server suite runs **twice**, with espeak present and absent. Both are supported, and
the degradation path is easy to break without noticing. Note `astral-sh/setup-uv`
publishes no floating major tag, so it is pinned to an exact version.
