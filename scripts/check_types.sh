#!/usr/bin/env bash
# Type checking, both directions: the source must pass, and mixing up coordinate
# spaces must fail. The second half is the point — it proves the newtypes bite.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> src/ must type check clean"
uv run ty check src/

echo
echo "==> coordinate-space violations must be rejected"
if uv run ty check scripts/coordinate_space_violations.py >/dev/null 2>&1; then
    echo "FAIL: the type checker accepted a mixed-up coordinate space." >&2
    echo "The newtypes in types.py have stopped enforcing anything." >&2
    exit 1
fi

violations=$(uv run ty check scripts/coordinate_space_violations.py 2>&1 |
    grep -c 'invalid-argument-type' || true)
echo "rejected $violations wrong-space calls, as intended"
