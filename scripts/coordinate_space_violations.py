"""Deliberate coordinate-space errors — every line here MUST fail type checking.

This file is never imported and never run. It exists so that `check_types.sh` can
prove the newtypes in types.py actually reject a mixed-up offset, because newtypes
that nothing enforces are pure noise.
"""

from melic_lsp.types import LyricCol, SpanMap, SrcCol, WordCol, WordSpan

span_map = SpanMap(())

span_map.to_source(WordCol(0), WordCol(1))  # word space into a lyric-space bridge
span_map.to_source(SrcCol(0), SrcCol(1))  # source space back into lyric space
span_map.to_source(0, 1)  # bare ints skipping the wrapping entirely

WordSpan("x", LyricCol(0)).lyric_col(LyricCol(3))  # lyric offset as a word offset
WordSpan("x", WordCol(0))  # a token located in the wrong space to begin with
