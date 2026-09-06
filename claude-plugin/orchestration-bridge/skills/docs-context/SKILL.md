---
name: docs-context
description: "Use for current/version-sensitive dependency documentation and when inspecting or refreshing the shared Docs L1/L2 stack used by Codex and Claude."
---

# Docs Context

Use the shared docs state in `${AGENTS_HOME:-$HOME/.agents}/docs-context/`.

Agent entrypoint:

```bash
orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<domain API keywords>'
```

Operator diagnostics use `orch-prompts docs-diagnose --json` for the secret-safe
Codex/Claude provider inventory and `orch-prompts docs-context` for L1 coverage.
`docs-context-sync` remains dry-run unless `--write` is explicit.

Policy:
- The kernel owns the Documentation decision; this skill owns resolver mechanics. Docs Resolver accepts only the exact version or a newer patch in the same major.minor track from `@neuledge/context` L1.
- Floating `latest`, another track, stale/missing docs, or irrelevant results are fallback conditions.
- L2 fallback is Context7 MCP or official docs only when Docs Resolver reports L1 missing, stale, cross-track, floating, or insufficient after local lookup/auto-download.
- Persist an L2 answer back into L1 with `orch-prompts docs-persist` so the next task and a post-compaction resume resolve locally; it refuses unpinned versions and unattributed sections. Skipped calls accumulate in `state/docs-persist-debt.jsonl` and surface in `docs-context`; nothing blocks on them.
- For a signature rather than prose, `orch-prompts docs-signature --cwd <repo> --package <name> --symbol <name>` reads the installed package directly, so it is version-correct even when L1 carries the package only as `latest`.
- `context` exposes `get_docs`, `search_packages`, and `download_package`; Context7 exposes `resolve-library-id` and `query-docs`. Empty MCP resources/templates do not prove them unavailable. Inspect `/mcp` in Claude or `ALL_TOOLS` in Codex.
- Direct MCP tool injection is optional for this workflow; `docs-resolve` remains authoritative when the active model does not expose those tools.
- Open a fresh task after Harness skill changes. Restart the relevant host only after an actual MCP configuration change, not from config-file mtime or missing direct tools alone.
- Never hardcode Context7 keys or other credentials.
