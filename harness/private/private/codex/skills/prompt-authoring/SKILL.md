---
name: prompt-authoring
description: Use when drafting, reviewing, shortening, or repairing a Goal Mode objective or a background, portable, cross-runtime, or manual-handoff prompt for another agent or model.
---

# Prompt Authoring

Keep reusable workflow in skills and deterministic interfaces. Use this only
for Goal Mode, durable, background, cross-runtime, or manual-handoff prompts.
Native same-session spawned agents do not trigger this skill; use the compact
interface below directly.

## Contract

- Choose the destination runtime/profile, not the authoring runtime. A Claude
  author can prepare a Codex prompt and vice versa. Cards describe their author;
  the generated prompt describes its receiver.
- Native spawned-agent prompt: `goal`, `write zone`, `verification`, `stop`;
  no prompt-check.
  Verification is root-owned unless this is an explicitly assigned final
  verification stream; otherwise write `none during work; root final
  acceptance`.
  Include the selected `docs-resolve` result only when the stream depends on
  external or version-sensitive behavior.
  Add task reference, selected docs/skills/agent, and artifact path only when
  the stream needs them.
- Portable/cross-boundary prompt: Target/Audience, Goal, Success criteria,
  Context, Constraints, Output, Stop; run `orch-prompts prompt-check`.
- Goal Mode objective: Outcome, Boundaries, Sources, Done, Progress, Stop.
  First decide whether the work is one durable outcome with a verifiable stop.
  Done names the exact commands or artifacts that prove completion. Progress
  names the checkpoint, verified evidence, remaining work, and any blocker.
  Reference active rules instead of copying them; after resume or compaction,
  re-ground from named sources and current repository/task state.
- Reference repository truth and triggered skills instead of copying their
  rules. Ask for concise decisions and evidence, never internal reasoning.
- Derive Done/verification from the requested outcome and existing evidence.
  Use the stage skill's verification routing; do not insert a full suite or UX
  proof package merely because the task mentions UI, risk, or a release.
- Where a prompt would otherwise leave user-visible behavior to the reader's
  guess, put the assumed `Given/When/Then` example in Success criteria or Goal
  Done. It replaces the guess; it is not a command or a variant matrix.
- Product variants such as language, theme, viewport, and state are product
  context, not an automatic acceptance matrix. Request representative cases
  unless the defect is specific to one dimension.
- If a worker/subagent creates a further prompt, apply the same routing:
  four fields locally, or this skill plus prompt-check across a boundary.
- For read-only research/review, a single Markdown artifact may be the only allowed write when its artifact path is explicit; do not mutate source/config.

## Two-gate interaction

A prompt inherits the two independent gates from
`orchestrator-stage/references/autonomy-and-approvals.md`; state the trigger,
never the whole contract.

- Do not write a prompt that forbids questions outright or that requires
  confirmation at every step; both break the gates.

## Output shape

For user-visible or behavior-changing work, ask for a behavior-first result:
what changed in user-visible terms, how to verify it, which normal/failure/edge
scenarios were checked, limitations, and rollback when it applies. Commands,
tests, and diffs are supporting evidence. Simple mechanical work uses outcome,
one verification sentence, and any material limitation.

## Significant Finding Capture

Capture only a decision-affecting finding that a future agent/orchestrator
would otherwise lose. Record evidence, implication, confidence, and promotion target; exclude raw logs and unsupported guesses.

Budgets: launcher 1,000 characters; worker 3,000; review 4,500; portable
fallback 6,000 before kernel/model layers.
