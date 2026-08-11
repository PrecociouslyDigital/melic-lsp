# Overview

`melic-lsp` is a prosody language server for ChordPro song files (`.cho`). It wraps
[`prosodic`](https://github.com/quadrismegistus/prosodic) — syllabification, lexical
stress, IPA, rhyme, metrical scansion — so that syllable counts, stress and chord
alignment are visible while writing lyrics, instead of only discoverable by singing.

Two halves, both in this repo:

- **`src/melic_lsp/`** — the Python LSP server (`pygls`), installed as `melic-lsp`.
- **`editors/vscode/`** — a thin `vscode-languageclient` extension.

The margin at the end of each lyric line carries the syllable count and the rhyme:

```
Swing [D]low, sweet [G]chari[D]ot,     6σ A
Comin' for to carry me [A7]home.       8σ B
Swing [D]low, sweet [G]chari[D]ot,     6σ A=
```

Letters run per section; `~` is a slant rhyme, `=` the same word ending a line again. A
trailing `?` on the count means a word had no pronunciation, so the number is a floor.

The **line signature** — stress marks grouped by chord, `6σ · + [D]++ [G]+- [D]-` — is
`melic.lineSignature.mode` away, but it lives properly in the Scansion Panel and Compare
Sections, which are column-aligned. An inlay hint is not, and comparing patterns line
against line is the only reason to print them.

# Core dev loop

```bash
uv run pytest -q                      # ~124 tests, ~2s
./scripts/check_types.sh              # ty clean AND wrong-space calls rejected
./scripts/check_versions.sh           # pyproject and package.json agree
uv run python scripts/bench_tier1.py  # gates the no-cache decision
uv run python scripts/smoke_lsp.py    # real LSP handshake against the real server
cd editors/vscode && npm run check-types
```

The last two matter more than they look. `check_types.sh` fails if the type checker
*accepts* a mixed-up coordinate space; `smoke_lsp.py` speaks real JSON-RPC to the real
binary and catches whole classes of failure no unit test sees.

CI runs all of it, with the server suite run twice — once with espeak installed and once
without. Both are supported configurations.

# Things that have already bitten, once each

Read the scoped rule before editing the matching area, but these are the ones that cost
real debugging time:

1. **`str.splitlines()` is wrong here.** It breaks on `\x0c`, ` `, `\x85`; editors
   don't. Row indices would silently drift. Use `chordpro._NEWLINE`.
2. **Server command ids and palette command ids must be disjoint.** A language client
   auto-registers an editor command for every id the server advertises; sharing one
   crashes initialization before anything renders. `smoke_lsp.py` checks this.
3. **`uv tool install .` installs a snapshot.** After changing the server, anywhere
   outside this workspace still runs the old copy until `uv tool install . --force`.
4. **Never memoise a `Warming` result.** The cache deliberately sits *behind* the
   readiness check in `prosody.py`.

# Conventions

- `uv` for Python, `npm` for the extension. Target Python 3.12+ (CI runs 3.12).
- Type check with `ty` (Astral). Pylance covers the editor.
- Prefer bash for ad-hoc scripts; if Python, stdlib only.
- Commit messages via the commit-writer subagent.
- GPL-3.0-or-later, because prosodic is. See the note in `README.md` — prosodic's own
  metadata says Apache-2.0 while the file it ships is GPLv3.
