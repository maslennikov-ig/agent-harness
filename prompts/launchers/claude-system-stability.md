Use `orchestration-bridge:system-stability` for Claude Code CLI diagnostics.

Goal: check Claude Code CLI in VS Code/WSL: `claude --version`, doctor/plugin/agent/MCP state, PATH, WSL filesystem, hooks, latency, disk/cache, suspicious plugin behavior, and WSL interop (run the shared bundled checker in `~/.agents/skills/system-stability-check`; orphan `Relay` processes with `UtilAcceptVsock` timeouts make every `.exe` launch stall 10 s).

Must not forget: diagnostic only; prefer VS Code integrated terminal assumptions; use `/ide` only as external terminal fallback; redact secrets; flag skills-dir plugins reported `Not loaded` and hooks that call Windows `.exe` synchronously.

Output: status, warnings, evidence, likely causes, safe next commands, VS Code/WSL notes, WSL interop status, MCP/plugin/agent visibility.

Stop: do not mutate settings, disable plugins, kill processes, clear caches, or run destructive commands without explicit approval.
