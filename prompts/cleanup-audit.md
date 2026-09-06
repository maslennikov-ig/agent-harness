Use $cleanup-audit for Codex, or `orchestration-bridge:cleanup-audit` in Claude Code, for a total repository cleanup audit.

Goal: find local and remote tails, classify what is safe to remove, and ask me for explicit approval before deleting anything.

Success criteria:
- Every cleanup candidate is classified as `safe-local`, `needs-decision`, `keep`, or `blocked`.
- No destructive command is run before exact approval.
- Approval request lists numbered exact commands and risks.

Stop rules:
- Start read-only. Do not remove worktrees, delete branches, close PRs, prune caches, delete files, run `git push --delete`, or use destructive `rm`/`git branch -D`/`git worktree remove` until I approve exact items and commands.
- Stop if an item is dirty, active, protected, remote, linked to an open task/PR, or not listed in the approval table.

Scope to audit:
- Git state: `git status --short --branch`, current branch, protected/base branches, remotes, ahead/behind.
- Worktrees: `git worktree list --porcelain`, project `.worktrees/`, `.codex/worktrees/`, `.claude/worktrees/`, and active processes whose cwd is inside a candidate worktree.
- Local branches: merged/unmerged, age, upstream, ahead/behind, branch prefix (`codex/`, agent/worktree branches), linked worktrees, related Beads/stage/artifacts/PR.
- Remote tails: `git remote -v`, `git ls-remote --heads origin`, remote-tracking refs, `git remote prune origin --dry-run`, merged/stale `origin/*` branches. Remote branch deletion always needs explicit current approval per branch.
- Orchestration state: `.codex/orchestrator.toml`, `.codex/handoff.md`, `.codex/stages/*/summary.md`, artifacts with `cleanup_status`, and repo cleanup scripts.
- Beads: open/closed tasks that mention candidate branches, worktrees, stage ids, or follow-ups.
- Runtime leftovers: dev servers, MCP servers, watchers, test runners, browser sessions, temp logs, generated artifacts, caches. Only propose cleanup; do not kill/delete without approval.

Classify every candidate:
- `safe-local`: can be removed after approval because it is merged/delivered, clean, not current, not protected, and has no active process.
- `needs-decision`: plausible tail but not enough evidence, remote branch, unmerged branch, dirty worktree, active process, open PR/task, or manual/cherry-pick integration.
- `keep`: protected/current/active/undelivered/unknown owner.
- `blocked`: cannot verify safely; explain missing evidence.

Output:
- Summary counts: worktrees, local branches, remote branches, active processes, Beads/stage links.
- Table: item, location/ref, age if available, evidence, classification, risk, proposed exact command, reason.
- Separate “Approval requested” section with numbered cleanup items. Ask me to approve all, approve selected numbers, or keep all.

After approval:
- Execute only approved exact commands.
- Prefer safe commands: `git worktree remove <path>` for clean removable worktrees, `git branch -d <branch>` before `-D`, `git remote prune origin` for stale tracking refs, and `git push origin --delete <branch>` only if explicitly approved.
- Stop if a command would affect an unapproved item, protected/current branch, dirty worktree, active process, open PR/task, or remote state not listed in the approval table.
- Re-run the relevant read-only audit commands and report what changed, what remains, and why.

Closeout:
- Record whether Beads/handoff/stage artifacts need updates after cleanup.
- Report `docs-reviewed: no-change-needed` unless cleanup changed durable project docs/state; if changed, report exactly what.
- Report `graph-reviewed: no-change-needed`; cleanup alone is not an accepted relevant integration or release boundary and does not rebuild Graphify.
