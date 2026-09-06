# Closeout and Delivery

Select one end path:

- simple read-only answer: respond directly;
- simple local file change: one final focused acceptance plus
  documentation-impact decision;
- medium single stream: closeout-lite;
- complex, staged, risky, or handoff-prone: full closeout. Delegation alone
  does not select this path.

Confirm the accepted diff/artifact, the one final acceptance result, remaining risks,
Beads/task truth, and worktree ownership. Record `docs-reviewed: updated` or
`docs-reviewed: no-change-needed` with a reason. For Graphify-enabled work,
record `graph-reviewed: used|updated|blocked|no-change-needed` with command
evidence or the bounded reason.

Repo-local acceptance runs once through `run_stage_closeout.py` with an explicit
level and exact task commands. Release uses only configured `release_commands`.
Closeout consumes that result; it does not choose or run a second set.

## Nontechnical acceptance packet

The user-facing final leads with observable behavior, not a diff; an internal
closeout artifact does not replace it. For medium/complex or behavior-changing
work, state what changed in user-visible terms, how the user can verify it,
which normal, failure, and edge scenarios were checked, known limitations,
residual risks, and unverified assumptions, and rollback/recovery when it
applies. Commands, tests, reviewer findings, and diffs are supporting evidence.
A simple change uses the compressed form: outcome, one verification sentence,
and any material limitation.

Ordinary commits and non-force push may proceed after final acceptance and
closeout when repository policy allows delivery. Before push, fetch and prove
the remote is not ahead or diverged, the tracking target is correct, and the
worktree contains no unrelated owner changes.

Ask before force-push, remote deletion, PR creation/merge, deploy,
production/live mutation, destructive cleanup, paid calls, real-user
messaging, or secrets/access changes.

Never force-delete a dirty worktree or unproven branch. Report unavailable
checks and explicit defers; do not relabel them as passed.
