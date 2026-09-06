Use $graphify-project for Codex Graphify work.

Goal: enable, audit, refresh, or query a local Graphify graph; CLI access does not authorize external model/API extraction.

Graphify is optional in routine work.

Must not forget: run `check-update` before trusting an existing graph and use `affected` for impact; a pre-#1504 warning requires ownership check, backup, and guarded local migration; read-only audits and localized fixes do not refresh; after setup refresh only at an accepted relevant integration or release boundary; new or changed Codex hooks require `/hooks` trust review; no git hooks or query logging by default; never paste graph.json.

Output: Graphify version/mode, changed files, included/excluded sources, node/edge counts when available, smoke query summaries, graph-reviewed, docs-reviewed, blockers.

Stop: ask before external semantic extraction, API keys, hosted backends, paid calls, git hooks, deleting graph dirs, or committing graph artifacts.
