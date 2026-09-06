---
name: graphify-project
description: "Use when a repository enables Graphify and needs local graph setup, freshness checks, focused queries, or a guarded refresh."
---

# Graphify Project

Routine project work does not require Graphify. When it is useful for orientation and `graphify-out/GRAPH_REPORT.md` exists, run `graphify check-update .` before trusting it and then read the report. Do not trust a graph whose focused query reports pre-#1504 node IDs.

The graph answers code-structure questions: what calls what, what a change reaches, how unfamiliar modules relate. It is not a documentation index. `graphify update` extracts document file names and headings but never document text, and queries match node names rather than content, so information inside docs, ADRs, runbooks, and research notes is found by reading and grepping them.

Use focused commands:

```bash
graphify query <terms>
graphify path <from> <to>
graphify explain <node>
graphify affected <exact-node-id>
```

Use `graphify affected` for blast-radius questions. Keep query logging disabled unless the user explicitly requests persisted telemetry.

If Graphify reports missing `tree_sitter_sql` in a repo with relevant SQL, treat the graph as incomplete. With dependency-install authorization, add the official `graphifyy[sql]` extra at the current version, rebuild, and verify SQL nodes appear.

For a pre-#1504 graph, first verify worktree ownership and back up `graphify-out` outside the repo. Then use the local migration path:

```bash
graphify update . --force
graphify cluster-only . --no-viz --no-label --timing
graphify check-update .
```

Use `--no-label` to prevent external community-label calls and `--timing` only for migration/rebuild diagnostics. Verify the warning disappears with a focused query. If semantic content cannot be reproduced locally, stop with the backup path; do not substitute a code-only graph or authorize semantic extraction implicitly.

Do not paste `graphify-out/graph.json` into prompts.

Do not install Graphify git hooks unless explicitly asked. Codex repos may use a narrow `.codex/hooks.json` PreToolUse hook; a new or changed non-managed Codex hook must complete `/hooks` trust review before anyone relies on it. Claude should treat Graphify as a local CLI knowledge source.

During closeout, read-only work and localized fixes report `graph-reviewed: used/no-change-needed`; refresh local Graphify only at an accepted relevant integration or release boundary when safe and report `updated`, otherwise report `blocked` with a concrete reason.
