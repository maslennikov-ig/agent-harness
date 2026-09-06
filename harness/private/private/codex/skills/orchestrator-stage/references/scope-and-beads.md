# Scope and Beads

Create or select a Beads task before medium/complex, staged, delegated, risky,
long, or handoff-prone work. A simple one-pass local change may skip it.

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

Before work inside a new stage, create one `orchestration-stage/v1` manifest
with acceptance owner/boundary, rollback boundary, worker ownership, status,
profile at creation, and bound stream artifacts.

A replan or material split requires `scope-preservation-ledger/v1`: exact-map
every stable acceptance criterion to a named larger stage, dependency, or gate
and bind the immutable criterion-set digest. A split additionally records one
allowed material boundary and evidence. Missing or renamed criteria block it.

Migration is `future_work_only`. Accepted history stays immutable; existing
Beads are not silently closed or reclassified. Grandfather only the recorded
legacy active stage.

Keep `.codex/handoff.md` current-state only and the project index
navigation-only. Put detailed accepted proof in stage artifacts and update
Beads whenever task truth changes.
