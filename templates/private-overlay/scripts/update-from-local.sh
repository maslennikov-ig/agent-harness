#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HARNESS_BIN="${HARNESS_BIN:-$HOME/.agent-harness-src/bin/harness}"

if [[ ! -x "$HARNESS_BIN" ]]; then
  echo "harness binary not found: $HARNESS_BIN" >&2
  echo "Set HARNESS_BIN=/path/to/harness or install agent-harness first." >&2
  exit 1
fi

"$HARNESS_BIN" export-local --scope private --target "$ROOT" --yes
git -C "$ROOT" status --short
