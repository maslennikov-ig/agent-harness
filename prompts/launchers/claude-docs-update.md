Use `orchestration-bridge:orchestrator-stage` routing and `orchestration-bridge:closeout` for Claude docs freshness.

Goal: check README/docs/CLAUDE/AGENTS/runbooks against current behavior, verification commands, architecture, deploy/runtime notes, and memory routing.

Must not forget: keep CLAUDE.md thin; import AGENTS when appropriate; remove stale template-bridge/Context7-first assumptions; use docs-reviewer only when it adds value.

Output: docs changed or no-change-needed with concrete reason, files/sections reviewed, runtime/memory notes, docs-reviewed result, graph-reviewed if configured.

Stop: ask before broad rewrites, plugin/settings changes, remote/live actions, or deleting project-specific memory.
