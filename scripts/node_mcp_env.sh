#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "node-mcp-env: expected a command to launch" >&2
  exit 64
fi

node_bin=""
if [ -d "${HOME}/.nvm/versions/node" ]; then
  shopt -s nullglob
  candidates=("${HOME}"/.nvm/versions/node/*/bin)
  shopt -u nullglob
  while IFS= read -r candidate; do
    if [ -x "${candidate}/node" ]; then
      node_bin="${candidate}"
    fi
  done < <(printf '%s\n' "${candidates[@]}" | sort -V)
fi

if [ -z "${node_bin}" ]; then
  node_command="$(command -v node 2>/dev/null || true)"
  if [ -n "${node_command}" ] && [ -x "${node_command}" ]; then
    node_bin="$(dirname "${node_command}")"
  fi
fi

if [ -z "${node_bin}" ]; then
  echo "node-mcp-env: no executable Node.js runtime found in NVM or PATH" >&2
  exit 127
fi

export PATH="${node_bin}:${PATH:-/usr/bin:/bin}"
exec "$@"
