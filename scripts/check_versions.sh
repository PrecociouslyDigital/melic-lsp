#!/usr/bin/env bash
# The server and the extension are versioned separately by two package managers
# and have to agree. Optionally checks them against a release tag as well:
#
#     ./scripts/check_versions.sh            # server == extension
#     ./scripts/check_versions.sh v0.2.0     # ...and both == the tag
set -euo pipefail
cd "$(dirname "$0")/.."

server=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
extension=$(grep -m1 '"version"' editors/vscode/package.json | cut -d'"' -f4)

echo "pyproject.toml            $server"
echo "editors/vscode/package.json  $extension"

if [[ "$server" != "$extension" ]]; then
    echo "MISMATCH: server $server != extension $extension" >&2
    exit 1
fi

if [[ $# -gt 0 ]]; then
    tag="${1#v}"
    echo "tag                       $tag"
    if [[ "$server" != "$tag" ]]; then
        echo "MISMATCH: tag $tag != declared version $server" >&2
        exit 1
    fi
fi

echo "versions agree"
