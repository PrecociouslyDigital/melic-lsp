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

## Feature notes

- **Semantic tokens** are delta-packed quintuples; a syllable spanning a chord emits one
  token per source range. Inexact (`WholeWord`) syllables are skipped, not guessed at.
- **Signature** lives in `signature.py`; `count_label()` is the single place the `?`
  uncertainty marker is applied. Anywhere showing a syllable count must use it, or a
  missing dictionary entry reads as a genuinely short line.
- **Diagnostics** deliberately contain *no* cross-line comparison. Two verses disagreeing
  on syllable count might be a mistake or might be the song, and a squiggle cannot tell.
  Divergence belongs in the compare view, on request. A guessed pronunciation is likewise
  not flagged — `{x_melic_word}` is the fix for that, and marking every invented word in
  a lyric sheet is noise you learn to ignore.
- **Hover** is the one place tier 2 may run, and must say when a reading came from a
  manual annotation rather than the dictionary.
