---
name: executing-plans
description: Use when executing a written implementation plan in a separate session
---

# Executing Plans

Execute the accepted plan as one continuous implementation stage, then accept
the cohesive result once.

## Process

1. Read the plan, repository instructions, current diff, and scope ledger.
2. Resolve only material contradictions or missing user-owned facts. Repository
   evidence and routine reversible defaults do not require confirmation.
3. Implement the complete plan in dependency order. Merge adjacent work that
   shares owner, subsystem, risk, rollback, and proof.
4. Use a focused diagnostic only when it helps unblock implementation.
   The plan's final acceptance owns the verification set.
5. Do not run per-task acceptance, review, package suites, closeout, or
   freshness-only checks.
6. After implementation and integration corrections are complete, run one
   risk-selected final acceptance set. Run the full configured suite once only
   at epic/release.
7. Use `superpowers:finishing-a-development-branch` when an integration choice
   remains.

Matching passing evidence may be reused when source, command, environment,
artifacts, and acceptance boundary are unchanged.

## Stop

Stop when the plan has a load-bearing contradiction, required ownership is
unclear, or the next step needs new destructive, live, external, or material
scope authority. A failed final check is not a reason to restart the plan:
batch the related fixes and rerun only failed or affected checks.
