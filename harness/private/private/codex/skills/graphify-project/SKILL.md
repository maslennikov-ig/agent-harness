---
name: graphify-project
description: Use when enabling, auditing, refreshing, or using Graphify as a local project knowledge graph, especially when setup must be skill-driven and must not use external model/API-backed Graphify extraction unless explicitly authorized.
---

# Graphify Project

## Core Rule

This skill is the workflow. The `graphify` CLI is only the local graph engine used by the workflow.

Do not interpret a request to "enable Graphify" as permission to run standalone external model/API-backed extraction. Do not configure API keys, hosted backends, paid model calls, or Graphify git hooks unless the user explicitly asks in the current task.

For Codex, a narrow project-local `PreToolUse` hook that runs `graphify hook-check` is allowed during setup only when it stays inside the project and does not present an unchecked stale graph as authoritative. This is not the same as Graphify git hooks.
Codex skips a new or changed non-managed project hook until the user reviews and trusts the exact definition through `/hooks`. Writing `.codex/hooks.json` is not proof that the hook ran; never bypass hook trust for setup convenience.

Default mode:

- local Graphify CLI installed or verified
- `.graphifyignore`, repo instructions, and optional orchestration config updated
- `.codex/hooks.json` includes the Codex `PreToolUse` Graphify reminder hook when the repo uses Codex
- `graphify update .` and `graphify cluster-only . --no-viz --no-label` used for a local project graph/report without external community-label calls
- generated `graphify-out/` kept local and ignored unless the repo explicitly wants shared graph artifacts
- semantic/docs/PDF enrichment attempted only through an already available and authorized local/session-backed path; otherwise report it as blocked or deferred

## Pre-implementation Decision Gate

Apply the two independent gates owned by `orchestrator-stage` in
`references/autonomy-and-approvals.md`; do not duplicate them here. Inspect
available evidence first, ask only when a gate qualifies, otherwise record the
decision and proceed.

## Preflight

Before changing files:

1. Read repo instructions: `AGENTS.md`, `CLAUDE.md`, `.codex/orchestrator.toml`, handoff/project notes, and `.gitignore` when present.
2. Create or select a Beads task if Beads is available and the setup will change files.
3. Inspect the repo shape, generated folders, dependencies, build outputs, temp/test artifacts, secrets/env files, large media, worktrees, and useful docs/research/PDF sources.
4. Decide whether the repo is large or durable enough to benefit from Graphify. For tiny/simple repos, stop with a recommendation instead of forcing setup.
5. When `graphify-out/graph.json` already exists, run `graphify check-update .` and one focused query before trusting it. If the query reports pre-#1504 node IDs, follow the guarded legacy migration below before using the graph for architecture or impact decisions.

## Setup

1. Verify the CLI engine:

   ```bash
   graphify --version
   graphify --help
   ```

   If it is missing, broken, or lacks a required parser, read `references/installation.md` before installing or changing dependencies.

2. Create or update `.graphifyignore`.

   Exclude dependency folders, build outputs, coverage, temp files, test artifacts, secrets, local worktrees, runtime state, large raw recordings, and agent runtime noise. Keep stable docs, ADRs, runbooks, and relevant PDFs unless the repo excludes them.

3. Add `graphify-out/` to `.gitignore` unless the repo explicitly commits shared graph artifacts.

4. Add a compact repo rule to `AGENTS.md` or the repo equivalent:

   - say Graphify is optional and suggest `graphify-out/GRAPH_REPORT.md` when it helps with architecture, impact, or unfamiliar areas
   - use focused `graphify query`, `graphify path`, or `graphify explain`
   - the graph answers code-structure questions; read a document to learn what it says
   - never paste `graphify-out/graph.json` into chat context
   - Codex `PreToolUse` Graphify hook is allowed for graph reminders
   - do not install Graphify git hooks or external semantic backends unless explicitly asked
   - record `graph-reviewed: used`, `updated`, `blocked`, or `no-change-needed`; read-only audits and localized fixes do not refresh, while an accepted relevant integration or release boundary refreshes the local graph when safe

