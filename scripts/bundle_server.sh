#!/usr/bin/env bash
# Builds the self-contained server that ships inside the VSIX: a Python interpreter
# and the server's dependencies, so installing the extension installs everything and
# the user's own Python is never consulted.
#
#     ./scripts/bundle_server.sh bundled              # this machine
#     ./scripts/bundle_server.sh bundled linux-x64    # any target, from anywhere
#
# Output is <dir>/python (a python-build-standalone interpreter) and <dir>/libs (the
# dependencies), which the extension launches as
#
#     <dir>/python/bin/python3.12 -m melic_lsp.server     PYTHONPATH=<dir>/libs
#
# Compiled wheels make a bundle specific to one platform and one Python minor
# version, so there is one build per VSIX target and both are pinned here.
#
# A plain install is 442 MB, almost none of it ours. Some is load-bearing: prosodic's
# metrical parser (`prosodic/parsing/maxent.py`) is numpy linear algebra, so numpy and
# pandas genuinely ship. Most is not — prosodic declares a plotting and notebook stack
# that nothing melic calls ever reaches. Pruning those leaves ~115-180 MB of
# dependencies depending on platform, plus ~50 MB of interpreter.
#
# The prune list is written against what prosodic *declares*, not what it imports, so
# upstream can invalidate it silently by starting to use scipy on a path we hit. The
# `bundle` CI job re-runs the whole suite and the LSP smoke test against the pruned
# tree, which is that risk made into a failing build.
set -euo pipefail
cd "$(dirname "$0")/.."

target_dir="${1:?usage: bundle_server.sh <output-dir> [vscode-target]}"
vscode_target="${2:-}"

# Not a preference. `editdistance`, which prosodic reaches through panphon's distance
# code, publishes no wheel past cp312 on any platform — 3.13 and 3.14 would have to be
# compiled from source on each target. Nothing outside this bundle runs on it, so the
# version is invisible to users; 3.12 has security support until October 2028.
python_version=3.12

# Default to this machine, so building one to look at needs no argument.
if [[ -z "$vscode_target" ]]; then
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64)   vscode_target=darwin-arm64 ;;
        Darwin-x86_64)  vscode_target=darwin-x64 ;;
        Linux-x86_64)   vscode_target=linux-x64 ;;
        Linux-aarch64)  vscode_target=linux-arm64 ;;
        *) echo "cannot guess a target for $(uname -s)-$(uname -m); pass one" >&2; exit 1 ;;
    esac
fi

# VS Code's target names are the vocabulary the rest of packaging uses, so they are the
# vocabulary here; uv's two different spellings stay an implementation detail.
case "$vscode_target" in
    darwin-arm64) wheels=aarch64-apple-darwin      ; py_os=macos   ; py_arch=aarch64 ; py_libc=none ;;
    darwin-x64)   wheels=x86_64-apple-darwin       ; py_os=macos   ; py_arch=x86_64  ; py_libc=none ;;
    linux-x64)    wheels=x86_64-unknown-linux-gnu  ; py_os=linux   ; py_arch=x86_64  ; py_libc=gnu  ;;
    linux-arm64)  wheels=aarch64-unknown-linux-gnu ; py_os=linux   ; py_arch=aarch64 ; py_libc=gnu  ;;
    win32-x64)    wheels=x86_64-pc-windows-msvc    ; py_os=windows ; py_arch=x86_64  ; py_libc=none ;;
    *) echo "unknown target $vscode_target" >&2; exit 1 ;;
esac

# Each entry was removed and the suite re-run; see the `bundle` job in CI.
prune=(
    # Declared by prosodic, but only reached when writing parquet in its batch and
    # client paths. Melic parses a line at a time and never goes near them.
    pyarrow
    # Dragged in eagerly by `nltk.metrics.association` at import time rather than by
    # anything asking for statistics. The scansion kernels are numpy.
    scipy
    # Plotting and notebook extras, never imported at all under melic.
    matplotlib statsmodels plotnine mizani patsy
    pillow PIL fonttools fontTools
    ipython IPython jedi pygments prompt_toolkit
)

# Refuse to clear a directory that is not ours to clear: a previous bundle has a
# libs/melic_lsp in it, anything else is someone's mistaken argument.
if [[ -e "$target_dir" ]]; then
    if [[ -d "$target_dir/libs/melic_lsp" ]]; then
        rm -rf "${target_dir:?}"
    elif [[ -n "$(ls -A "$target_dir" 2>/dev/null)" ]]; then
        echo "refusing to overwrite $target_dir: not a previous bundle" >&2
        exit 1
    fi
fi
mkdir -p "$target_dir"

echo "==> fetching the $vscode_target interpreter"
# uv already tracks which python-build-standalone build belongs to each platform, so
# ask it rather than keeping a table of release tags in sync by hand.
url=$(uv python list --all-platforms --all-arches --only-downloads --output-format json |
    python3 -c "
import json, sys
want = ('$py_os', '$py_arch', '$py_libc')
builds = [
    row for row in json.load(sys.stdin)
    if row['url']
    and row['implementation'] == 'cpython'
    and row['variant'] == 'default'
    and row['version_parts']['minor'] == ${python_version#3.}
    and (row['os'], row['arch'], row['libc']) == want
]
if not builds:
    sys.exit('no python $python_version build for $vscode_target')
# Newest patch release, so a bundle picks up security fixes without being told.
print(max(builds, key=lambda row: row['version_parts']['patch'])['url'])
")
# install_only tarballs unpack to a single python/ directory, on every platform.
curl --fail --silent --show-error --location "$url" | tar -xz -C "$target_dir"

echo "==> installing the server and its dependencies"
uv pip install --quiet --python "$python_version" --python-platform "$wheels" \
    --target "$target_dir/libs" .

echo "==> pruning what melic never reaches"
shopt -s nullglob
for pkg in "${prune[@]}"; do
    rm -rf "$target_dir/libs/$pkg" "$target_dir/libs/$pkg".libs "$target_dir/libs/$pkg"-*.dist-info
done

size_mb=$(du -sm "$target_dir" | cut -f1)
echo
echo "bundle at $target_dir: ${size_mb} MB  ($vscode_target, python $python_version)"

# Not a target, just a tripwire for the prune quietly ceasing to apply — the
# dependencies alone are 442 MB unpruned. Real bundles sit well under this and differ
# by platform: manylinux numpy carries its own OpenBLAS, so Linux is the big one.
ceiling_mb=350
if (( size_mb > ceiling_mb )); then
    echo "FAIL: ${size_mb} MB exceeds the ${ceiling_mb} MB ceiling." >&2
    echo "Something the prune list used to remove is back. Compare against:" >&2
    printf '  %s\n' "${prune[@]}" >&2
    exit 1
fi
