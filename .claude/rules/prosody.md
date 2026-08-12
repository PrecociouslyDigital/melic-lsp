---
paths:
  - "src/melic_lsp/prosody.py"
  - "src/melic_lsp/rhyme.py"
---

# The prosodic adapter — the only module that imports prosodic

Everything crosses this seam as an `Analysis`: a result, "still warming", or an honest
reason it cannot be answered. Keep it ChordPro-ignorant — no chords, no lines, no
directives. Anything needing both belongs in `analysis.py`.

## Verified facts about prosodic 3.10, so you need not re-derive them

- **`langs.get_word(token, lang)` is the cheap entry point.** Returns
  `(sylls_ll, meta)` — a list of pronunciation *variants*, each a list of
  `(ipa, syllable_text)` tuples. No `Text`, no DataFrame, no metrical parse.
- **Syllable texts partition the token exactly**, so cumulative lengths locate each one.
  Compare **lengths, never text**: the g2p path skips `fix_recasing` and may hand back a
  lowercased token that is still a correct partition.
- **`utils.get_syll_ipa_stress(ipa)`** → `'P'` / `'S'` / `'U'`, parsed into `Stress` at
  this boundary and nowhere else.
- **`meta['ipa_origin']`** is `'dict'` or `'tts'` — i.e. whether espeak guessed it.
- **An out-of-vocabulary word raises `RuntimeError`** when espeak is missing. That is a
  normal Tuesday for lyrics, so it becomes `Unavailable`, never an exception escaping.
- **Import costs ~1.5s warm, far more cold.** Hence the background warm-up.
- **Prosodic's warnings go to stderr**, but the import is still wrapped in
  `redirect_stdout(sys.stderr)`: one stray print from any of ~30 transitive dependencies
  would corrupt the JSON-RPC stream and be miserable to diagnose.

## Two traps

**Never memoise a `Warming` answer.** `syllabify` checks readiness and only then calls
the `lru_cache`d `_syllabify`. Caching `Warming` would pin a word to "still loading" for
the life of the server. `test_warming_is_never_memoised` guards this.

**A bare `WordForm` has no `key`.** Its rhyme methods are `@cache`d, so they need a hash,
which normally comes from a parent. Build them with an explicit
`key=f"melic.wordform.{token}"` — see `_wordform_cached`.

## Rhyme

Built from `get_word` output directly — no `Text`, no parse, no metrical machinery.
`rime_type` returns `'perfect'`, `'slant'`, `'assonance'` or `None`, and prosodic's own
calibration says to count **perfect and slant only**: including assonance triples the
false-positive rate for almost no extra recall. `rhymes()` encodes that; don't loosen it.

`rime_distance` returns `nan` past its cap, so classify with `rime_type`, not the scalar.
The 2-D signal underneath is exposed as `prosody.rime_distance_nc()` → `(nucleus, coda)`
or None, since `nan` (identical tokens, or no rime) is not a small distance. That is the
only new thing this seam offers; the decision of what to do with the numbers is not
prosodic's, and does not live here.

`prosody.rhymes()` is the boolean; `rhyme.classify()` is what the features use, and it
keeps *how* two endings chime as a `Chime` — `PERFECT`, `SLANT` or `IDENTICAL`, rendered
as ``, `~` and `=`. Do not collapse it back to a boolean: the quality is computed on
every comparison either way, and throwing it away is the bug this replaced.

`IDENTICAL` is where we deliberately depart from prosodic: a word does not rhyme with
itself, which is right about rhyme and wrong about songs. A refrain ending "home" every
time is the same slot in the scheme, and `classify` short-circuits to `IDENTICAL` on
matching tokens before prosodic is consulted at all.

## The one sanctioned relaxation, and where it is allowed to live

`rhymes()` and `classify()` stay strict — **do not loosen them**, and do not make
assonance a rhyme globally, which is exactly the trade prosodic measured and rejected.

`rhyme.solve()` is the gated relaxation instead. It may admit a near miss (nucleus
identity plus a coda within `CONTEXTUAL_CODA_MAX`, both in `rhyme.py`) **only where the
song's structure vouches for it** — the stanza already has a strict group, another
stanza could spell the same shape, or `{x_melic_scheme}` declares it — and marks what it
admits `Chime.CONTEXTUAL` (`≈`) rather than folding it into `SLANT`. The thresholds are
ours, not prosodic's, which is why they sit in `rhyme.py` with the measurements that
chose them, while `prosody.py` only reports distances.

Two bounds keep the search from costing more than the document: `MAX_FREE_LINES` (how
many endings get compared) and `MAX_CANDIDATES` (how many readings get weighed). Without
the second, a stanza with weak edges in every direction takes seconds — measured, and
pinned by `test_a_stanza_whose_near_misses_are_tangled_keeps_its_strict_scheme`.
`melic.rhyme.slantScope: strict` turns the whole solver off and leaves the strict pass.
