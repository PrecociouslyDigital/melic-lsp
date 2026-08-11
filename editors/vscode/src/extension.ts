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

/** Where to look for the server, in order of how deliberate the choice is. */
function resolveServer(): { command: string; args: string[] } {
  const configured = vscode.workspace
    .getConfiguration("melic")
    .get<string>("serverPath");
  if (configured) {
    return { command: configured, args: [] };
  }

  const binary = process.platform === "win32" ? "Scripts" : "bin";
  const candidates = [
    // A checkout being worked on wins over anything installed globally.
    ...(vscode.workspace.workspaceFolders ?? []).map((folder) =>
      path.join(folder.uri.fsPath, ".venv", binary, "melic-lsp")
    ),
    // Where `uv tool install` and `pipx install` put it. Worth checking by path
    // as well as by name: a VS Code started from the Dock on macOS does not
    // necessarily inherit a login shell's PATH, and then a perfectly good
    // install looks like a missing one.
    path.join(os.homedir(), ".local", binary, "melic-lsp"),
  ];

  const found = candidates.find((candidate) => fs.existsSync(candidate));
  return { command: found ?? "melic-lsp", args: [] };
}

export function activate(context: vscode.ExtensionContext): void {
  const server = resolveServer();
  const serverOptions: ServerOptions = {
    run: { command: server.command, args: server.args, transport: TransportKind.stdio },
    debug: { command: server.command, args: server.args, transport: TransportKind.stdio },
  };

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
    registerPanel("melic.compareSections", "Compare Sections"),
    registerPanel("melic.scansionPanel", "Scansion")
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

function registerPanel(command: string, title: string): vscode.Disposable {
  return vscode.commands.registerCommand(command, async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "chordpro") {
      vscode.window.showInformationMessage("Melic: open a ChordPro file first.");
      return;
    }
    if (!client) {
      return;
    }

    const text = await client.sendRequest<string>("workspace/executeCommand", {
      command,
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
