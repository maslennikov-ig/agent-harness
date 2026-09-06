---
name: cleanup-audit
description: Use when Codex should audit stale branches, worktrees, sessions, Beads/stage tails, caches, or runtime leftovers before any cleanup.
---

# Cleanup Audit

Start read-only. Cleanup commands are proposals until the user approves them.

## Audit

Inspect:
- `git status --short --branch`
- local and remote branches
- worktrees
- Beads tasks, stage/handoff links, completion inbox state
- active dev servers, MCP servers, Codex/Claude sessions, logs, caches
- repo delivery policy and protected branches

Classify each item:
- `safe-local`: removable after explicit approval
- `needs-decision`: needs user choice or repo owner context
- `keep`: active, protected, or intentionally retained
- `blocked`: cannot classify safely

## Output

- Inventory grouped by project/runtime
- Classification and evidence for each cleanup candidate
- Exact proposed commands
- Commands requiring approval
- Blockers and follow-up decisions
- `docs-reviewed` and `graph-reviewed` impact when applicable

## Stop Rules

Do not remove worktrees, delete branches, close PRs, kill processes, clear caches, mutate remotes, or close Beads tasks unless the user explicitly approves the exact action.
