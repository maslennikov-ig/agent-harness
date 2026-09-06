---
name: writing-plans
description: Use when a multi-step task needs a durable implementation plan before code; keep simple direct changes on a brief local checklist.
---

# Writing Implementation Plans

## Overview

Plan around cohesive, reviewable outcomes. A plan should reduce uncertainty and
handoff risk, not expand one change into dozens of ceremonial actions.

Simple direct changes do not need a standalone plan document. Use a short
working checklist, make the edit, and accept it once at the proper boundary.

For durable plans, save to
`docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md` unless project rules
specify another location.

## Cohesive task sizing

Each task is one cohesive acceptance boundary that may include decision,
contract, implementation, persistence/adapter work, consumer adoption, tests or
other proof, and documentation when they share owner, subsystem, risk, test
environment, rollback boundary, and acceptance proof.

Merge adjacent work by default. Split only for an unresolved public ownership
or contract boundary, a hard dependency, an independent rollback/migration
boundary, a distinct security/compliance risk, or external authorization.

Do not split a plan into 2-5 minute ceremony. Focused red-green TDD steps,
implementation, final acceptance, docs, and commit are parts of the cohesive
task, not separate tasks or review gates.

## Before writing

Inspect the project contract and relevant code. Record:

- goal and non-goals;
- acceptance criteria and their owning task;
- affected files and public interfaces;
- dependencies and material risk boundaries;
- any concrete uncertainty that needs a diagnostic before the next edit;
- final task and epic/release checks actually needed.

Every acceptance criterion maps to a task, dependency, or explicit gate.
Replanning preserves this ledger.

## Plan shape

```markdown
# [Feature] Implementation Plan

**Goal:** [accepted outcome]
**Approach:** [2–4 sentences]
**Non-goals:** [explicit exclusions]
**Spec:** [accepted spec/design path when one exists; executors read it too]

## Scope ledger
- [criterion] -> Task 1 / dependency / gate

### Task 1: [cohesive outcome]
**Files:** [exact paths]
**Boundary:** [owner, subsystem, rollback and proof]
**Interfaces:** [consumes / produces]
**Final verification:** [smallest meaningful set or existing evidence]

- [ ] Implement the complete cohesive change and its durable docs.
- [ ] Run the one final risk-selected acceptance set.
- [ ] Self-review the resulting diff and record acceptance evidence.
```

Include exact commands and signatures when they remove ambiguity. Do not paste
full implementations when repository patterns already answer the detail.

## Self-review

Check once:

1. Every acceptance criterion has an owner.
2. No task exists solely for a helper, proof, docs update, or settled decision.
3. Split reasons are material and recorded.
4. Diagnostics are optional; risk labels alone do not require a TDD cycle.
5. Broad verification is scheduled only at epic/release, not after local edits.

Fix gaps inline. Do not add a separate review round without a real risk trigger.

## Execution handoff

Keep execution with the owner who has context, or delegate for a concrete
benefit. Unavailable delegation does not block local work.
