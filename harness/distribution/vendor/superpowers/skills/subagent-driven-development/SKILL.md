---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks in the current session
---

# Subagent-Driven Development

Root executes work it already holds the context for. Delegate a stream only
for a concrete parallel-latency, context-isolation, specialist, or
write-isolation benefit; root owns coordination, shared decisions,
integration, final acceptance, and delivery. If delegation is unavailable,
continue locally; unavailable subagents never block.

**Core principle:** delegate by benefit; integrate and accept once.

## Boundary

- The root owner keeps the scope ledger, shared decisions, integration, final
  acceptance, and delivery.
- A worker owns one coherent stream with a non-overlapping write zone and a
  report artifact. Do not create a fresh worker for each helper, file, test, or
  plan checkbox.
- A worker or reviewer completes its assigned stream itself and does not spawn
  another subagent. The root owns decomposition and every review seat.
- Workers self-review their stream. They may use a focused diagnostic
  when it unblocks implementation; risk labels add no test requirement.
- Worker completion does not trigger a task review, package suite, closeout, or
  fresh-evidence gate.
- Substantive medium/complex final review uses one bounded delegated reviewer.
  Root integrates findings and owns one final acceptance. Fan out only when
  each reviewer stream has a concrete benefit or an explicit independent-
  review risk; two lenses alone do not require two reviewers.

## Process

### 1. Prepare the cohesive stage

Read the plan, repository contract, current diff, and ownership state. Record:

- the accepted outcome and non-goals;
- each stream's write zone, inputs, outputs, and dependencies;
- optional diagnostics only where they would unblock implementation;
- the root-owned final acceptance set;
- material stop conditions.

If the plan names a spec, read it too. Treat the accepted spec as intent and
the plan as its implementation argument. Make routine reversible rulings from
repository evidence, record the decision and its cost if wrong, and continue.

Use an isolated worktree only when repository policy or write isolation needs
one. Do not pause for confirmation when repository evidence resolves the
choice. Ask one plain-language question only when the canonical information or
authority gate qualifies.

For a durable delegated plan, resolve its plan-scoped directory with
`scripts/sdd-workspace PLAN_FILE`; use `scripts/task-brief PLAN_FILE N` when a
worker needs one task extracted without pasting it through controller context.
Keep the ledger current-state only: stream owner, status, commit or diff,
evidence already produced, and blocker.
Generate `scripts/review-package PLAN_FILE BASE HEAD` only when the final risk-selected review actually runs.
Do not delete the workspace automatically.

### 2. Dispatch useful streams

Give each worker:

- one cohesive goal and explicit write zone;
- requirements or a brief path;
- known interfaces and dependencies;
- any explicitly assigned diagnostic or final verification target;
- a report path and concise status contract;
- stop rules for scope, ownership, destructive, live, and external actions.

Start safe independent streams together when doing so materially reduces
latency. Keep shared-state or dependent streams sequential. Do not add reviewer
workers merely for independence.

Batch small same-shape edits into one coherent worker stream. Split only when
the work needs distinct judgment, verification, ownership, or write isolation.

Template: [implementer-prompt.md](implementer-prompt.md)

### 3. Integrate worker returns

Read each report and inspect the owned delta. Resolve overlapping assumptions,
interface mismatches, and blockers at the root. Batch related corrections
before acceptance.

- `DONE`: integrate the stream.
- `DONE_WITH_CONCERNS`: resolve material concerns before acceptance; ledger
  non-blocking observations.
- `NEEDS_CONTEXT`: provide the missing fact and resume only that stream.
- `BLOCKED`: change context, capability, ownership, or the plan; do not repeat
  the same dispatch unchanged.

Rule on plan conflicts at the root when the accepted spec and repository truth
resolve them. Stop only when every path is a guess or the next step crosses an
ownership, destructive, live, external, security, or scope boundary.

Do not run a per-worker acceptance set or task review. Do not ask a worker to
rerun unchanged passing checks for a newer timestamp.

### 4. Accept once

After all implementation and integration corrections are complete:

1. Run the one root-owned risk-selected final acceptance set.
2. At epic/release, run the full configured suite once. Reuse matching passing
   evidence when source, command, environment, artifacts, and boundary match.
3. Run one combined final review only when changed risk requires it.
4. Record docs and graph decisions, then use
   `superpowers:finishing-a-development-branch` when integration choices remain.

## Final failures

When final acceptance or review finds problems:

- group related findings into one correction wave;
- fix the complete group;
- rerun only failed or affected checks;
- run the release set once after those checks are green only when a release
  claim requires it.

There is no automatic per-fix re-review. Use
[re-review-prompt.md](re-review-prompt.md) only for an unresolved P0/P1 or an
explicit independent-review requirement that remains distinct after the
correction. Otherwise the root owner adjudicates the delta and current
acceptance evidence.

## Model and context selection

Choose the least expensive model that can reliably own the stream:

- mechanical work with exact instructions: economical model;
- multi-file integration, debugging, or unfamiliar contracts: standard model;
- architecture, security, concurrency, migrations, or broad judgment: capable
  specialist.

Pass paths and compact artifacts instead of session history. A report contains
what changed, evidence already produced, files touched, decisions, and
concerns. Avoid repeated status narration.

## Stop

Stop and report when ownership overlaps, a public interface cannot be reconciled
from the accepted plan, a worker repeats the same blocker, or the next step
needs new destructive, live, external, or scope authority. Do not delete a
workspace or branch without the authority required by the active repository
contract.
