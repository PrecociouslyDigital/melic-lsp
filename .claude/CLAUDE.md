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

Letters run per stanza. `~` is a slant rhyme, `=` the same word ending a line again, and
`≈` a near rhyme the *solver* admitted — same vowel, a coda a little off — which is only
ever labelled where the song's structure vouches for it (`melic.rhyme.slantScope`). A
trailing `?` on the count means a word had no pronunciation, so the number is a floor.

A song can declare the shape it means to have, which the solver honours and the hints
measure against: `{x_melic_scheme: ABAB}` for a section, `{x_melic_scheme: chorus = ABAB}`
for every section of a kind.

The **line signature** — stress marks grouped by chord, `6σ · + [D]++ [G]+- [D]-` — is
`melic.lineSignature.mode` away, but it lives properly in the Scansion Panel and Compare
Sections, which are column-aligned. An inlay hint is not, and comparing patterns line
against line is the only reason to print them.

# Core dev loop

```bash
uv run pytest -q                      # ~2s
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
3. **`uv tool install .` installs a snapshot, and `--force` is not enough to refresh
   it.** Anywhere outside this workspace runs the globally installed copy, and uv caches
   the built wheel under `melic-lsp==<version>`. The version rarely changes, so `--force`
   happily reinstalls the *same cached wheel* and the code never updates — silently, with
   a success message. Use **`uv tool install . --force --reinstall`**, then verify against
   the installed interpreter rather than trusting the output:

   ```bash
   uv tool install . --force --reinstall
   "$(uv tool dir)/melic-lsp/bin/python" -c "from melic_lsp.chordpro import lookup; print(lookup('start_of_anything'))"
   ```

   The in-workspace `.venv` is an editable install pointing at `src/`, so it is never
   stale; only the global copy drifts, which is why this hides until you open a file
   outside the repo.
4. **Never memoise a `Warming` result.** The cache deliberately sits *behind* the
   readiness check in `prosody.py`.
5. **The rhyme solver needs both its bounds.** `MAX_FREE_LINES` caps the endings it
   compares; `MAX_CANDIDATES` caps the readings it weighs, and only the second stops a
   stanza with weak edges in every direction from taking **seconds** — a free line with
   an edge to several groups multiplies readings rather than adding to them. Measured,
   and pinned by a test.

# Conventions

- `uv` for Python, `npm` for the extension. Target Python 3.12+ (CI runs 3.12).
- Type check with `ty` (Astral). Pylance covers the editor.
- Prefer bash for ad-hoc scripts; if Python, stdlib only.
- Commit messages via the commit-writer subagent.
- GPL-3.0-or-later, because prosodic is. See the note in `README.md` — prosodic's own
  metadata says Apache-2.0 while the file it ships is GPLv3.
