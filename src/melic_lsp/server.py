"""The pygls server: registration, settings, and the warm-up that hides tier 0.

Prosodic takes seconds to import, so it is loaded off the event loop after
``initialized``. Requests arriving in the meantime answer ``Warming`` rather than
zero, and one refresh once loading finishes replaces the placeholders.
"""

from __future__ import annotations

import asyncio
import logging
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from . import prosody
from .analysis import DocumentAnalysis, analyse_document
from .features import diagnostics, hints, hover, inlay_hints, symbols, views
from .features.semantic_tokens import LEGEND, encode
from .settings import Settings
from .types import SrcCol, Unavailable

try:
    VERSION = version("melic-lsp")
except PackageNotFoundError:  # a source checkout that was never installed
    VERSION = "0.0.0+dev"


class MelicServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("melic-lsp", VERSION)
        self.settings = Settings()

    def analyse(self, uri: str) -> DocumentAnalysis:
        """Tier 1 over a whole document. Measured at ~3 ms for 200 lines, warm.

        Recomputed per request rather than cached: prosodic memoises per word and
        we memoise the derived offsets, so a re-scan is dictionary lookups. A
        document cache would only add invalidation bugs.
        """
        document = self.workspace.get_text_document(uri)
        return analyse_document(
            document.source,
            self.settings.lang,
            self.settings.rhyme,
            self.settings.chord_aware_syllables,
            self.settings.slant_scope,
        )


server = MelicServer()


@server.feature(lsp.INITIALIZED)
async def on_initialized(ls: MelicServer, params: Any) -> None:
    """Load prosodic off the event loop, then ask the client to redraw once."""
    await asyncio.to_thread(prosody.warm_up, ls.settings.lang)

    status = prosody.status()
    if isinstance(status, Unavailable):
        ls.window_show_message(
            lsp.ShowMessageParams(type=lsp.MessageType.Warning, message=status.reason)
        )

    _refresh(ls)

    # Loading the syntax models costs seconds the first time a metrical scan runs.
    # Doing it here makes the first hover instant and costs the user nothing.
    await asyncio.to_thread(prosody.prewarm_scansion, ls.settings.lang)


def _refresh(ls: MelicServer) -> None:
    """Ask the client to redraw everything a change may have altered.

    Diagnostics are in the list because the cross-line hints refuse to compare a line
    that is still warming: without a pull after warm-up they would stay silent until
    the next keystroke, and after a settings change they would keep answering with the
    settings they were computed under.
    """
    for refresh in (
        ls.workspace_semantic_tokens_refresh,
        ls.workspace_inlay_hint_refresh,
        ls.workspace_diagnostic_refresh,
    ):
        try:
            refresh(None)
        except Exception:  # noqa: BLE001 - a client may not support refreshing
            logging.getLogger(__name__).debug("client declined refresh", exc_info=True)


@server.feature(lsp.INITIALIZE)
def on_initialize(ls: MelicServer, params: lsp.InitializeParams) -> None:
    ls.settings = Settings.parse(params.initialization_options)


@server.feature(lsp.WORKSPACE_DID_CHANGE_CONFIGURATION)
def on_configuration(ls: MelicServer, params: Any) -> None:
    ls.settings = Settings.parse(getattr(params, "settings", None))
    # Nothing else would ask: turning a rule off is not an edit, so without this the
    # document keeps the annotations it had until the next keystroke.
    _refresh(ls)


@server.feature(lsp.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL, LEGEND)
def semantic_tokens(ls: MelicServer, params: lsp.SemanticTokensParams) -> lsp.SemanticTokens:
    if not ls.settings.stress_highlight:
        return lsp.SemanticTokens(data=[])
    return encode(list(ls.analyse(params.text_document.uri).lines))


@server.feature(lsp.TEXT_DOCUMENT_INLAY_HINT)
def inlay_hint(ls: MelicServer, params: lsp.InlayHintParams) -> list[lsp.InlayHint]:
    model = ls.analyse(params.text_document.uri)
    visible = [
        analysis
        for analysis in model.lines
        if params.range.start.line <= analysis.line.row <= params.range.end.line
    ]
    return inlay_hints.build(visible, ls.settings, model.rhymes)


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover_(ls: MelicServer, params: lsp.HoverParams) -> lsp.Hover | None:
    model = ls.analyse(params.text_document.uri)
    row = params.position.line
    line = next((l for l in model.document.lines if l.row == row), None)
    if line is None:
        return None
    # The enclosing stanza, not the section: hover names this line's rhyme partners,
    # and the letters were handed out per stanza. A wider scope would name partners
    # the margin never labelled.
    stanza = next(
        (
            stanza
            for section in model.sections
            for stanza in section.stanzas
            if stanza.start_row <= row <= stanza.end_row
        ),
        None,
    )
    siblings = list(stanza.lines) if stanza else []
    return hover.build(
        line,
        SrcCol(params.position.character),
        siblings,
        ls.settings.lang,
        model.rhymes,
        model.overrides,
    )


@server.feature(lsp.TEXT_DOCUMENT_DIAGNOSTIC)
def diagnostic(
    ls: MelicServer, params: lsp.DocumentDiagnosticParams
) -> lsp.DocumentDiagnosticReport:
    """Pull-model diagnostics: the client asks when it wants them, so there is no
    invalidation to get wrong."""
    model = ls.analyse(params.text_document.uri)
    return lsp.RelatedFullDocumentDiagnosticReport(
        items=diagnostics.build(
            model.document, list(model.lines), ls.settings, model.overrides
        )
        # Per-line lints and cross-line hints stay in separate modules — one is
        # about a line, the other about a song — and meet here.
        + hints.build(model, ls.settings.hints, params.text_document.uri)
    )


@server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(
    ls: MelicServer, params: lsp.DocumentSymbolParams
) -> list[lsp.DocumentSymbol]:
    model = ls.analyse(params.text_document.uri)
    return symbols.build(list(model.sections), list(model.lines), model.rhymes)


# Deliberately NOT the `melic.compareSections` / `melic.scansionPanel` ids the
# extension puts in the command palette. A language client auto-registers an
# editor command for every id the server advertises here, so sharing them makes
# both sides claim the same id and the second registration throws, taking the
# whole session down. These are the RPC entry points; the palette ids wrap them.
COMPARE_SECTIONS = "melic.server.compareSections"
SCANSION_PANEL = "melic.server.scansionPanel"


# pygls spreads executeCommand arguments across the handler's parameters and
# converts each one by its annotation, so the document URI arrives as a plain str.
@server.command(COMPARE_SECTIONS)
def compare_sections(ls: MelicServer, uri: str) -> str:
    return views.compare_sections(ls.analyse(uri))


@server.command(SCANSION_PANEL)
def scansion_panel(ls: MelicServer, uri: str) -> str:
    return views.scansion_panel(ls.analyse(uri))


LATE_CANCEL = "Cancel notification for unknown message id"


def quiet_late_cancels() -> None:
    """Stop pygls warning about a cancel for a request that already finished.

    Every handler here answers synchronously, so a ``$/cancelRequest`` can only
    reach us after we have replied — the client cancels on the next keystroke and we
    were done before it asked. There is nothing to cancel and nothing to act on, but
    it lands in the editor's output channel at WARNING, several times per boot.
    """
    logging.getLogger("pygls.protocol.json_rpc").addFilter(
        lambda record: not record.getMessage().startswith(LATE_CANCEL)
    )


def main() -> None:
    server.settings = Settings()
    quiet_late_cancels()
    server.start_io()


if __name__ == "__main__":
    main()
