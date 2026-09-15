# melic-lsp

A [Chordpro](http://chordpro.org/) language server, designed for songwriting.

![Demo Screenshot](./docs/Screenshot.png)


This wraps [`quadrismegistus/prosodic`](https://github.com/quadrismegistus/prosodic)
and displays its information via LSP.

## Features

|                    |                                                                |
| ------------------ | -------------------------------------------------------------- |
| **Highlighting**   | Syllables coloured by lexical stress                           |
| **Line signature** | Syllable count at the end of each line                         |
| **Rhyme**          | Line endings labelled with rhyme, with slant rhyme support     |
| **Hover**          | Docs and detailed analysis available on hover                  |
| **Diagnostics**    | ChordPro syntax, chord placement                               |
| **Quick fixes**    | Move a chord onto the start of the syllable it landed inside   |
| **Hints**          | Opt-out notes where a stanza drifts from the shape of its siblings |
| **Outline**        | Sections and their stanzas, each with its syllable profile     |
| **Analysis**       | tools for chord/syllable/stress grid and cross-work comparison |

## Line hints

By default, Each line is annotated with its syllable count and rhyme scheme
```
Swing [D]low, sweet [G]chari[D]ot,       6σ A
Comin' for to carry me [A7]home.         8σ B
Swing [D]low, sweet [G]chari[D]ot,       6σ A=
Comin' for to [A7]carry me [D]home.      8σ B=
```

`~` marks a slant rhyme, `=` a same-word rhyme, and `≈` a near rhyme. Melic attempts
to infer rhymes based on the structure of your song, but this is a work in progress.

You can also manually declare a rhyme scheme

```
{x_melic_scheme: ABAB}            this section
{x_melic_scheme: chorus = ABXAB}   every chorus in the song
```

Declaring one is worth more than a hint to check against. It tells Melic how you sing
the lines, so that stanza's endings get a more generous hearing than they would on
their own — enough for the `-ing`/`-in'` that carries a lot of folk song:

```
Oh if I was a blackbird, could whistle and sing,     12σ A
I'd follow the vessel my true love sails in,         11σ A≈
```

Without the declaration those two are left unlabelled, because `sing`/`in` is past
what Melic will call a rhyme unprompted. The extra latitude only ever goes toward the
shape you declared, though, and it stops well short of pretending: a different vowel,
or one line ending on a vowel where the other ends on a consonant, is still no. A
stanza that does not rhyme will still be reported as not matching what you declared.

## Hints

Melic has some configurable hints:

| Setting | Fires when |
| --- | --- |
| `melic.hints.rhymeSchemeMismatch` | a stanza rhymes unlike the pattern it declares, or unlike the matching stanza of the first section of its kind |
| `melic.hints.parallelLineDrift` | a line's syllable count is more than `tolerance` (1) from the line it lines up with |
| `melic.hints.chordProgressionDrift` | a line carries more than `tolerance` (2) syllables away from what the other lines over those same chords carry |

## The stress pattern

`melic.lineSignature.mode` will put the stress marks in the margin too:

```
Swing [D]low, sweet [G]chari[D]ot,       6σ · + [D]++ [G]+- [D]-
Comin' for to carry me [A7]home.         8σ · +---+-- [A7]+
```

`+` primary stress · `^` secondary · `-` unstressed. 

## Manual Annotations.

Melic takes your chordpro annotations into account when syllabalizing words.
Melic will prefer *cha·ri·ot* over *cha·riot* when the word is labelled `chari[D]ot`.
You can also apply manual overrides for specific words

```
{x_melic_word: chariot = +cha -ri -ot}      the whole document
{x_melic_word_section: fire = +fire}        the enclosing section
{x_melic_word_line: fire = +fi -re}         the next lyric line
{x_melic_scheme: ABAB}                      the rhyme pattern of this section
```

### espeak

`prosodic` supports using [espeak](https://github.com/espeak-ng/espeak-ng) to infer pronunciation of words not in its dictionary.
This extension does not bundle espeak, but it will be used if it is available in the extension's environment.

Espeak is generally available in your package manager
```bash
brew install espeak-ng
sudo apt install espeak-ng
choco install espeak-ng
```

### pytorch

`prosodic` also supports using [pytorch](https://github.com/pytorch/pytorch) to speed up automated scansion
This extension does not bundle pytorch, but it will be used if it is available in the extension's environment.

```bash
uv tool install torch --torch-backend=auto
```

## Development
We welcome contributions! We currently only ship an extension for VSCode:

```bash
uv sync
cd editors/vscode && npm install && cd -
brew install espeak
```

Then F5 in `editors/vscode` to open an Extension Development Host.

A vim binding might be a good first contribution 👀

We have a basic test suite, and a bit of custom tooling for types
```bash
uv run pytest                      # ~2s
./scripts/check_types.sh           # src/ clean, and wrong-space calls rejected
./scripts/check_versions.sh        # pyproject and package.json agree
uv run python scripts/bench_tier1.py   # gates the caching decision
uv run python scripts/smoke_lsp.py     # real LSP handshake against the real server
```

To reload during development, run

```bash
uv tool install . --force --reinstall
```

`--reinstall` is not optional: uv caches the built wheel under the version, which
rarely changes, so `--force` alone happily reinstalls the same stale copy and says it
succeeded. It matters because the extension runs the first server it finds — a trusted
workspace's `.venv`, then `~/.local/bin/melic-lsp`, and only then the copy it bundled —
so a stale global install outranks the bundle and is what you end up editing against.
The workspace `.venv` is an editable install pointing at `src/`, so only the global
copy ever drifts, which is why this hides until you open a file outside the repo.

## Releasing

The version lives in two files and the tag has to agree with both. `npm version` keeps
`package-lock.json` in step:

```bash
# bump `version` in pyproject.toml, then
cd editors/vscode && npm version X.Y.Z --no-git-tag-version && cd -
./scripts/check_versions.sh vX.Y.Z
git push origin main
git tag vX.Y.Z && git push origin vX.Y.Z
```

The tag does the rest: the full CI suite runs first, then one VSIX per platform is
built and attached to a GitHub Release.

Publishing onward to the extension registries is opt-in, one repository secret each:

| Secret | Buys |
|---|---|
| `VSCE_PAT` | the VS Code Marketplace |
| `OVSX_TOKEN` | Open VSX |

Neither is required. With a secret unset, its step is skipped, the run says so in a
notice, and the release is GitHub-only — the attached VSIXes still install by hand.
