---
name: cleanup-audit
description: "Use when auditing stale branches, worktrees, sessions, tasks, or runtime leftovers before any cleanup."
---

# Cleanup Audit

Start read-only. Do not remove worktrees, delete branches, close PRs, kill processes, or run remote deletion until exact commands are approved.

Audit:
- `git status --short --branch`, branches, remotes, worktrees, and active processes.
- Beads/stage/handoff links.
- Runtime leftovers: dev servers, MCP servers, Claude/Codex sessions, logs, caches.

Classify items as `safe-local`, `needs-decision`, `keep`, or `blocked`.

Report exact proposed commands and ask for approval before action.
