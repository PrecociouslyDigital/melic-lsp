---
paths:
  - "editors/vscode/**"
---

# The VS Code client — thin on purpose

All the prosody lives in the server. This finds it, starts it, forwards settings, and
renders two panels. Resist adding logic here; it is the half without tests.

## Contribute no language and no grammar

`aleskabourek.vschordpro` already registers the `chordpro` language id and its TextMate
grammar, and two grammars over one language fight. We layer `semanticTokenTypes` /
`semanticTokenScopes` on top, plus `configurationDefaults` so stressed syllables are
visible without the user editing a theme.

## Build

Bundled with **esbuild** into a single `out/extension.js`; `node_modules` is not shipped.

```
npm run check-types   # tsc --noEmit — esbuild does NOT type check
npm run compile       # esbuild bundle
npm run watch
```

`--external:vscode` is mandatory: the editor supplies that module. The safety property to
preserve is that **the bundle's only non-builtin require is `vscode`** — everything else
it needs is a Node builtin. Verify with:

```bash
node -e "const s=require('fs').readFileSync('./out/extension.js','utf8');
const b=new Set(require('module').builtinModules);
console.log([...new Set([...s.matchAll(/require\(\"([^\"]+)\"\)/g)].map(m=>m[1]))]
  .filter(n=>!b.has(n)&&!n.startsWith('node:')))"
```

If bundling `vscode-languageclient` ever misbehaves, the fallback is to ship
`node_modules` again and accept vsce's warning. Don't chase it further than that.

## Installing a change needs BOTH halves

The server is installed as a **snapshot**, so this catches people out:

```bash
uv tool install . --force                              # the server
cd editors/vscode && npx @vscode/vsce package \
  && code --install-extension melic-lsp-0.1.0.vsix --force
```

then reload the VS Code window. Inside this workspace the extension prefers `.venv`, so
server edits are picked up on restart; anywhere else it uses the global copy.

`resolveServer()` checks, in order: the `melic.serverPath` setting, a workspace `.venv`,
then `~/.local/bin` **by path** — a VS Code started from the Dock on macOS does not
necessarily inherit a login shell's `PATH`, and then a working install looks like a
missing one.

## Panels

Output is served through a `melic:` URI via a `TextDocumentContentProvider`, which VS
Code renders read-only for free. Re-running a command replaces the content at the same
URI so the panel updates in place instead of stacking tabs.
