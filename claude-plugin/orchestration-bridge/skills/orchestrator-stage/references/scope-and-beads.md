# Scope and Beads

Create or select a Beads task before medium/complex, staged, delegated, risky,
long, or handoff-prone work. A simple one-pass local change may skip durable
tracking.

## Task authoring

A Beads task is a compact outcome contract: its title names the outcome; its
description gives only the problem context and desired end state; its acceptance
criteria name observable evidence; and its remaining fields record only material
boundaries, dependencies, and settled decisions. Keep implementation method,
model or worker routing, and inherited workflow rules in the launch prompt unless
the task has already settled one as a real constraint.

Beads owns task status, dependencies, decisions, and accepted history. Query
only the selected goal lineage; do not copy the full backlog into prompts,
handoff, or project index.

After a successful `bd create`, `bd update`, or `bd close`, a repository
enrolled in GitHub sync resolves the console through
`${ORCHESTRATION_CONSOLE_ROOT:-${AGENTS_HOME:-$HOME/.agents}/orchestration-console}`
and invokes its executable `scripts/github_sync.sh --trigger --bead <ID>
<repo>` exactly once when the required GitHub authentication is available. If
the repository is not enrolled, authentication is absent, or the script is not
installed, record `GitHub sync: skipped - <reason>` and keep the local Beads
operation authoritative. Never invent or download a missing sync script. The
trigger durably coalesces repeated work; it does not wait for network
convergence. Never edit or close the GitHub issue separately. GitHub discovery
may import a missing task, but it never changes an existing linked Bead; Beads
owns that link's open/closed state.

Before streams inside a new stage, record one stage manifest with its
acceptance owner, acceptance boundary ID, rollback boundary, worker ownership,
and current status. Returned artifacts bind to that manifest.

During replanning, use `scope-preservation-ledger/v1`: map every stable
acceptance criterion to a larger stage, dependency, or explicit gate and bind
the criterion-set digest. A material split records one allowed boundary and its
evidence. Missing mappings block the replan.

Migration is `future_work_only`. Keep accepted history immutable, do not
silently close existing Beads, and grandfather at most the already recorded
legacy active stage.

Keep `.codex/handoff.md` current-state only. Put detailed accepted evidence in
the stage artifact and update Beads when task truth changes.
