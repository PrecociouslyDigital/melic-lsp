# melic-lsp

A prosody language server for ChordPro files.

Writing a song means juggling three things the plain text doesn't show you: how many
syllables a line has, which of them are stressed, and where the chords change relative
to those syllables. Two verses sung to the same melody have to agree on all three, and
normally you can only check that by singing it.

This wraps [`quadrismegistus/prosodic`](https://github.com/quadrismegistus/prosodic) —
which already solves the hard linguistic half — in a language server, so the answers
show up where the writing happens.

## The line signature

The core artifact, shown at the end of each lyric line:

```
Swing [D]low, sweet [G]chari[D]ot,     5σ · + [D]++ [G]+- [D]
Comin' for to carry me [A7]home.       8σ · +---+-- [A7]+
```

`+` primary stress · `^` secondary · `-` unstressed. Marks are grouped by the chord
covering them, and a run before the first bracket is sung before any chord. Line one
changes chord every couple of syllables; line two holds one chord for seven. Both scan
plausibly, and that difference is invisible in the plain text.

A trailing `?` on the count (`6σ?`) means a word had no pronunciation available, so the
number is a floor rather than a total.

## Features

| | |
|---|---|
| **Highlighting** | Syllables coloured by lexical stress, with alternating bands so neighbours stay distinct |
| **Line signature** | The above, as an end-of-line inlay hint |
| **Rhyme** | Line endings labelled `a`/`b`/… per section |
| **Hover** | *word* → syllables, IPA, stress, weight, alternate pronunciations. *blank space* → metrical scan and rhyme partners. *directive* → ChordPro docs |
| **Diagnostics** | ChordPro syntax (unclosed `[`/`{`, unknown directive with did-you-mean, unmatched environment), plus chord-lands-mid-syllable and guessed-pronunciation hints |
| **Outline** | Sections, each with its syllable profile — `Verse 1 · 8,6,8,6σ` |
| **Commands** | `Melic: Compare Sections` stacks parallel lines; `Melic: Scansion Panel` shows a chord/syllable/stress grid |

Cross-line comparison is deliberately opt-in. Two verses that disagree on syllable
count might be a mistake or might be the song, and a squiggle can't tell the
difference — so divergence appears in the compare view, where you can look at it,
never as a passive diagnostic.

## Setup

```bash
uv sync
cd editors/vscode && npm install && cd -
brew install espeak      # optional; see below
```

Then F5 in `editors/vscode` to open an Extension Development Host.

The VS Code client contributes no language or grammar — `aleskabourek.vschordpro`
already registers the `chordpro` language ID and its TextMate grammar, and two grammars
over one language fight. This layers semantic tokens on top.

### espeak

`prosodic` ships a 2.75 MB English dictionary, so common words resolve without espeak.
espeak is the fallback for anything missing, and lyrics are full of words that miss —
`wayfaring` and `wretch` both do. Without it those words yield a hint diagnostic and are
excluded from counts (which is why the `?` marker exists). Everything degrades; nothing
crashes.

## Settings

All under `melic.*`: `stressHighlight.enabled`, `lineSignature.mode`
(`chord-grouped` | `flat` | `count-only` | `off`), `inlayHints.perSyllable`,
`rhyme.enabled`, `diagnostics.chordpro`, `diagnostics.chordMidSyllable`,
`diagnostics.unknownPronunciation`, `lang`, `serverPath`.

## Development

```bash
uv run pytest                      # ~90 tests, ~1.5s
./scripts/check_types.sh           # src/ clean, and wrong-space calls rejected
./scripts/check_versions.sh        # pyproject and package.json agree
uv run python scripts/bench_tier1.py   # gates the caching decision
uv run python scripts/smoke_lsp.py     # real LSP handshake against the real server
```

CI runs all of these on every push, with the server suite run **twice** — once with
espeak installed and once without. Both are supported configurations and the
degradation path is easy to break without noticing.

### Releasing

```bash
./scripts/check_versions.sh v0.2.0     # after bumping both version fields
git tag v0.2.0 && git push --tags
```

The tag must match the version in `pyproject.toml` and `editors/vscode/package.json`;
CI refuses the release otherwise. That builds the `.vsix`, runs the full suite, and
attaches the package to a GitHub Release — no configuration required beyond having a
GitHub remote.

Publishing to the extension registries is **opt-in**: each step is skipped unless its
secret exists, so nothing below is needed to cut a release.

| Target | Secret | What it takes |
|---|---|---|
| GitHub Release | — | Works out of the box. Users install with `code --install-extension melic-lsp-*.vsix` |
| VS Code Marketplace | `VSCE_PAT` | An Azure DevOps organisation, a publisher created at [manage](https://marketplace.visualstudio.com/manage), and a PAT scoped to **Marketplace → Manage**. The `publisher` field in `editors/vscode/package.json` must match the publisher ID you register — it currently says `melic` |
| Open VSX | `OVSX_TOKEN` | An [open-vsx.org](https://open-vsx.org) account, a signed Eclipse Contributor Agreement, and an access token. This is the registry VSCodium and other forks use |

Also worth adding before publishing anywhere: a `repository` field in the extension's
`package.json` (CI passes `--allow-missing-repository` until there is a remote to point
at), and an icon.

### How it's put together

```
types.py       three coordinate spaces as newtypes, and the ADTs
chordpro.py    parsing and position mapping — no prosodic, no LSP
prosody.py     the only module that imports prosodic
analysis.py    joins the two
signature.py   LineAnalysis -> the string above
sections.py    grouping and parallel-line alignment
rhyme.py       end-rhyme, from cached word data only
server.py      pygls registration and warm-up
features/      one module per LSP feature
```

**The critical seam is `chordpro.py`.** All the position-mapping logic — the
highest-risk code here — has no prosodic dependency, so it is testable in milliseconds
without loading a dictionary. One exhaustive round-trip test over the fixtures checks
that every lyric offset maps back to the same character, which subsumes chord-split
words, leading and trailing chords, unicode and apostrophes.

**Three coordinate spaces, three newtypes.** Prosodic reports syllable offsets within a
word; chords are stripped in lyric space; the editor draws in source space. Each hop has
exactly one bridge, so passing an offset from the wrong space is a type error rather
than a highlight one character off. `scripts/check_types.sh` proves this by requiring
the checker to *reject* `scripts/coordinate_space_violations.py`.

**Caching is word-level only.** Prosodic memoises `get_word`; we memoise the derived
offsets on top. There is no line cache, no document cache and no invalidation logic,
because tier 1 over a 200-line song measures ~3 ms warm against a 10 ms budget. That
decision is measured, not assumed — `scripts/bench_tier1.py` re-checks it and fails if
it ever exceeds 50 ms.

**Two tiers.** Syllables, stress and rhyme are computed on demand for every request.
The metrical parse (`prosodic.Text` + `line.parse()`) costs seconds on first use and is
kept strictly behind hover, with the model load pre-warmed in the background so the
first hover isn't a stall.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).

Copyright (C) 2026 Sydney.

This follows `prosodic`, which this depends on directly. Note that prosodic's package
metadata declares Apache-2.0 while the LICENSE file it ships is GPLv3; GPL is the safe
reading either way, since Apache-2.0 is one-way compatible into GPLv3.

This program is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version. It is distributed in
the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
Public License for more details.
