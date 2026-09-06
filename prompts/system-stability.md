Run a full stability check of the current Codex/Desktop environment.

Work diagnostically only: do not delete anything, kill processes, disable MCP/plugins, or change configs without separate explicit approval.

Goal: separate real causes of slow or unstable Codex/Desktop behavior from normal background processes and give safe next actions.

Success criteria:
- The diagnostic reports concrete metrics for processes, command latency, MCP, disk, caches, configs, and hooks.
- Real problems are separated from normal background processes.
- Next actions are split into safe changes and actions requiring separate approval.

Use the `$system-stability-check` skill when it is available in the skill list. If the skill is available, open its `SKILL.md` first, then run the bundled checker:

```bash
python3 "${AGENTS_HOME:-$HOME/.agents}/skills/system-stability-check/scripts/check_system_stability.py"
```

The checker resolves `CODEX_HOME` itself (explicit env, else the newest `/mnt/c/Users/*/.codex`, else `~/.codex`); pass `CODEX_HOME` only to override. If that path is missing, use `${CODEX_HOME:-$HOME/.codex}/skills/system-stability-check`. Read its `WSL interop` section: orphan `Relay` processes with `UtilAcceptVsock` accept timeouts in `dmesg` make every Windows `.exe` launched from WSL stall exactly 10 s (confirm with `time cmd.exe /c exit`); they ignore SIGTERM, so the remedy is `kill -9` as root or `wsl --shutdown`, both separately authorized.

If the skill is missing, run a manual check:

1. Check Codex/Desktop processes: `codex app-server`, active `codex` sessions, old `claude` sessions, child processes, PID/PPID, RSS/CPU, and parent trees.
2. Check MCP processes and duplicates by group. Take the groups from what is actually configured — `claude mcp list` and `mcp_servers` in `${CODEX_HOME}/config.toml` — instead of a list that goes stale here; step 7 covers servers that were removed.
3. Check base command latency with fresh measurements: `bash -lc true`, `node -v`, `npm --version`, `git status --short`, simple `rg`/`find` over a small area.
4. Check disk pressure and large caches: `/`, `$HOME`, the WSL mount `/mnt/c` when present, `/tmp`, `$HOME/.cache/ms-playwright`, `$HOME/.npm/_npx`, `${CODEX_HOME}/.tmp/plugins`, `${CODEX_HOME}/plugins/cache`.
5. Check the global `${CODEX_HOME}/config.toml`: active `features`, `mcp_servers`, plugins, disabled Google Calendar/Drive, suspicious shell wrappers or commands that can slow startup.
6. Check hooks: global and project `.codex/hooks.json`, `PreToolUse`, `PostToolUse`, git hooks, Graphify hook-check, and any command that runs before every tool call.
7. Check `sequential-thinking` leftovers in active configurations: `config.toml`, `.mcp*.json`, `mcp.json`, `.claude/settings*.json`, `.gemini/settings*.json` under `${CODEX_HOME}`, `$HOME/.config`, `$HOME/.local/share/chezmoi`, `${CODEX_WORKSPACE:-$HOME/code}`. Exclude historical and noisy directories: `sessions`, `archived_sessions`, `_quarantine`, `log`, `.mypy_cache`, `node_modules`, `.git`, `graphify-out`.
8. Separate real problems from the normal diagnostic processes started by this check itself.
9. On WSL, check interop: `ps -eo pid,ppid,comm | awk '$3=="Relay"'` for orphan relays (PPID 1) and `dmesg | grep -c UtilAcceptVsock`; time `cmd.exe /c exit`.
10. If Impeccable is part of the active design stack, inspect its installed global skill metadata and provider/plugin configuration without running an installer or updater. Confirm Claude uses the official `impeccable@impeccable` marketplace plugin instead of a duplicate CLI copy, and flag an enabled `frontend-design@claude-plugins-official` as a conflicting design ruleset. Keep Lazyweb and Stitch presence informational. If freshness cannot be established read-only, recommend a separately authorized update workflow.

Stop rules:
- Use reasonable timeouts for commands that can hang.
- Do not run deep recursive scans over huge trees without filters and exclusions.
- If the manual check grows too broad, report top-level metrics first and propose the next precise safe check.

Output:
Answer in Russian, briefly but with numbers:

- overall status: stable / warnings / critical problem;
- the most important metrics: command latency, WSL interop latency and relay state, Codex/MCP process counts, heaviest memory groups, disk fill, and cache sizes;
- what exactly affects startup and response latency;
- what can be fixed safely as the next step, separated from risky actions;
- if everything is stable, say directly that nothing needs fixing now.
