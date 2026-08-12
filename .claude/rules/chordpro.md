---
paths:
  - "src/melic_lsp/chordpro.py"
  - "src/melic_lsp/overrides.py"
  - "src/melic_lsp/sections.py"
---

# Parsing ChordPro — pure, and deliberately prosodic-free

`chordpro.py` has no prosodic dependency and must keep it that way. It classifies every
line into a sum type and turns lyric lines into position-mapped data.

```python
type Line = Blank | Comment | Directive | Verbatim | Lyric
```

Only `Lyric` carries `chords`/`spans`. `Verbatim` — the contents of `{sot}`, `{sog}`,
abc and ly blocks — is excluded from analysis **structurally**, because it simply is not
a `Lyric`, rather than by an `if` someone forgets. Handle with `match` and `assert_never`
so a new line kind surfaces as an error at every site that must care.

## Do not use `str.splitlines()`

It also breaks on `\v`, `\f`, `\x1c`–`\x1e`, `\x85`, U+2028 and U+2029. Editors break on
`\n`, `\r\n`, `\r` and nothing else, so a document containing any of those characters
would give every row below it an index the editor disagrees with — silently misplacing
every annotation. Use `_NEWLINE`. `test_rows_ignore_characters_editors_do_not_break_on`
guards it.

The trailing empty line after a final newline is kept on purpose: the editor shows it.

## Directives

`DIRECTIVES` is built from `_SIMPLE` plus `_ENVIRONMENTS`, which generates both halves of
each start/end pair from one row, plus `_MELIC`. Environments carry `EnvKind.LYRIC` or
`EnvKind.VERBATIM`, which is what excludes tab and grid blocks from analysis.

**`_MELIC` is the whole of what our own directives are**: a name, and the documentation
hover shows for it, with nowhere else either can be written. `_melic()` is the only way
one is built and its `doc` parameter has no default, `overrides.py` imports the names
from here rather than spelling them again, and `DirectiveSpec.doc` carries the prose to
hover — so a fifth directive is documented and parsed by the same edit, or it does not
exist. `test_hover.py` walks the table rather than a list of its own.

**`lookup()` checks the table before its two generic rules.** Our own `x_melic_*`
directives are registered, and the "anything starting with `x_` is custom" fallback would
otherwise shadow them with a documentation-free stub. The same order matters for
environments: the spec allows `{start_of_x}` for any `x`, so `_environment()` resolves
whatever the table has never heard of — `{start_of_intro}`, `{start_of_solo}` — as
`EnvKind.LYRIC`. Unknown means lyrics because the verbatim environments are a closed set
the table already names, and a solo that is nothing but chords has no lyrics to find.

`env_label()` unwraps the modern `{start_of_verse: label="Verse 1"}` to `Verse 1`, and is
the one place a section's name is read out of a directive value.

## Manual annotations

`overrides.py` parses `{x_melic_word: chariot = +cha -ri -ot}` and its `_section` /
`_line` variants. Precedence: **line → section → document → chord-aware → dictionary.**

It also parses `{x_melic_scheme}`, in two forms:

```
{x_melic_scheme: ABAB}            the enclosing section, or the next one
{x_melic_scheme: chorus = ABAB}   every chorus in the song
```

Three things about it that are decisions rather than details:

- **It lands on stanzas, not sections**, and only on those whose line count matches the
  pattern — a scheme is measured over a stanza, and holding a six-line stanza to a
  four-letter pattern would compare two things that were never the same shape.
- **The grammar lives in `rhyme.py`** (`canonical_pattern`), because a declaration is
  compared against a `scheme_string` and the two must agree on the alphabet. Letters are
  renamed into first-appearance order, and a letter used once reads as `X` — no group of
  one is ever lettered, so no stanza could spell such a shape. `overrides.py` owns the
  discovery, the scoping and the `Problem` reporting, and nothing else.
- **It is an expectation, not an instruction.** It corroborates a weak edge the phonetics
  already allow and reports a stanza that drifts from it; it cannot make two words rhyme.
  Forcing a pair would be a different directive (`{x_melic_rhyme}`), and is not built.

Two things to preserve:

- **`_annotations()` is the swap point.** Finding annotations is deliberately separated
  from parsing them, because `x_` directives are spec-legal but *do* render as grey text
  in vschordpro's preview, while `#` comments are dropped by every renderer. Moving the
  annotations must stay a one-function change.
- **Validation is textual, not length-based.** `types.tile()` compares lengths, which is
  sound for prosodic (guaranteed to partition) but far too weak for hand-typed input — a
  same-length typo would sail straight through. Overrides compare the joined syllables to
  the token case-insensitively.

## Sections

**Section → stanza → line.** A `{start_of_verse}` holding four quatrains is one section
of four stanzas, not a sixteen-line verse: a rhyme scheme measured across all four is
noise, and `analysis.py` labels rhymes per *stanza*.

One rule builds both levels: **a blank line ends the stanza, and outside an environment
it ends the section too.** Outside one there is nothing else to go on, so an undirected
song is a run of single-stanza sections — exactly the shape it had before stanzas
existed. `Section.lines` flattens, for the callers that want it whole.

Anything scoped by rhyme must use the **stanza**: `server.py` hands hover the enclosing
stanza's lines, or hover would name partners the margin never labelled. `overrides.py` is
the opposite case and correctly uses the section — `{x_melic_word_section}` means the
whole verse.

`Stack.blocks` aligns stanza against stanza, then line against line inside each, so a
sixteen-line verse compared with an eight-line one does not pair line 1 with line 1 and
drift from there. Ragged tails are left ragged, since a stanza with an extra line is
exactly the divergence worth seeing.
