"""Drive the real server over stdio with a real LSP handshake.

The plumbing is not unit-tested on purpose — mocking pygls would test pygls. This
speaks the actual protocol to the actual binary instead, and checks the sequence
that no unit test covers: placeholders while prosodic loads, a refresh request when
it is ready, then real annotations.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, BinaryIO

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "swing_low.cho"


def send(stream: BinaryIO, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode()
    stream.write(b"Content-Length: %d\r\n\r\n%s" % (len(body), body))
    stream.flush()


def receive(stream: BinaryIO) -> dict[str, Any] | None:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = stream.read(1)
        if not chunk:
            return None
        header += chunk
    length = int(
        next(
            line.split(b":")[1]
            for line in header.split(b"\r\n")
            if line.lower().startswith(b"content-length")
        )
    )
    return json.loads(stream.read(length))


def await_response(stdin: BinaryIO, stdout: BinaryIO, request_id: int) -> dict[str, Any]:
    """Read until our response arrives, answering any server->client requests."""
    while True:
        message = receive(stdout)
        if message is None:
            raise SystemExit("server closed the connection unexpectedly")
        if message.get("id") == request_id and ("result" in message or "error" in message):
            return message
        if "method" in message and "id" in message:  # a request aimed at us
            send(stdin, {"jsonrpc": "2.0", "id": message["id"], "result": None})


def request(stdin: BinaryIO, stdout: BinaryIO, id_: int, method: str, params: Any) -> Any:
    send(stdin, {"jsonrpc": "2.0", "id": id_, "method": method, "params": params})
    message = await_response(stdin, stdout, id_)
    if "error" in message:
        raise SystemExit(f"{method} failed: {message['error']}")
    return message["result"]


def main() -> int:
    uri = FIXTURE.as_uri()
    document = {"textDocument": {"uri": uri}}
    whole_file = {
        **document,
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 99, "character": 0}},
    }

    process = subprocess.Popen(
        [sys.executable, "-m", "melic_lsp.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert process.stdin and process.stdout
    stdin, stdout = process.stdin, process.stdout
    ok = True

    capabilities = request(
        stdin, stdout, 1, "initialize",
        {
            "processId": None, "rootUri": None,
            "capabilities": {
                "workspace": {
                    "semanticTokens": {"refreshSupport": True},
                    "inlayHint": {"refreshSupport": True},
                }
            },
            # No options: the point is to see what a user actually gets.
            "initializationOptions": {},
        },
    )["capabilities"]

    for capability in (
        "semanticTokensProvider",
        "inlayHintProvider",
        "hoverProvider",
        "diagnosticProvider",
        "documentSymbolProvider",
    ):
        present = capability in capabilities
        print(f"{capability:<24} {'advertised' if present else 'MISSING'}")
        ok &= present

    # A language client registers an editor command for every id the server
    # advertises. If the extension also contributes one of those ids, the second
    # registration throws and the whole session dies before a single hint renders
    # — which no amount of talking to the server on its own would reveal.
    advertised = set(
        (capabilities.get("executeCommandProvider") or {}).get("commands", [])
    )
    manifest = json.loads(
        (ROOT / "editors" / "vscode" / "package.json").read_text()
    )
    contributed = {
        entry["command"] for entry in manifest["contributes"].get("commands", [])
    }
    clash = advertised & contributed
    print(f"{'command ids':<24} {len(advertised)} server, {len(contributed)} palette"
          f"{'  CLASH: ' + ', '.join(sorted(clash)) if clash else ', disjoint'}")
    if clash:
        print(f"  these ids would be registered twice: {sorted(clash)}", file=sys.stderr)
        ok = False

    send(stdin, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
    send(stdin, {
        "jsonrpc": "2.0", "method": "textDocument/didOpen",
        "params": {"textDocument": {
            "uri": uri, "languageId": "chordpro", "version": 1,
            "text": FIXTURE.read_text(),
        }},
    })

    # Before warm-up: placeholders, never a confident zero.
    early = request(stdin, stdout, 2, "textDocument/inlayHint", whole_file) or []
    labels = {hint["label"] for hint in early}
    warming = labels <= {"…"}
    print(f"{'while warming':<24} {sorted(labels)} "
          f"{'(placeholders, no false counts)' if warming else ''}")
    if any("0σ" in label for label in labels):
        print("  a line reported 0 syllables before it was analysed", file=sys.stderr)
        ok = False

    # The server asks us to redraw once prosodic is loaded; that is our cue.
    print(f"{'waiting for warm-up':<24} ...", flush=True)
    while True:
        message = receive(stdout)
        if message is None:
            raise SystemExit("server closed while warming up")
        if "id" in message and "method" in message:
            send(stdin, {"jsonrpc": "2.0", "id": message["id"], "result": None})
            if message["method"].endswith("/refresh"):
                print(f"{'refresh requested':<24} {message['method']}")
                break

    tokens = request(stdin, stdout, 3, "textDocument/semanticTokens/full", document)
    data = tokens.get("data") if isinstance(tokens, dict) else None
    print(f"{'semantic tokens':<24} {len(data) // 5 if data else 0} syllables")
    ok &= bool(data)

    hints = request(stdin, stdout, 4, "textDocument/inlayHint", whole_file) or []
    print(f"{'inlay hints':<24} {len(hints)}")
    for hint in hints[:4]:
        print(f"    line {hint['position']['line']:>2}  {hint['label']}")
    ok &= bool(hints) and all(hint["label"] != "…" for hint in hints)

    # By default the margin carries the count and the rhyme and nothing else. The
    # stress marks live in the panels, where columns line up and comparing them
    # actually works.
    marked = [hint["label"] for hint in hints if "[" in hint["label"]]
    if marked:
        print(f"  stress marks in the margin by default: {marked[:2]}", file=sys.stderr)
        ok = False

    # Hover on "chariot", which the [D] splits in two.
    line5 = FIXTURE.read_text().splitlines()[5]
    column = line5.index("chari") + 2
    hover = request(stdin, stdout, 5, "textDocument/hover", {
        **document, "position": {"line": 5, "character": column},
    })
    body = (hover or {}).get("contents", {}).get("value", "")
    first = body.splitlines()[0] if body else "<nothing>"
    print(f"{'hover on chariot':<24} {first}")
    ok &= "cha" in body and "|" in body  # split word plus the IPA table

    symbols = request(stdin, stdout, 6, "textDocument/documentSymbol", document) or []
    print(f"{'document symbols':<24} " +
          ", ".join(f"{s['name']} ({s['detail']})" for s in symbols))
    ok &= len(symbols) >= 2

    # Diagnostics deserve a document that is actually broken.
    edges = ROOT / "tests" / "fixtures" / "edges.cho"
    send(stdin, {
        "jsonrpc": "2.0", "method": "textDocument/didOpen",
        "params": {"textDocument": {
            "uri": edges.as_uri(), "languageId": "chordpro", "version": 1,
            "text": edges.read_text(),
        }},
    })
    report = request(stdin, stdout, 7, "textDocument/diagnostic",
                     {"textDocument": {"uri": edges.as_uri()}})
    items = (report or {}).get("items", [])
    kinds = {item["message"].split(":")[0].split(".")[0] for item in items}
    print(f"{'diagnostics':<24} {len(items)} on edges.cho")
    for message in sorted(kinds)[:4]:
        print(f"    {message}")
    ok &= any("Unclosed" in item["message"] for item in items)

    long_song = ROOT / "tests" / "fixtures" / "long_song.cho"
    send(stdin, {
        "jsonrpc": "2.0", "method": "textDocument/didOpen",
        "params": {"textDocument": {
            "uri": long_song.as_uri(), "languageId": "chordpro", "version": 1,
            "text": long_song.read_text(),
        }},
    })
    # Driven off what the server advertises, so a renamed command cannot quietly
    # stop being exercised here.
    for id_, command in enumerate(sorted(advertised), start=8):
        panel = request(stdin, stdout, id_, "workspace/executeCommand",
                        {"command": command, "arguments": [long_song.as_uri()]})
        body = panel or ""
        # "+" can only be a stress mark: the panels are where those still belong.
        print(f"{command:<24} {len(body.splitlines())} lines, "
              f"{'with' if '+' in body else 'NO'} stress marks")
        ok &= "Melic —" in body and len(body.splitlines()) > 5 and "+" in body

    # Editors cancel requests they no longer need, and ours are answered long
    # before the cancel arrives. That race is normal and unactionable, so it must
    # not shout in the output channel.
    send(stdin, {"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": 4}})

    request(stdin, stdout, 8 + len(advertised), "shutdown", None)
    send(stdin, {"jsonrpc": "2.0", "method": "exit", "params": None})
    _, err = process.communicate(timeout=60)

    stderr = err.decode(errors="replace")
    for line in stderr.splitlines():
        if "Traceback" in line or "Exception" in line:
            print(f"  stderr: {line}", file=sys.stderr)
            ok = False

    noisy = "Cancel notification for unknown" in stderr
    print(f"{'late cancel':<24} {'NOISY' if noisy else 'quiet'}")
    ok &= not noisy

    print("\nOK" if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
