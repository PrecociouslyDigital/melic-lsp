---
paths:
  - "src/melic_lsp/server.py"
  - "src/melic_lsp/features/**/*.py"
  - "src/melic_lsp/settings.py"
  - "src/melic_lsp/signature.py"
---

# The server and its features

`pygls` **2.x** — note the v2 import layout (`pygls.lsp.server.LanguageServer`) and that
handlers are registered with `@server.feature(...)`. Diagnostics use the **pull** model
(`textDocument/diagnostic`), so there is no invalidation to get wrong.

`MelicServer.analyse(uri)` recomputes tier 1 per request. That is deliberate — see the
caching note in `architecture.md`. Do not add a document cache.

## The command-id trap that took the server down once

A language client **auto-registers an editor command for every id the server advertises**
in `executeCommandProvider`. The extension separately registers its own palette commands.
If those id sets overlap, the second registration throws *during initialization* and the
entire session dies before a single hint renders.

So they are kept disjoint on purpose:

| | |
|---|---|
| Palette (extension, in `contributes.commands`) | `melic.compareSections`, `melic.scansionPanel` |
| RPC entry points (server, `@server.command`) | `melic.server.compareSections`, `melic.server.scansionPanel` |

`scripts/smoke_lsp.py` intersects the two sets and fails if they overlap. Keep that check
if you touch either side.

Also: pygls spreads `executeCommand` arguments across the handler's parameters and
converts each by its annotation. Declare `def handler(ls, uri: str)`, not a `list[Any]` —
annotating a list makes cattrs structure the URI string into a list of characters.

## Warm-up

`INITIALIZED` runs `warm_up` via `asyncio.to_thread` (keeping the event loop free), then
asks the client to refresh once, then pre-warms tier 2. Requests arriving before that
answer `Warming`, and the signature renders `…` rather than a confident `0σ`.

`_refresh(ls)` is that redraw, and it covers semantic tokens, inlay hints **and
diagnostics**. Diagnostics belong in it because the hints refuse to compare a warming
line, so without the third refresh they would stay silent until the next keystroke.
`on_configuration` calls it too: turning a rule off is not an edit, and nothing else
would ask for the repaint.

## Feature notes

- **Semantic tokens** are delta-packed quintuples; a syllable spanning a chord emits one
  token per source range. Inexact (`WholeWord`) syllables are skipped, not guessed at.
- **Signature** lives in `signature.py`; `count_label()` is the single place the `?`
  uncertainty marker is applied. Anywhere showing a syllable count must use it, or a
  missing dictionary entry reads as a genuinely short line. `render()` takes its `Mode`
  with no default on purpose — the default is `Settings.signature` and only there.
- **The margin defaults to count plus rhyme, not stress marks.** Inlay hints sit flush
  against text of varying length, so nothing in that column lines up with anything else,
  and lining marks up is the entire reason to read them. `views.py` shows them in
  columns instead. `chord-grouped` remains one setting away for anyone who wants it.
- **Diagnostics** are per line. `diagnostics.py` compares nothing across lines and must
  stay that way: two verses disagreeing on syllable count might be a mistake or might be
  the song. A guessed pronunciation is likewise not flagged — `{x_melic_word}` is the fix
  for that, and marking every invented word in a lyric sheet is noise you learn to ignore.
- **`hints.py` is the governed exception**, and the only place a cross-line judgement is
  published. Three rules — `rhymeSchemeMismatch`, `parallelLineDrift`,
  `chordProgressionDrift` — each with its own `melic.hints.<rule>.severity` (`off` is a
  supported answer) and, for the count rules, a tolerance. The constraints that earn them
  the exception, all of which have tests:
  - Every rule refuses to fire while a compared line is **warming** or holds an
    **unresolved** word: its count is a floor, not a total. This is also what keeps the
    espeak-less CI leg quiet.
  - The stack rules and the progression rule run only on **explicitly-kinded** sections.
    In an undirected song every blank-line stanza is one implicit kind, and a chorus hook
    would be held against a verse line. A **declared** scheme is its own norm and applies
    wherever it is written, implicit stanzas included.
  - Every hint carries `source` and a `code` — the code *is* the settings key — and names
    its evidence in `related_information`, capped at `RELATED_CAP`.
  - The progression rule needs a group of `MIN_PROGRESSION_GROUP` and a strict-majority
    mode before it has a norm, and skips rows `parallelLineDrift` already claimed.
  `smoke_lsp.py` pins the defaults by asserting **zero coded diagnostics on
  `swing_low.cho`**; `drift.cho` is the fixture where each rule does fire.
- **Hover** is the one place tier 2 may run, and must say when a reading came from a
  manual annotation rather than the dictionary.
