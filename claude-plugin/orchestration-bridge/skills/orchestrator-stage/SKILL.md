---
name: orchestrator-stage
description: "Use when medium or complex Claude Code work needs orchestration, staged delivery, bounded delegation, or risk-based verification; final closeout uses the mutually exclusive closeout skill."
---

# Claude Orchestrator Stage

Deliver one cohesive outcome with the smallest workflow that preserves scope,
ownership, and acceptance evidence.

## Start

1. Read repository `AGENTS.md`/`CLAUDE.md`, git state, and the selected task
   truth. Apply `references/autonomy-and-approvals.md` for its two independent
   interaction gates.
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
| stage creation, replanning, level, cost anomaly | `references/stage-lifecycle-and-sizing.md` |
| subagent, worktree, reviewer, parallel stream | `references/delegation-and-isolation.md` |
| Beads, manifest, scope ledger, handoff | `references/scope-and-beads.md` |
| dependency docs, Graphify, design routing | `references/docs-and-graphify.md` |
| work-first cadence, final acceptance, evidence reuse, risk review | `references/verification-routing.md` |
| acceptance, delivery, cleanup, docs/graph result | `references/closeout-and-delivery.md` |

Do not load every reference pre-emptively. One scenario should normally need
one reference; load a second only when it crosses a real boundary.

After compaction, a reference loaded earlier is not evidence that this task
made the kernel's documentation decision.

## Execution contract

- Keep one active implementation stage for one cohesive acceptance boundary.
  Decision, contract, implementation, adapter/persistence, consumer adoption,
  tests, proof, and docs belong together when ownership and rollback align.
- Root executes work it already holds the context for, including medium work.
  Delegate a stream when it has a concrete benefit: `parallel_latency`,
  `context_isolation`, `specialist_capability`, or `write_isolation`. If
  delegation is unavailable, continue locally. Root owns coordination, shared
  decisions, integration, final acceptance, and delivery; the delegation
  reference owns stream boundaries and safe parallel launch.
- Apply the relevant Superpowers process skill after routing, specialized by
  `references/verification-routing.md`: implementation is work-first and
  mandatory verification/review starts only at final task acceptance.
- Work from current evidence. If two progress checkpoints contain no material
  change, interrupt or replan instead of waiting.
- If you are about to guess at ambiguous, stateful, or failure-sensitive
  user-visible behavior, write the one `Given/When/Then` example you are
  assuming instead of guessing silently; it is not a step or a variant matrix.
- For user-visible medium/complex work, build the smallest end-to-end slice
  first when later work would amplify a wrong product assumption, and present
  it as observable behavior: runnable flow, copyable command and
  expected output, example request/response with a failure case, or a
  plain-language trace. Screenshots are optional when useful to the decision.
  Recording the slice does not pause implementation; wait
  only when it exposes an unresolved user-owned decision that separately
  qualifies under the intent gate. Skip the slice for a purely internal
  refactor whose observable contract is already fixed.
- Claim acceptance only after the one root-owned explicit set and matching
  closeout. Update task truth before final delivery. The user-facing final
  leads with observable behavior and how to verify it; see
  `references/closeout-and-delivery.md` for the acceptance packet.

Stop only for a question qualified by the autonomy reference, missing ownership
that cannot be recovered safely, or a real authorization boundary.
