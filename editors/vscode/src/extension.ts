/**
 * A thin client. The prosody lives in the server; this file finds it, starts it,
 * and forwards settings.
 *
 * No language or grammar is contributed here — aleskabourek.vschordpro already
 * registers the `chordpro` language ID and its TextMate grammar, and two grammars
 * over one language fight. We layer semantic tokens on top of what it provides.
 */

import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

/** How to launch the server: a command, its arguments, and any environment it needs. */
type Server = { command: string; args: string[]; env?: NodeJS.ProcessEnv };

/**
 * The interpreter and dependencies packaged into the VSIX by
 * `scripts/bundle_server.sh`. Absent in a development checkout, which is what makes
 * the bundle safe to prefer over nothing: there, one of the candidates above it wins.
 *
 * `python3.12` is the real binary rather than the `python` symlink beside it, which
 * packaging may not preserve. The version tracks `python_version` in the build
 * script; `check_versions.sh` holds the two together.
 */
function bundledServer(context: vscode.ExtensionContext): Server | undefined {
  const root = path.join(context.extensionPath, "bundled");
  const interpreter =
    process.platform === "win32"
      ? path.join(root, "python", "python.exe")
      : path.join(root, "python", "bin", "python3.12");

  if (!fs.existsSync(interpreter)) {
    return undefined;
  }
  return {
    command: interpreter,
    args: ["-m", "melic_lsp.server"],
    // The dependencies sit beside the interpreter rather than inside it, so they
    // have to be pointed at rather than found.
    env: { ...process.env, PYTHONPATH: path.join(root, "libs") },
  };
}

/** Where to look for the server, in order of how deliberate the choice is. */
function resolveServer(context: vscode.ExtensionContext): Server {
  const configured = vscode.workspace
    .getConfiguration("melic")
    .get<string>("serverPath");
  if (configured) {
    return { command: configured, args: [] };
  }

  const binary = process.platform === "win32" ? "Scripts" : "bin";
  const candidates = [
    // A checkout being worked on wins over anything installed globally — but only
    // one we are allowed to run. A workspace .venv is workspace-controlled content,
    // so starting it is executing code that came with the folder; in an untrusted
    // workspace we skip it and let the bundle below answer instead.
    ...(vscode.workspace.isTrusted
      ? (vscode.workspace.workspaceFolders ?? []).map((folder) =>
          path.join(folder.uri.fsPath, ".venv", binary, "melic-lsp")
        )
      : []),
    // Where `uv tool install` and `pipx install` put it. Worth checking by path
    // as well as by name: a VS Code started from the Dock on macOS does not
    // necessarily inherit a login shell's PATH, and then a perfectly good
    // install looks like a missing one.
    path.join(os.homedir(), ".local", binary, "melic-lsp"),
  ];

  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (found) {
    return { command: found, args: [] };
  }

  // Last, so that anything the user installed deliberately outranks what we shipped.
  // Falling through to the bare name keeps development checkouts working, where no
  // bundle has been built and `melic-lsp` is expected on PATH.
  return bundledServer(context) ?? { command: "melic-lsp", args: [] };
}

export function activate(context: vscode.ExtensionContext): void {
  const server = resolveServer(context);
  const executable = {
    command: server.command,
    args: server.args,
    options: server.env ? { env: server.env } : undefined,
    transport: TransportKind.stdio,
  };
  const serverOptions: ServerOptions = { run: executable, debug: executable };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "chordpro" }],
    // Sent at initialize so the very first analysis already respects settings,
    // rather than being redrawn a moment later.
    initializationOptions: { melic: vscode.workspace.getConfiguration("melic") },
    synchronize: {
      configurationSection: "melic",
    },
    outputChannel: vscode.window.createOutputChannel("Melic"),
  };

  client = new LanguageClient("melic", "Melic", serverOptions, clientOptions);
  client.start().catch((error: unknown) => {
    vscode.window.showErrorMessage(
      `Melic: could not start ${server.command}. ${String(error)}`
    );
  });

  context.subscriptions.push(
    { dispose: () => void client?.stop() },
    vscode.workspace.registerTextDocumentContentProvider(PANEL_SCHEME, panels),
    registerPanel("melic.compareSections", "melic.server.compareSections", "Compare Sections"),
    registerPanel("melic.scansionPanel", "melic.server.scansionPanel", "Scansion")
  );
}

/**
 * Panel output is held in memory and served through a `melic:` URI, which VS Code
 * renders read-only for free. Re-running a command replaces the content of the
 * same URI, so the panel updates in place instead of stacking up tabs.
 */
const PANEL_SCHEME = "melic";
const contents = new Map<string, string>();
const changed = new vscode.EventEmitter<vscode.Uri>();

const panels: vscode.TextDocumentContentProvider = {
  onDidChange: changed.event,
  provideTextDocumentContent: (uri) => contents.get(uri.toString()) ?? "",
};

/**
 * Wires a palette command to a server command. The two ids must differ: the
 * language client already registers an editor command for every id the server
 * advertises, so reusing one here would collide and fail initialization.
 */
function registerPanel(
  paletteCommand: string,
  serverCommand: string,
  title: string
): vscode.Disposable {
  return vscode.commands.registerCommand(paletteCommand, async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "chordpro") {
      vscode.window.showInformationMessage("Melic: open a ChordPro file first.");
      return;
    }
    if (!client) {
      return;
    }

    const text = await client.sendRequest<string>("workspace/executeCommand", {
      command: serverCommand,
      arguments: [editor.document.uri.toString()],
    });

    const uri = vscode.Uri.parse(`${PANEL_SCHEME}:${title}`);
    contents.set(uri.toString(), text ?? "");
    changed.fire(uri);

    const panel = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(panel, {
      viewColumn: vscode.ViewColumn.Beside,
      preview: true,
      preserveFocus: true,
    });
  });
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
