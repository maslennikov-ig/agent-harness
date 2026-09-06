Use `orchestration-bridge:graphify-project` for Claude Graphify work.

Goal: use or refresh a local Graphify graph in Claude Code CLI; no git hooks or external semantic backends by default.

Graphify is optional in routine work.

Must not forget: run `check-update` before trusting an existing graph and use `affected` for impact; a pre-#1504 warning requires ownership check, backup, and guarded local migration; read-only audits and localized fixes do not refresh; after setup refresh only at an accepted relevant integration or release boundary; no query logging by default; never paste graph.json.

Output: mode, graph/report status, focused queries used, changed files if any, graph-reviewed, docs-reviewed, blockers.

Stop: ask before Graphify git hooks, external semantic extraction, API/model calls, deleting graph dirs, plugin/settings changes, or committing graph artifacts.
