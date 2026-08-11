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
each start/end pair from one row. Environments carry `EnvKind.LYRIC` or
`EnvKind.VERBATIM`, which is what excludes tab and grid blocks from analysis.

**`lookup()` checks the table before the `x_` rule.** Our own `x_melic_*` directives are
registered, and the generic "anything starting with `x_` is custom" fallback would
otherwise shadow them with a documentation-free stub.

## Manual overrides

`overrides.py` parses `{x_melic_word: chariot = +cha -ri -ot}` and its `_section` /
`_line` variants. Precedence: **line → section → document → chord-aware → dictionary.**

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

Explicit environments win; otherwise blank lines mark stanzas. A blank line *inside* an
environment does not split it — the author already said where the section ends. Ragged
tails in `Stack.rows` are left ragged, since a verse with an extra line is exactly the
divergence worth seeing.
