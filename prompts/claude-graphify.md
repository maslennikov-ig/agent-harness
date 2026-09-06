Use `orchestration-bridge:graphify-project` to audit, enable, or refresh Graphify for the current repository in Claude Code CLI.

Goal: create or update a local Graphify knowledge graph so future Claude/Codex agents know it is an optional orientation aid, can use `graphify-out/GRAPH_REPORT.md` and focused `graphify query/path/explain` when useful, and report `graph-reviewed` during closeout.

Hard rules:
- Read-only audits and localized fixes do not refresh the graph; after setup, code/docs/architecture/durable workflow changes make the next accepted relevant integration or release boundary eligible for refresh.
- If asked only for an audit/status check, do not write files; report current Graphify state and exact proposed changes.
- `graphify` CLI is the local graph engine. Do not run external model/API-backed extraction, configure API keys, paid model calls, hosted backends, or semantic enrichment unless explicitly authorized.
- Do not install Graphify git hooks unless explicitly asked.
- Claude should treat Graphify as a local CLI knowledge source. Codex-specific `.codex/hooks.json` hook setup is only in scope when the repo is also a Codex-enabled repo and the user asks for it.
- Keep query logging disabled unless explicitly requested.
<!-- fragment:graphify-hygiene -->
- Do not commit large generated `graphify-out/` artifacts unless the repo contract explicitly wants shared graph outputs.
- Never paste `graphify-out/graph.json` into chat.
- Use Beads before file-changing setup when Beads is available.
<!-- /fragment:graphify-hygiene -->

Preflight:
1. Read repo rules (`AGENTS.md`, `CLAUDE.md`), `.gitignore`, package/config files, docs, handoff/project notes if present, and `git status`.
2. Create/select a Beads task before changing files when Beads is available.
3. Identify generated/noisy/secret/large paths to ignore, plus useful docs/ADRs/runbooks/research/PDF sources to keep.
4. Verify Graphify CLI/version/path. If missing, outdated, or missing `tree_sitter_sql`, follow the skill's install/SQL-extra guidance and approval boundary.
5. Run `graphify check-update .` before trusting an existing graph. A pre-#1504 warning uses the skill's ownership, backup, and migration guard.

Implementation, when approved:
1. Create/update `.graphifyignore` to exclude generated/noisy/secret files while keeping useful durable docs.
2. Add `graphify-out/` to `.gitignore` unless the repo intentionally shares graph artifacts.
3. Add a short project rule saying Graphify is optional, suggesting `GRAPH_REPORT.md` and focused graph queries when useful, avoiding `graph.json` and Graphify git hooks, refreshing only at an accepted relevant integration or release boundary after setup, and reporting `graph-reviewed`.
4. Build with `graphify update .`, then `graphify cluster-only . --no-viz --no-label`; `--no-label` prevents external label calls.
5. Run two focused queries; use `graphify affected "<exact-node-id>"` for impact.
6. Legacy migration: back up, run `graphify update . --force` then `graphify cluster-only . --no-viz --no-label --timing`, and verify the warning disappears. `--timing` is diagnostic-only; semantic blockers follow the skill's stop rule.

Closeout:
- Run `git status --short` and `git diff --check`.
- Verify generated `graphify-out/` is ignored/not staged unless intentionally tracked.
- Verify Graphify git hooks are absent unless explicitly requested.
- Keep query logging disabled; rerun `graphify check-update .` and `graphify affected` when impact matters; confirm no pre-#1504 warning remains.
- Report Graphify version, mode, hook status, nodes/edges, included/excluded sources, changed files, smoke query summaries, blockers, next action, `docs-reviewed`, and `graph-reviewed`.

Stop rules:
- Stop before installing Graphify, configuring API keys, enabling external model/API extraction, adding git hooks, committing generated graph artifacts, or making broad repo-policy changes without explicit approval.
- Stop if secret/noisy/generated path handling is uncertain and graph generation could index sensitive or oversized content.

Output:
- Mode: audit-only, enabled, or refreshed.
- Files changed or reviewed-no-change.
- Graphify command evidence and smoke-query summaries.
- Hook status and generated-artifact tracking/ignore status.
- Remaining blockers or next action.
