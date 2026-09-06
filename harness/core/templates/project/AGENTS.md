# Project Agent Rules

- Keep user-facing communication concise and explicit.
- Use the local repo instructions before broader defaults.
- Use `harness init-project` only for project-local baseline files.
- Do not commit secrets, runtime state, `.beads/`, `graphify-out/graph.json`, logs, caches, or local screenshots.
- For external/versioned dependency behavior, use `orch-prompts docs-resolve`.
- Use the installed `orchestrator-stage` workflow when its task trigger applies.
- This is a starter project configuration. Use `orchestration-setup` when a
  full repository-specific baseline is needed; derive verification commands
  and delivery rules from this project's code and owner.
- Graphify is an optional local aid when helpful; keep it in local mode unless
  the user explicitly authorizes external model/API extraction.
