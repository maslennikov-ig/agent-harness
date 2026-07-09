# Project Agent Rules

- Keep user-facing communication concise and explicit.
- Use the local repo instructions before broader defaults.
- Use `harness init-project` only for project-local baseline files.
- Do not commit secrets, runtime state, `.beads/`, `graphify-out/graph.json`, logs, caches, or local screenshots.
- Use Docs L1/L2 for current dependency docs and examples: query `@neuledge/context` first with lockfile-routed package/version; use Context7 MCP or first-party docs only when L1 is missing, stale, or insufficient.
- Use Beads for file-changing, delegated, long-running, or handoff-prone work.
- Use Graphify only in local mode unless the user explicitly authorizes external model/API extraction.