5. Add or merge `.codex/hooks.json` for Codex projects:

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Bash",
           "hooks": [
             {
               "type": "command",
               "command": "${HOME}/.local/bin/graphify hook-check"
             }
           ]
         }
       ]
     }
   }
   ```

   If the `graphify` binary lives elsewhere, use `which graphify` and record the resolved absolute path. Do not add git hooks with `graphify hook install`.
   After writing or changing the hook, tell the user to inspect `/hooks` and trust the exact definition before relying on it. Do not use `--dangerously-bypass-hook-trust` as part of normal setup.

6. If `.codex/orchestrator.toml` exists, add a small `[knowledge_graph]` section with graph dir, ignore file, update/query/affected/check-update commands, hook policy, and closeout marker. Use `hooks_allowed = "codex_pre_tool_use_only"` or equivalent, `git_hooks_allowed = false`, and `codex_pre_tool_use_hook = true`.

## Build And Refresh

Use the local graph engine:

```bash
graphify check-update .
graphify update .
graphify cluster-only . --no-viz --no-label
```

Run these commands after all tracked setup files are written. Later, run them at an accepted relevant integration or release boundary after code, architecture docs, entrypoints, routes, integrations, contracts, or durable workflow/instructions changed. Read-only audits, stage-local notes, and localized review fixes do not rebuild the graph. A later commit or rebase triggers a rebuild only when that new `HEAD` is itself another accepted relevant integration or release boundary. Before final reporting, compare `git rev-parse --short=8 HEAD` with `Built from commit` in `graphify-out/GRAPH_REPORT.md`; during setup or an approved legacy migration they must match unless the final state intentionally has only uncommitted local changes, which must be reported.

Use `graphify affected "<exact-node-id>" --graph graphify-out/graph.json` when it helps answer a blast-radius question without a broad grep/read loop. Use `query`, `path`, and `explain` for orientation and relationships.

Keep query logging disabled by default. Do not set `GRAPHIFY_QUERY_LOG`, `GRAPHIFY_QUERY_LOG_ENABLE`, or `GRAPHIFY_QUERY_LOG_RESPONSES` unless the user explicitly requests persisted query telemetry; logs can retain query text, corpus paths, and optionally full responses.

## Legacy Migration And Semantic Sources

If a focused query reports pre-#1504 node IDs, `.graphifyignore` was tightened against already-indexed sources, or semantic/non-code extraction is in scope, read `references/legacy-and-semantic.md` before acting. Routine local graph use and accepted-boundary refreshes do not load that migration/backend detail.

## Closeout

Before reporting completion:

1. Run `git status --short` and `git diff --check`.
2. Confirm `graphify-out/` is ignored and not staged.
3. Confirm `.codex/hooks.json` contains only the intended Codex `PreToolUse` Graphify hook.
4. Confirm Graphify git hooks are not installed unless explicitly requested. Report whether the Codex hook is trusted; if a new or changed hook still awaits `/hooks` review, record that exact blocked state instead of claiming it ran.
5. Confirm `graphify-out/GRAPH_REPORT.md` `Built from commit` matches current `HEAD` after setup or after any commit made during setup. If not, rerun `graphify update .` and `graphify cluster-only . --no-viz --no-label`.
6. Confirm `graphify-out/graph.json` has no forbidden `source_file` entries for excluded runtime/noise roots such as `.worktrees/`, `.claude/`, `node_modules/`, and `graphify-out/`.
7. Run `graphify check-update .`; for impact-sensitive work, include one `graphify affected` result. Confirm no pre-#1504 warning remains after an approved migration.
8. Confirm query logging remains disabled unless the user explicitly requested it.
9. Update Beads with commands and graph status when Beads is available.
10. Report `docs-reviewed: updated` or `docs-reviewed: no-change-needed`.
11. Report `graph-reviewed: updated`, `used`, `no-change-needed`, or `blocked` with command evidence.

Final report must include:

- Graphify version and install method
- mode: `code/local graph`, `full semantic`, or `blocked/deferred semantic`
- node/edge counts when available
- included and excluded sources
- changed files
- smoke query summaries
- blockers and next recommended action
