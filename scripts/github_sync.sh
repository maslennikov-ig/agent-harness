#!/usr/bin/env bash
# Stable wrapper for the versioned Beads<->GitHub reconciliation coordinator.
#
# Current entry points:
#   github_sync.sh --trigger [--bead ID] [repo ...]  # durable, fast enqueue
#   github_sync.sh --reconcile [--dry-run] [repo ...]
#   github_sync.sh --install-hooks [--dry-run] [repo ...]
#   github_sync.sh --inventory [repo ...]
#
# Retired --pull-only/--push-only hook bodies are compatibility triggers. They
# are a visible no-op until the repository has been explicitly enrolled by a
# successful --install-hooks run; they never call `bd github`.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/github_sync.py"
MODE="reconcile"
ARGS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --trigger)
      MODE="trigger"
      ;;
    --reconcile)
      MODE="reconcile"
      ;;
    --install-hooks)
      MODE="install-hooks"
      ;;
    --inventory)
      MODE="inventory"
      ;;
    --pull-only|--push-only)
      MODE="legacy"
      ;;
    --bead)
      if [ "$#" -lt 2 ]; then
        echo "github_sync: --bead needs an ID" >&2
        exit 2
      fi
      ARGS+=("--bead" "$2")
      shift
      ;;
    --dry-run|--no-start|--queued-only|--apply-alias-redirects)
      ARGS+=("$1")
      ;;
    -h|--help)
      sed -n '2,13p' "$0"
      exit 0
      ;;
    --*)
      echo "github_sync: unknown option $1" >&2
      exit 2
      ;;
    *)
      ARGS+=("$1")
      ;;
  esac
  shift
done

exec python3 "${PYTHON_SCRIPT}" "${MODE}" "${ARGS[@]}"
