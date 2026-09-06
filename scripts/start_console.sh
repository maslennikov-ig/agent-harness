#!/usr/bin/env bash
set -euo pipefail

resolve_script_path() {
  local source="${BASH_SOURCE[0]}"
  while [ -L "${source}" ]; do
    local dir
    dir="$(cd -P "$(dirname "${source}")" && pwd)"
    local target
    target="$(readlink "${source}")"
    case "${target}" in
      /*) source="${target}" ;;
      *) source="${dir}/${target}" ;;
    esac
  done
  cd -P "$(dirname "${source}")" && pwd
}

detect_codex_home() {
  local settings_path="${ORCH_PANEL_SETTINGS_PATH:-${CONSOLE_DIR:-}/state/panel-settings.json}"
  local stored_home=""
  if [ -f "${settings_path}" ]; then
    stored_home="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8")); print(value.get("codex_home", "") if value.get("schema_version") == "orchestration-console-settings/v1" else "")' "${settings_path}" 2>/dev/null || true)"
    if [ -n "${stored_home}" ] && [ -d "${stored_home}" ]; then
      printf '%s\n' "${stored_home}"
      return
    fi
  fi
  if [ -n "${CODEX_HOME:-}" ]; then
    printf '%s\n' "${CODEX_HOME}"
    return
  fi
  if [ -f "${CONSOLE_DIR}/release-manifest.json" ]; then
    printf '%s\n' "${HOME}/.codex"
    return
  fi
  local best=""
  local best_score=-1
  consider_codex_home() {
    local candidate="$1"
    local score
    [ -d "${candidate}" ] || return 0
    score="$(codex_home_score "${candidate}")"
    if [ "${score}" -gt "${best_score}" ]; then
      best="${candidate}"
      best_score="${score}"
    fi
  }
  consider_codex_home "${HOME}/.codex"
  local users_root="${CODEX_WINDOWS_USERS_ROOT:-/mnt/c/Users}"
  if [ -d "${users_root}" ]; then
    while IFS= read -r -d '' found; do
      consider_codex_home "${found}"
    done < <(find "${users_root}" -maxdepth 2 -type d -name .codex -print0 2>/dev/null)
  fi
  if [ -n "${best}" ]; then
    printf '%s\n' "${best}"
  else
    printf '%s\n' "${HOME}/.codex"
  fi
}

codex_home_score() {
  local candidate="$1"
  local score=1
  [ -f "${candidate}/config.toml" ] && score=$((score + 1))
  [ -f "${candidate}/AGENTS.md" ] && score=$((score + 5))
  if [ -d "${candidate}/agents" ]; then
    local agents
    agents="$(find -L "${candidate}/agents" -maxdepth 1 -type f -name '*.toml' 2>/dev/null | wc -l)"
    agents=$((agents * 2))
    [ "${agents}" -gt 50 ] && agents=50
    score=$((score + agents))
  fi
  if [ -d "${candidate}/skills" ]; then
    local skills
    skills="$(find -L "${candidate}/skills" -mindepth 2 -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l)"
    [ "${skills}" -gt 50 ] && skills=50
    score=$((score + skills))
  fi
  if [ -d "${candidate}/superpowers/skills" ]; then
    local superpowers
    superpowers="$(find -L "${candidate}/superpowers/skills" -mindepth 2 -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l)"
    [ "${superpowers}" -gt 50 ] && superpowers=50
    score=$((score + superpowers))
  fi
  [ -f "${candidate}/catalog/assets.json" ] && score=$((score + 5))
  printf '%s\n' "${score}"
}

SCRIPT_DIR="$(resolve_script_path)"
CONSOLE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CODEX_HOME="$(detect_codex_home)"
export CODEX_HOME
# The session home stays isolated; the catalog, the installed skills and agents,
# and the sync runner live in the asset home, which is usually a different
# directory. The panel owns that split, so ask it rather than score again here.
detect_codex_asset_home() {
  if [ -f "${CONSOLE_DIR}/release-manifest.json" ]; then
    printf '%s\n' "${CODEX_ASSET_HOME:-${CODEX_HOME}}"
    return
  fi
  local resolved=""
  resolved="$(python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" homes 2>/dev/null \
    | sed -n 's/^codex_asset_home=//p')"
  if [ -n "${resolved}" ] && [ -d "${resolved}" ]; then
    printf '%s\n' "${resolved}"
    return
  fi
  printf '%s\n' "${CODEX_HOME}"
}
CODEX_ASSET_HOME="$(detect_codex_asset_home)"
CLAUDE_HOME="${CLAUDE_HOME:-${CLAUDE_CONFIG_DIR:-${HOME}/.claude}}"
AGENTS_HOME="${AGENTS_HOME:-${HOME}/.agents}"
INITIAL_CODEX_WORKSPACE="${CODEX_WORKSPACE:-}"
WORKSPACE="${INITIAL_CODEX_WORKSPACE:-${HOME}/code}"
if [ ! -d "${WORKSPACE}" ]; then
  WORKSPACE="${PWD}"
fi
PROJECT_WORKSPACE="${INITIAL_CODEX_WORKSPACE:-${PWD}}"
NOTES="${CONSOLE_DIR}/AGENT_NOTES.md"
if [ -f "${CONSOLE_DIR}/release-manifest.json" ]; then
  NOTES="${CONSOLE_DIR}/state/AGENT_NOTES.md"
fi
PANEL_HOST="${ORCH_PROMPTS_HOST:-${CODEX_PROMPTS_HOST:-127.0.0.1}}"
PANEL_PORT="${ORCH_PROMPTS_PORT:-${CODEX_PROMPTS_PORT:-8765}}"
PANEL_URL="http://${PANEL_HOST}:${PANEL_PORT}/"
PANEL_LOG="${CONSOLE_DIR}/state/server.log"
PANEL_PID="${CONSOLE_DIR}/state/server.pid"
FRONTEND_DIST_DIR="${ORCH_FRONTEND_DIST_DIR:-${CONSOLE_DIR}/web/dist}"
FRONTEND_NODE_MODULES_DIR="${ORCH_FRONTEND_NODE_MODULES_DIR:-${CONSOLE_DIR}/node_modules}"
FRONTEND_BUILD_STAMP="${FRONTEND_DIST_DIR}/index.html"

# The ASGI panel host needs the locked starlette/uvicorn/a2a-sdk environment.
# Everything else in this launcher stays on plain python3.
detect_panel_python() {
  if [ -n "${ORCH_PANEL_PYTHON:-}" ]; then
    printf '%s\n' "${ORCH_PANEL_PYTHON}"
  elif [ -x "${CONSOLE_DIR}/.venv/bin/python" ]; then
    printf '%s\n' "${CONSOLE_DIR}/.venv/bin/python"
  else
    printf '%s\n' "python3"
  fi
}

PANEL_PYTHON="$(detect_panel_python)"

# Only the panel host needs the locked environment, so this is checked where the
# panel actually starts rather than for every subcommand.
require_panel_python() {
  if [ -n "${ORCH_PANEL_PYTHON:-}" ] || [ -x "${CONSOLE_DIR}/.venv/bin/python" ]; then
    return 0
  fi
  cat >&2 <<EOF
The panel runtime is missing: ${CONSOLE_DIR}/.venv was not found.
Provision it with the supported restore path:
  uv sync --frozen --project "${CONSOLE_DIR}"
Or point ORCH_PANEL_PYTHON at an interpreter that has starlette, uvicorn, and a2a-sdk.
EOF
  return 1
}

frontend_dependencies_need_install() {
  local lock_marker="${FRONTEND_NODE_MODULES_DIR}/.package-lock.json"
  [ -d "${FRONTEND_NODE_MODULES_DIR}" ] || return 0
  [ -f "${lock_marker}" ] || return 0
  [ "${CONSOLE_DIR}/package-lock.json" -nt "${lock_marker}" ]
}

frontend_sources_are_newer() {
  [ -f "${FRONTEND_BUILD_STAMP}" ] || return 0
  local source
  for source in \
    "${CONSOLE_DIR}/package.json" \
    "${CONSOLE_DIR}/package-lock.json" \
    "${CONSOLE_DIR}/vite.config.ts" \
    "${CONSOLE_DIR}/tsconfig.json" \
    "${CONSOLE_DIR}/tsconfig.node.json" \
    "${CONSOLE_DIR}/postcss.config.js" \
    "${CONSOLE_DIR}/tailwind.config.js" \
    "${CONSOLE_DIR}/components.json" \
    "${CONSOLE_DIR}/web/index.html"; do
    [ "${source}" -nt "${FRONTEND_BUILD_STAMP}" ] && return 0
  done
  find "${CONSOLE_DIR}/web/src" "${CONSOLE_DIR}/web/public" \
    -type f -newer "${FRONTEND_BUILD_STAMP}" -print -quit 2>/dev/null \
    | grep -q .
}

ensure_frontend_build() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required to build the Orchestration Console frontend." >&2
    return 1
  fi
  if frontend_dependencies_need_install; then
    npm --prefix "${CONSOLE_DIR}" ci || return 1
  fi
  if frontend_sources_are_newer; then
    npm --prefix "${CONSOLE_DIR}" run build || return 1
  fi
  if [ ! -f "${FRONTEND_BUILD_STAMP}" ]; then
    echo "Frontend build did not produce ${FRONTEND_BUILD_STAMP}." >&2
    return 1
  fi
}

# Epic Workspace coordination writes are on by default: the rollout that kept
# them behind this flag is accepted, and a read-only workspace cannot register
# a project or an epic at all. Set ORCH_COORDINATION=0 to get the read-only
# panel back. Exporting the resolved value keeps `serve` and the background
# `start` path identical instead of depending on the caller's shell.
ORCH_COORDINATION="${ORCH_COORDINATION:-1}"

export CODEX_HOME CODEX_ASSET_HOME CLAUDE_HOME AGENTS_HOME ORCH_COORDINATION
export CODEX_WORKSPACE="${WORKSPACE}"

mkdir -p "${CONSOLE_DIR}"

if [ ! -f "${NOTES}" ]; then
  mkdir -p "$(dirname "${NOTES}")"
  cat > "${NOTES}" <<'EOF'
# Orchestration Console Notes

Created by reconstructed codex-prompts launcher.
EOF
fi

catalog_summary() {
  python3 - <<'PY'
import json
from pathlib import Path

import os

path = Path(os.environ.get("CODEX_ASSET_HOME") or os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")) / "catalog/assets.json"
if not path.exists():
    print("Catalog not found:", path)
    raise SystemExit(1)

data = json.loads(path.read_text())
staged = data.get("staged_sources") or {}
if isinstance(staged, dict):
    sources = [(key, value) for key, value in staged.items()]
else:
    sources = [(None, value) for value in staged]

print("generated_at:", data.get("generated_at"))
print("installed_skills:", len(data.get("installed_skills") or []))
print("custom_agents:", len(data.get("custom_agents") or []))
print("staged_sources:", len(sources))
print("staged_skills:", sum(len(s.get("skills", [])) for _, s in sources if isinstance(s, dict)))
print("staged_agents:", sum(len(s.get("agents", [])) for _, s in sources if isinstance(s, dict)))
print()
for source_id, source in sources:
    if not isinstance(source, dict):
        continue
    print(
        f"- {source.get('id') or source.get('name') or source_id or 'source'}: "
        f"skills={len(source.get('skills', []))} "
        f"agents={len(source.get('agents', []))}"
    )
PY
}

list_skills() {
  local dirs=()
  for dir in "${CODEX_HOME}/skills" "${CODEX_ASSET_HOME}/skills" "${AGENTS_HOME}/skills" \
             "${CODEX_HOME}/superpowers/skills" "${CODEX_ASSET_HOME}/superpowers/skills"; do
    [ -d "${dir}" ] && dirs+=("${dir}")
  done
  [ "${#dirs[@]}" -gt 0 ] || return 0
  find "${dirs[@]}" -mindepth 2 -maxdepth 2 -name SKILL.md 2>/dev/null \
    | while IFS= read -r path; do basename "$(dirname "${path}")"; done \
    | sort -u
}

list_agents() {
  local dirs=()
  for dir in "${CODEX_HOME}/agents" "${CODEX_ASSET_HOME}/agents" "${AGENTS_HOME}/agents"; do
    [ -d "${dir}" ] && dirs+=("${dir}")
  done
  [ "${#dirs[@]}" -gt 0 ] || return 0
  find "${dirs[@]}" -maxdepth 1 -type f -name '*.toml' 2>/dev/null \
    | while IFS= read -r path; do basename "${path%.toml}"; done \
    | sort -u
}

open_notes() {
  if [ -n "${EDITOR:-}" ] && command -v "${EDITOR}" >/dev/null 2>&1; then
    "${EDITOR}" "${NOTES}"
  elif command -v nano >/dev/null 2>&1; then
    nano "${NOTES}"
  elif command -v vim >/dev/null 2>&1; then
    vim "${NOTES}"
  else
    sed -n '1,220p' "${NOTES}"
  fi
}

run_sync() {
  local candidates=(
    "${CODEX_ASSET_HOME}/skills/codex-catalog-sync/scripts/run_catalog_sync.py"
    "${CODEX_ASSET_HOME}/bin/sync_catalog.py"
  )
  local runner
  for runner in "${candidates[@]}"; do
    if [ -f "${runner}" ]; then
      python3 "${runner}"
      return
    fi
  done
  # Naming both homes is the point: the runner is missing from the asset home,
  # and the isolated session home is not where it was ever going to be.
  echo "codex-catalog-sync runner not found in the asset home." >&2
  echo "  CODEX_ASSET_HOME: ${CODEX_ASSET_HOME}" >&2
  echo "  CODEX_HOME:       ${CODEX_HOME} (isolated session home; not searched)" >&2
  for runner in "${candidates[@]}"; do
    echo "  looked for: ${runner}" >&2
  done
  echo "Set CODEX_ASSET_HOME, or store codex_asset_home in the panel settings." >&2
  return 1
}

show_header() {
  clear 2>/dev/null || true
  echo "Orchestration Prompt Console"
  echo "CODEX_HOME:  ${CODEX_HOME}"
  echo "CODEX_ASSETS:${CODEX_ASSET_HOME}"
  echo "CLAUDE_HOME: ${CLAUDE_HOME}"
  echo "WORKSPACE:   ${WORKSPACE}"
  echo "NOTES:       ${NOTES}"
  echo
  catalog_summary || true
  echo
}

show_help() {
  cat <<EOF
Commands:
  open     start server if needed and open ${PANEL_URL}
  serve    run web dashboard server in the foreground
  status   check web dashboard health
  menu     show this legacy terminal menu
  notes    open or print AGENT_NOTES.md
  catalog  show catalog summary
  skills   list installed skills
  agents   list custom agents
  sync     run codex-catalog-sync direct runner
  docs-context  show compact Docs L1/L2 status; add --json for full state
  docs-context-plan  show dry-run L1 install plan
  docs-context-sync  dry-run L1 install plan; add --write to execute
  docs-diagnose  inspect the shared Codex/Claude docs route without exposing secrets
  docs-resolve  resolve one dependency docs query through L1, auto-download, then fallback status
  docs-persist  store an L2 answer back into L1 so later tasks and resumes hit local docs
  docs-signature  read a symbol declaration from the installed package; version-correct, no network
  prompt-get  print one exact raw prompt card by ID; no server or automatic selection
  prompt-check  lint a generated agent prompt from stdin or --file
  prompts-sync  check prompt fragment drift; add --write to re-expand from canon
  context-audit  audit harness context size and behavioral evidence; add --json
  coordination-archive  archive local coordination state; requires --confirm archive-local-coordination
  benchmark  measure prompt, panel, repository scan, tails, and throughput latency; add --quick or --json
  claude-aitmpl  show Claude-only aitmpl agent candidates and dry-run commands
  claude-agents  show local Claude Markdown subagent library and install commands
  claude-agent-install  copy one local Claude agent into .claude/agents or ~/.claude/agents
  install-claude-plugin  sync orchestration-bridge into ~/.claude/skills
  shell    open a shell in ${WORKSPACE}
  help     show this help
  quit     exit
EOF
}

panel_expected_build_id() {
  sha256sum "${CONSOLE_DIR}/scripts/orchestration_panel.py" | awk '{print substr($1, 1, 12)}'
}

panel_health_payload() {
  curl -fsS --max-time 1 "${PANEL_URL}api/health" 2>/dev/null
}

panel_online() {
  panel_health_payload >/dev/null
}

panel_health() {
  local payload expected
  payload="$(panel_health_payload)" || return 1
  expected="$(panel_expected_build_id)" || return 1
  python3 -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(0 if data.get("online") and data.get("build_id") == sys.argv[1] else 1)' "${expected}" <<<"${payload}"
}

panel_pid_is_owned() {
  local pid="$1"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  [ -r "/proc/${pid}/cmdline" ] || return 1
  tr '\0' '\n' <"/proc/${pid}/cmdline" | grep -Fxq -- "${CONSOLE_DIR}/scripts/orchestration_panel.py" || return 1
  tr '\0' '\n' <"/proc/${pid}/cmdline" | grep -Fxq -- "${PANEL_PORT}" || return 1
}

stop_owned_stale_panel() {
  local pid
  pid="$(sed -n '1p' "${PANEL_PID}" 2>/dev/null || true)"
  if ! panel_pid_is_owned "${pid}"; then
    echo "Dashboard is stale, but its process ownership is not proven; refusing to stop it." >&2
    return 1
  fi
  kill "${pid}"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "${pid}" 2>/dev/null || return 0
    sleep 0.1
  done
  echo "Stale dashboard did not stop after SIGTERM (pid ${pid})." >&2
  return 1
}

serve_panel() {
  require_panel_python || return 1
  ensure_frontend_build || return 1
  mkdir -p "${CONSOLE_DIR}/state"
  echo "$$" > "${PANEL_PID}"
  exec "${PANEL_PYTHON}" "${CONSOLE_DIR}/scripts/orchestration_panel.py" --host "${PANEL_HOST}" --port "${PANEL_PORT}"
}

ensure_panel() {
  mkdir -p "${CONSOLE_DIR}/state"
  ensure_frontend_build || return 1
  if panel_health; then
    return 0
  fi
  require_panel_python || return 1
  if panel_online; then
    stop_owned_stale_panel || return 1
  fi
  nohup "${PANEL_PYTHON}" "${CONSOLE_DIR}/scripts/orchestration_panel.py" --host "${PANEL_HOST}" --port "${PANEL_PORT}" >"${PANEL_LOG}" 2>&1 &
  echo "$!" > "${PANEL_PID}"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if panel_health; then
      return 0
    fi
    sleep 0.2
  done
  echo "Dashboard did not become healthy. Log: ${PANEL_LOG}" >&2
  return 1
}

open_panel() {
  ensure_panel
  if command -v powershell.exe >/dev/null 2>&1; then
    # The URL is inlined rather than passed as a trailing argument: `-Command`
    # does not bind positional arguments to a `param()` block, it appends them
    # to the command text, so the parameter stayed null and Start-Process failed
    # its FilePath validation. The `||` fallback then printed the URL, which
    # reads like success while no browser ever opened.
    powershell.exe -NoProfile -Command "Start-Process -FilePath '${PANEL_URL}'" >/dev/null 2>&1 || echo "${PANEL_URL}"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${PANEL_URL}" >/dev/null 2>&1 || true
  else
    echo "${PANEL_URL}"
  fi
}

coordination_mode() {
  case "${ORCH_COORDINATION}" in
    1 | on | true | yes) echo "read-write" ;;
    *) echo "read-only (set ORCH_COORDINATION=1 to enable writes)" ;;
  esac
}

panel_status() {
  echo "Coordination: $(coordination_mode)"
  if panel_health; then
    echo "Dashboard healthy: ${PANEL_URL}"
  elif panel_online; then
    echo "Dashboard is stale: ${PANEL_URL} (run 'orch-prompts open' to replace the owned server)"
    return 1
  else
    echo "Dashboard is not running: ${PANEL_URL}"
    [ -f "${PANEL_LOG}" ] && tail -n 20 "${PANEL_LOG}"
    return 1
  fi
}

docs_context_status() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" docs-context
}

docs_context_plan() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" docs-context-plan "$@"
}

docs_context_sync() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" docs-context-sync "$@"
}

docs_diagnose() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" docs-diagnose "$@"
}

docs_resolve() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" docs-resolve "$@"
}

docs_persist() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" docs-persist "$@"
}

claude_aitmpl() {
  CODEX_WORKSPACE="${PROJECT_WORKSPACE}" python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" claude-aitmpl "$@"
}

claude_agents() {
  CODEX_WORKSPACE="${PROJECT_WORKSPACE}" python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" claude-agents "$@"
}

claude_agent_install() {
  CODEX_WORKSPACE="${PROJECT_WORKSPACE}" python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" claude-agent-install "$@"
}

prompt_check() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" prompt-check "$@"
}

prompt_get() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" prompt-get "$@"
}

prompts_sync() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" prompts-sync "$@"
}

context_audit() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" context-audit "$@"
}

benchmark() {
  python3 "${CONSOLE_DIR}/scripts/orchestration_panel.py" benchmark "$@"
}

coordination_archive() {
  "${PANEL_PYTHON}" "${CONSOLE_DIR}/scripts/orchestration_panel.py" coordination-archive "$@"
}

install_claude_plugin() {
  if [ -f "${CONSOLE_DIR}/release-manifest.json" ]; then
    echo "This public release uses 'harness bootstrap' and 'harness claude'; no marketplace registration is required." >&2
    return 2
  fi
  "${CONSOLE_DIR}/scripts/install_claude_plugin.sh"
}

interactive_menu() {
  show_header
  show_help
  echo
  while true; do
    read -r -p "orch-prompts> " cmd || break
    case "${cmd:-}" in
      ""|"help") show_help ;;
      "open") open_panel ;;
      "serve") serve_panel ;;
      "status") panel_status ;;
      "notes") open_notes ;;
      "catalog") catalog_summary ;;
      "docs-context") docs_context_status ;;
      "docs-context-plan") docs_context_plan ;;
      "docs-context-sync") docs_context_sync ;;
      "docs-diagnose") docs_diagnose ;;
      "docs-resolve") docs_resolve ;;
      "docs-persist") docs_persist ;;
      "prompt-get") prompt_get ;;
      "prompt-check") prompt_check ;;
      "prompts-sync") prompts_sync ;;
      "context-audit") context_audit ;;
      "benchmark") benchmark ;;
      "coordination-archive") echo "Use: orch-prompts coordination-archive --confirm archive-local-coordination" ;;
      "claude-aitmpl") claude_aitmpl ;;
      "claude-agents") claude_agents ;;
      "claude-agent-install") claude_agent_install ;;
      "install-claude-plugin") install_claude_plugin ;;
      "skills") list_skills ;;
      "agents") list_agents ;;
      "sync") run_sync ;;
      "shell") cd "${WORKSPACE}" && exec bash ;;
      "quit"|"exit") break ;;
      *) echo "Unknown command: ${cmd}. Type: help" ;;
    esac
    echo
  done
}

case "${1:-}" in
  "") open_panel ;;
  "open") open_panel ;;
  "serve") serve_panel ;;
  "status") panel_status ;;
  "menu") interactive_menu ;;
  "notes") open_notes ;;
  "catalog") catalog_summary ;;
  "docs-context") docs_context_status ;;
  "docs-context-plan") shift; docs_context_plan "$@" ;;
  "docs-context-sync") shift; docs_context_sync "$@" ;;
  "docs-diagnose") shift; docs_diagnose "$@" ;;
  "docs-resolve") shift; docs_resolve "$@" ;;
  "docs-persist") shift; docs_persist "$@" ;;
  "prompt-get") shift; prompt_get "$@" ;;
  "prompt-check") shift; prompt_check "$@" ;;
  "prompts-sync") shift; prompts_sync "$@" ;;
  "context-audit") shift; context_audit "$@" ;;
  "benchmark") shift; benchmark "$@" ;;
  "coordination-archive") shift; coordination_archive "$@" ;;
  "claude-aitmpl") shift; claude_aitmpl "$@" ;;
  "claude-agents") shift; claude_agents "$@" ;;
  "claude-agent-install") shift; claude_agent_install "$@" ;;
  "install-claude-plugin") install_claude_plugin ;;
  "skills") list_skills ;;
  "agents") list_agents ;;
  "sync") run_sync ;;
  "shell") cd "${WORKSPACE}" && exec bash ;;
  "help"|"-h"|"--help") show_help ;;
  *)
    echo "Unknown command: $1" >&2
    show_help >&2
    exit 2
    ;;
esac
