Use `orchestration-bridge:system-stability` for a Claude Code CLI stability check.

Target runtime: Claude Code CLI in the VS Code integrated terminal on WSL.

Work diagnostically only: do not delete files, kill processes, disable plugins/MCP servers, change settings, or mutate configs without separate explicit approval.

Goal: separate real causes of slow or unstable Claude Code CLI/VS Code/WSL behavior from normal background processes and give safe next actions.

Checks:
1. `claude --version`, `timeout 20s claude doctor || true`, `claude plugin list`, `claude agents --json`, and `timeout 30s claude mcp list || true`. Flag any skills-directory plugin reported `Not loaded` because its name is taken by an installed plugin (for example `superpowers@skills-dir`): its skills are silently absent.
2. VS Code/WSL mode: integrated terminal, workspace location under `/home/`, PATH visibility, `ripgrep`, terminal GPU setting advisory, `/ide` only for external-terminal attach.
3. Plugins/settings: enabled/disabled plugins, hooks, deny rules, `CLAUDE_HOME`, `~/.claude/CLAUDE.md`, and redacted `~/.claude.json` metadata. Do not expose secret values.
4. MCP health: configured servers, duplicate/stuck MCP processes, slow commands, and whether failures are transient timeouts or persistent errors.
5. Command latency: `bash -lc true`, `node -v`, `npm --version`, `git status --short`, simple `rg`/`find` over a small local area.
6. Disk/cache pressure: `/`, `$HOME`, `/tmp`, WSL Windows mount if relevant, npm/npx caches, Playwright cache, Claude plugin/cache dirs.
7. Hooks and startup costs: global/project Claude hooks, shell wrappers, long-running watchers, old Claude sessions, and heavy dev servers. A `Stop`/`Notification` hook that calls `powershell.exe` or `cmd.exe` synchronously pays the full WSL interop cost on every stop; prefer one global hook with `"async": true` over per-project copies.
8. Bundled checker and WSL interop: run `python3 ~/.agents/skills/system-stability-check/scripts/check_system_stability.py` (shared with Codex; it resolves `CODEX_HOME` itself) and read `Warnings` and `WSL interop`. Orphan `Relay` processes (`/init`, PPID 1, no children) with `UtilAcceptVsock` accept timeouts in `dmesg` make every Windows `.exe` launched from WSL stall exactly 10 s; confirm with `time cmd.exe /c exit`. They ignore SIGTERM, so the fix is `kill -9` as root or `wsl --shutdown`, both approval-required.
9. Design stack: verify `impeccable@impeccable` comes from the official Impeccable marketplace, its marketplace has auto-update enabled, no duplicate CLI-installed Claude copy is active, and `frontend-design@claude-plugins-official` is disabled because it conflicts with Impeccable. Keep Lazyweb and Stitch installed unless they have an independent failure.

Success criteria:
- Report concrete metrics for CLI version, plugin/MCP state, command latency, WSL interop latency, process counts, disk/cache pressure, and hook/plugin risks.
- Separate real problems from normal background processes and checks started by this diagnostic run.
- Next actions are split into safe changes and actions requiring explicit approval.

Stop rules:
- Use reasonable timeouts for commands that can hang.
- Do not run deep recursive scans over huge trees without filters and exclusions.
- Stop before any config mutation, process kill, cache prune, plugin disable, MCP removal, or destructive cleanup.

Output:
- Overall status: stable, warnings, or critical problem.
- WSL interop status: relay count, accept timeouts, `.exe` launch latency.
- Key metrics with numbers and evidence sources.
- What affects startup/response latency.
- Safe next actions vs approval-required actions.
- If stable, say directly that no fix is needed now.
