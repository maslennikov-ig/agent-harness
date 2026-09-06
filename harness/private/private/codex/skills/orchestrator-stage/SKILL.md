---
name: orchestrator-stage
description: "Use when medium or complex work needs engineering orchestration, staged delivery, bounded subagents, or risk-based verification; final closeout uses the mutually exclusive orchestration-closeout skill."
---

# Orchestrator Stage

Deliver one cohesive outcome with the smallest workflow that preserves scope,
ownership, and acceptance evidence.

## Start

1. Read repository `AGENTS.md`, git state, and selected task truth. Apply
   `references/autonomy-and-approvals.md` for its two independent interaction
   gates.
2. Classify:
   - simple: one obvious local result; execute directly and accept it once;
   - medium: one bounded cohesive result and one final
     task-acceptance/`closeout-lite` pass;
   - complex: cross-boundary, staged, risky, or handoff-prone work requiring
     coordinated delivery.
   Execution ownership may be root or delegated by concrete benefit;
   classification does not require a subagent count.
3. Load only the next relevant reference:

| Trigger | Load |
|---|---|
| stage creation, replanning, lifecycle level, cost anomaly | `references/stage-lifecycle-and-sizing.md` |
| subagent, worktree, reviewer, parallel stream | `references/delegation-and-isolation.md` |
| Beads, manifest, scope ledger, handoff | `references/scope-and-beads.md` |
| dependency docs, Graphify, design routing | `references/docs-and-graphify.md` |
| work-first cadence, final acceptance, evidence reuse, risk review | `references/verification-routing.md` |
| acceptance, delivery, cleanup, docs/graph result | `references/closeout-and-delivery.md` |

Do not pre-load every reference. One scenario should normally need one; load a
second only when it crosses a real boundary.

After compaction, a reference loaded earlier is not evidence that this task
made the kernel's documentation decision.

## Execution contract

- Keep one implementation stage per cohesive acceptance boundary. Keep decision,
  contract, implementation, consumers, proof, and docs together when ownership
  and rollback align.
- Root executes work it already holds the context for, including medium work.
  Delegate a stream when it has a concrete benefit: `parallel_latency`,
  `context_isolation`, `specialist_capability`, or `write_isolation`. If
  delegation is unavailable, continue locally. Root owns coordination, shared
  decisions, integration, final acceptance, and delivery; the delegation
  reference owns stream boundaries and safe parallel launch.
- Apply the relevant Superpowers process skill after routing, specialized by
  `references/verification-routing.md`: implementation is work-first and
  mandatory verification/review starts only at final task acceptance.
- Work from current evidence. Two checkpoints without a material artifact,
  diff, result digest, or blocker change end the wait and trigger a replan.
- If you are about to guess at ambiguous, stateful, or failure-sensitive
  user-visible behavior, write the one `Given/When/Then` example you are
  assuming instead of guessing silently; it is not a step or a variant matrix.
- For user-visible medium/complex work, build the smallest end-to-end slice
  first when it prevents amplifying a wrong assumption. Use a runnable flow, command/output, request/response, or plain trace.
  A screenshot is optional when it actually helps the decision. Keep
  working; wait only for an unresolved user-owned decision under the intent
  gate. Skip a purely internal refactor with a fixed observable contract.
- One cohesive change that lands as a single commit is `inner_loop`: no
  manifest, no stage directory, no per-task acceptance file. Its acceptance is
  one line in the handoff.
- From `slice_acceptance` up, in a repo initialized by `orchestration-setup`,
  stage readiness and stream acceptance are deterministic:
  `check_stage_ready.py` against the tracked `stage-manifest.json`,
  `validate_artifact.py` for returned stream artifacts, and
  `record_stage_telemetry.py --sizing-diagnostic` for sizing findings.
- Accept only after one root-owned explicit set, matching closeout, and updated
  task truth. Lead the final with observable behavior and verification; the
  acceptance packet is in `references/closeout-and-delivery.md`.

Stop only for a question qualified by the autonomy reference, unrecoverable
ownership ambiguity, or a real authorization boundary.
