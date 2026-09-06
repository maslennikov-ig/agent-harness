---
name: system-stability
description: "Use when diagnosing Claude Code CLI, VS Code/WSL, MCP, hooks, or local runtime stability without changing configuration."
---

# Claude System Stability

Work diagnostically only.

Check:
- `claude --version`, `claude doctor`, `claude plugin list`, `claude agents --json`. A skills-dir plugin reported `Not loaded` (name taken by an installed plugin) means its skills are silently absent.
- VS Code integrated terminal PATH and WSL filesystem location.
- `rg` availability; set `USE_BUILTIN_RIPGREP=0` only after explicit config change approval.
- MCP status through `claude mcp list` and `/mcp` when inside chat.
- Hooks and enabled plugins; isolate suspected plugin/hook issues with `claude --safe-mode`. Hooks that call `powershell.exe`/`cmd.exe` synchronously pay the WSL interop cost on every event; prefer one global hook with `"async": true`.
- Bundled checker shared with Codex: `python3 ~/.agents/skills/system-stability-check/scripts/check_system_stability.py`. Its `WSL interop` section reports orphan `Relay` processes and `UtilAcceptVsock` accept timeouts; each stuck relay makes every Windows `.exe` launched from WSL stall 10 s (`time cmd.exe /c exit`). They ignore SIGTERM: `kill -9` as root or `wsl --shutdown`, only with approval.
- Harness context through `orch-prompts context-audit`: owned startup/peak,
  layer budgets, semantic ownership, and live-canary status. A static pass does
  not prove token or wall-time improvement.
- Impeccable design stack: verify `impeccable@impeccable` is enabled from the official `pbakaus/impeccable` marketplace with auto-update, no duplicate CLI-installed Claude copy is active, and `frontend-design@claude-plugins-official` is disabled because its rules conflict with Impeccable. Lazyweb and Stitch may remain installed for their narrower roles.
- CPU, memory, disk pressure, and long-running dev/MCP processes.

Report status, evidence, likely cause, and safe next commands. Do not mutate settings unless explicitly asked.
