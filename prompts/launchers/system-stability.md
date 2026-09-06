Use $system-stability-check for Codex/Desktop diagnostics.

Goal: produce an evidence-based local stability report for Codex, MCP servers, hooks, command latency, disk/memory pressure, caches, and heavy dev processes.

Must not forget: diagnostic only; run the bundled checker (shared copy in `~/.agents/skills/system-stability-check`, resolves `CODEX_HOME` itself); read its `WSL interop` section (orphan `Relay` processes with `UtilAcceptVsock` timeouts stall every `.exe` launch 10 s); distinguish disabled config from active processes; call out duplicate MCP groups and heavy servers separately.

Output: summary, warnings, process groups, WSL interop, latency, disk/cache status, Codex config/MCP/plugin notes, safe next commands.

Stop: do not kill processes, delete caches, edit config, or restart services unless the user explicitly asks for fixes.
