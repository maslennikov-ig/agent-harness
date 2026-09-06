Use $cleanup-audit for Codex, or `orchestration-bridge:cleanup-audit` in Claude Code.

Goal: audit stale branches, worktrees, sessions, Beads/stage tails, runtime leftovers, and cleanup candidates without deleting anything.

Must not forget: start read-only; classify each item as safe-local, needs-decision, keep, or blocked; exact cleanup commands require approval before execution.

Output: tail inventory, risk classification, proposed commands, blocked decisions, Beads/stage links, docs-reviewed/graph-reviewed impact.

Stop: do not remove worktrees, delete branches, close PRs, kill processes, clear caches, or mutate remotes without explicit approval.
