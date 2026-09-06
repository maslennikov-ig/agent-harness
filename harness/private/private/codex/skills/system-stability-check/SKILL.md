---
name: system-stability-check
description: Use when Codex, agents, the shared harness, MCP servers, hooks, local commands, or the development environment seem unstable, slow, duplicated, stale, or resource-heavy.
---

# System Stability Check

Run the bundled collector for a bounded, evidence-based health report. It has a 60-second global budget, a 15-second full `orchestration-latency/v1` benchmark cap, one config scan, and a synthetic check of the shared bounded Node test runner. Missing required evidence is an error; optional unavailable caches or `orch-prompts` are notes.

## Run

```bash
python3 "$(dirname "$(readlink -f "$0")")/scripts/check_system_stability.py"  # or the skill's absolute path
```

The collector resolves `CODEX_HOME` itself (explicit env, else the newest `/mnt/c/Users/*/.codex`, else `~/.codex`).

Add `--json` for machine-readable output.

Read `Warnings` first, then:

- `Bounded Node test runner`: confirms a synthetic Node test exits within its process-group boundary.
- `Harness latency`: prompt, overview, repo discovery, tails, throughput, Beads, and panel budgets.
- `Harness context`: run `orch-prompts context-audit`; inspect owned startup and
  scenario-peak reductions, layer budgets, semantic-owner conflicts, and the
  separate live-canary status.
- `Code Mode batching guidance`: confirms the approved batching rule appears once in global `AGENTS.md` and is not duplicated across custom-agent TOML files.
- `Process groups`: MCP duplication, stale tests, app-server, dev servers, and browsers.
- `WSL interop`: orphan `Relay` processes and `UtilAcceptVsock` accept timeouts from dmesg; each stuck relay makes every Windows `.exe` launched from WSL stall 10 s.
- `Latency`, memory, disk/caches, and Codex config.

## Interpretation

- Fast shell commands do not prove harness health; require the harness benchmark.
- A static context pass does not prove runtime speed. Do not make token or
  latency claims while `live_canary_status` is `not_run`.
- A runner failure, harness warn/error, invalid benchmark contract, stale panel, or failed tails/throughput/Beads check is a concrete regression.
- Missing or duplicated Code Mode batching guidance is configuration drift; keep one global copy instead of repeating it in every custom agent.
- Missing `orch-prompts` is unavailable evidence, not machine instability.
- Recent relay accept timeouts with live relay PIDs: ask the user to `kill -9` them as root (they ignore SIGTERM); if launches still stall, `wsl --shutdown`.
- Eight or more MCP process groups in one session, especially recent groups, signals a lifecycle leak. New servers remain visible through `other-mcp`.
- Node/Vitest/Jest processes older than six hours are stale unless their owner proves otherwise.
- Recommend an app restart after active work is saved when app-server RSS exceeds 4 GiB, or exceeds 2.5 GiB after seven days while available RAM is below 8 GiB.
- Duplicate MCP/plugin sources, `/mnt/c` above 95%, Playwright cache above 5 GiB, or npm `_npx` above 3 GiB need attention, not automatic cleanup.

## Safety

Do not kill processes, delete caches, or edit config unless the user explicitly asks. Never print raw process arguments. Correlate PID/PPID/PGID, session, launch time, and command name; redact Bearer/Authorization values, keys, tokens, passwords, and secrets before storing or printing any required text. Distinguish disabled Calendar/Drive entries from active integrations and heavy dev/browser processes from MCP pressure.
