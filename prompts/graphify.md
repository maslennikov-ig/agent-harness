Use $orchestrator-stage and $graphify-project to enable or refresh Graphify for the current repository.

If `$graphify-project` is not listed in the active skill list, read and follow:
`${AGENTS_HOME:-$HOME/.agents}/skills/graphify-project/SKILL.md`.

Goal: create or update a local Graphify knowledge graph so future agents know it is an optional orientation aid, can use `graphify-out/GRAPH_REPORT.md` and focused `graphify query/path/explain` when useful, and refresh the graph only at setup/migration or an accepted relevant integration or release boundary.

Hard rules:
- Read-only audits and localized fixes do not refresh the graph; after setup, code/docs/architecture/durable workflow changes make the next accepted relevant integration or release boundary eligible for refresh.
- If I asked only for an audit/status check, do not write files; report the current Graphify state and the exact changes you would make.
- `graphify` CLI is the local graph engine; `$graphify-project` is the setup/refresh workflow.
- Do not run external model/API-backed Graphify extraction, configure API keys, paid model calls, hosted backends, or semantic enrichment unless I explicitly authorize that in this task.
- Do not install Graphify git hooks unless I explicitly ask.
- The project-local Codex `PreToolUse` hook running `graphify hook-check` is allowed for Graphify-enabled Codex repos. A new or changed non-managed hook must be reviewed and trusted through `/hooks`; writing the file does not prove it ran, and normal setup never bypasses hook trust.
- Keep query logging disabled unless I explicitly request persisted query telemetry.
<!-- fragment:graphify-hygiene -->
- Do not commit large generated `graphify-out/` artifacts unless the repo contract explicitly wants shared graph outputs.
- Never paste `graphify-out/graph.json` into chat.
- Use Beads before file-changing setup when Beads is available.
<!-- /fragment:graphify-hygiene -->
- If the repo is too small to benefit, say so and stop with a recommendation.

Preflight:
1. Read repo rules (`AGENTS.md`/equivalent), `.gitignore`, package/config files, docs, handoff/project notes if present, and `git status`.
2. Create or select a Beads task before changing files when Beads is available.
3. Identify generated/noisy/secret/large paths to ignore, plus useful docs/ADRs/runbooks/research/PDF sources to keep.
4. Verify Graphify CLI/version/path. If missing, outdated, or missing `tree_sitter_sql`, follow the skill's install/SQL-extra guidance.
5. Run `graphify check-update .` before trusting an existing graph. A pre-#1504 warning uses the skill's ownership, backup, and migration guard.

Implementation:
1. Create/update `.graphifyignore` to exclude generated/noisy/secret files while keeping useful durable docs.
2. Add `graphify-out/` to `.gitignore` unless the repo intentionally shares graph artifacts.
3. Add a short project rule saying Graphify is optional, suggesting `GRAPH_REPORT.md` and focused graph queries when useful, avoiding `graph.json` and Graphify git hooks, allowing the Codex PreToolUse hook, refreshing only at an accepted relevant integration or release boundary after setup, and reporting `graph-reviewed`.
4. Add or merge `.codex/hooks.json` with a `PreToolUse` hook for `Bash` that runs the resolved `graphify hook-check` command.
5. If orchestration config exists, add/refresh a small knowledge-graph section: enabled flag, graph dir, ignore file, update/query commands, Codex hook allowed, git hooks false, closeout marker.
6. Build with `graphify update .`, then `graphify cluster-only . --no-viz --no-label`; `--no-label` prevents external label calls.
7. Run two focused queries; use `graphify affected "<exact-node-id>"` for impact.
8. Legacy migration: back up, run `graphify update . --force` then `graphify cluster-only . --no-viz --no-label --timing`, and verify the warning disappears. `--timing` is diagnostic-only; semantic blockers follow the skill's stop rule.

Closeout:
- Run `git status --short` and `git diff --check`.
- Verify generated `graphify-out/` is ignored/not staged.
- Verify `.codex/hooks.json` contains only the intended Codex Graphify hook and report whether the exact new or changed definition has completed `/hooks` trust review.
- Verify Graphify git hooks are absent unless explicitly requested.
- Keep query logging disabled; rerun `graphify check-update .` and `graphify affected` when impact matters; confirm no pre-#1504 warning remains.
- Compare current `git rev-parse --short=8 HEAD` with `Built from commit` in `graphify-out/GRAPH_REPORT.md`; refresh if setup changed HEAD after graph build.
- Check `graphify-out/graph.json` has no forbidden `source_file` entries for excluded roots such as `.worktrees/`, `.claude/`, `node_modules/`, and `graphify-out/`.
- Update Beads with commands run and graph status when available.
- Report Graphify version, mode (`code/local graph`, `full semantic`, or `blocked/deferred semantic`), hook status, nodes/edges, included/excluded sources, changed files, smoke query summaries, blockers, next action, `docs-reviewed`, and `graph-reviewed`.

Stop rules:
- Stop before external model/API-backed extraction, configuring API keys, paid model calls, hosted backends, Graphify git hooks, or committing generated graph artifacts unless explicitly authorized.
- Stop if Graphify CLI or repo ownership cannot be established from local evidence.

Output:
- Mode: audit-only, updated local graph, or blocked.
- Files changed or reviewed-no-change.
- Graphify version, hook status, nodes/edges, included/excluded sources, and smoke query summaries.
- Verification evidence, `docs-reviewed`, and `graph-reviewed`.
- Blockers, next action, and remaining explicit defers.

After setup, tell me that Codex skips a new or changed project-local hook until I review and trust the exact definition through `/hooks`.
