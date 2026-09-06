---
name: orchestration-closeout
description: "Use when a Codex stage or task is ready for final verification, documentation/graph review, delivery, and cleanup."
---

# Orchestration Closeout

Close the existing acceptance boundary; never create a helper, proof, docs, or
graph-only micro-stage.
Keep `inner_loop`, `slice_acceptance`, `integration`, and `release` evidence
distinct.

## Path

- Simple local change: focused proof plus documentation-impact decision.
- Medium single stream: `closeout-lite`.
- Complex, staged, risky, or handoff-prone work: full closeout. Delegation alone
  does not select this path.

For `closeout-lite`, quote the narrow command and pass/fail result, update the
Beads task when one exists, record `docs-reviewed`, and `graph-reviewed` when
the repo enables Graphify.

For full closeout:

1. Reconcile the accepted diff/artifacts, scope ledger, task truth, remaining
   risk, and worktree ownership.
2. Use the root-owned `run_stage_closeout.py` result as the single acceptance
   result. Task acceptance passes exact commands; release uses only configured
   `release_commands`. Reuse the matching receipt and do not run another set.
3. Promote each durable significant finding to Beads, docs/research, AGENTS, a
   skill, prompt, or ADR. Keep transient and stage-local findings stage-local.
4. Record `docs-reviewed: updated|no-change-needed` with a reason; for a
   dependency-lockfile diff append `; documentation-decision: <the task's
   decision>` to the same line. For an
   enabled local graph, keep refresh read-only until durable relevant changes
   reach an accepted relevant integration or release boundary and are safe.
   Otherwise record `graph-reviewed: blocked|no-change-needed`.
5. Update handoff/project index only when current truth or stable entrypoints
   changed. Report explicit defers; unavailable checks are not passes.

When closeout changes task state, wait until its delegated writers have
finished and perform the canonical reread. After a successful `bd close`, a
repository enrolled in GitHub sync resolves the console through
`${ORCHESTRATION_CONSOLE_ROOT:-${AGENTS_HOME:-$HOME/.agents}/orchestration-console}`
and invokes its executable `scripts/github_sync.sh --trigger --bead <ID>
<repo>` exactly once when the required GitHub authentication is available. If
the repository is not enrolled, authentication is absent, or the script is not
installed, record `GitHub sync: skipped - <reason>` and keep the local Beads
close authoritative. Never invent or download a missing sync script. Do not
close the GitHub issue separately; the bounded trigger coalesces and retries
reconciliation from Beads.

Ordinary commit and ordinary non-force push to an existing configured tracking
branch may proceed after final acceptance and closeout under repository
policy or current user authorization. Fetch first and prove the remote is not
ahead or diverged, the target is correct, and no unrelated owner changes are
included. Ask before PR/merge, force-push, remote deletion, deploy,
production/live mutation, paid calls, real-user messaging, secrets/access
changes, destructive cleanup, or material scope expansion.

Never force-delete a dirty worktree or unproven branch. For delegated work,
inspect only exact task-owned runtime tails; never terminate by broad process
name. Resolve the exact PID/PGID before any termination.
