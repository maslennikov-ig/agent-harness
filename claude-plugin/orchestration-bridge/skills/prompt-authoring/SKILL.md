---
name: prompt-authoring
description: "Use when drafting, reviewing, shortening, or repairing a background, portable, cross-runtime, or manual-handoff prompt for another agent."
---

# Claude Prompt Authoring

Use only for a durable or cross-boundary prompt another agent will run. Inline
same-session Agent prompts do not trigger this skill; use the four-field
contract below directly. Keep reusable workflow in skills and deterministic
interfaces.

## Routing

1. Select the destination runtime/profile and prompt kind, independently of
   the authoring runtime: Claude `fable-5.1`/`opus-5` or Codex `gpt-6-astra`.
2. Portable, background, cross-runtime, and manual-handoff prompts use
   Target/Audience, Goal, Success criteria, Context, Constraints, Output, and
   Stop, then run `orch-prompts prompt-check`.
   A Codex Goal Mode objective instead uses Outcome, Boundaries, Sources, Done,
   Progress, Stop and no prompt-check on the objective. Check that it names one
   durable outcome with a verifiable stop; otherwise recommend an ordinary
   task or a split. The `prepare-codex-goal` card owns its explicit delegation
   of in-scope choices and artifact-only handoff. It does not start the goal.
3. A native same-session Agent call uses exactly four contract fields and no
   prompt-check:
   `goal`, `write_zone` (`read-only` is valid), `verification`, and `stop`.
   Verification is root-owned unless this is an explicitly assigned final
   verification stream; otherwise write `none during work; root final
   acceptance`.
   Include the selected `docs-resolve` result only when the stream depends on
   external or version-sensitive behavior.
   No harness Agent hook is installed.
4. Keep only task-critical facts inline. Reference triggered skills, repository
   memory, docs, and agents instead of copying their procedures.
   Derive Done/verification from the requested outcome and existing evidence.
   Use the stage skill's verification routing; UI or risk labels alone do not
   introduce a full suite or UX proof package.
5. Ask for concise decisions and evidence, never hidden or internal reasoning.
   Where a prompt would otherwise leave user-visible behavior to the reader's
   guess, put the assumed `Given/When/Then` example in Success criteria. It
   replaces the guess; it is not a command or a variant matrix.
   Product variants such as language, theme, viewport, and state are context,
   not an automatic acceptance matrix; use representative cases unless a
   defect is dimension-specific.
6. If a worker/subagent creates a further prompt, apply the same routing:
   four fields locally, or this skill plus prompt-check across a boundary.

For read-only research/review, a single Markdown artifact may be the only allowed write when its artifact path is explicit.

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
fallback 6,000 before the kernel/model layers.

Skeleton:

```text
Target: Claude <profile> <role>
Audience: <background agent/manual launcher>
Goal: <finished outcome>
Success criteria:
- <observable result>
Context: <only context needed to act>
Constraints: <write zone, selected skills, docs limits>
Output: <behavior-first result, then supporting evidence>
Stop: <when to stop and ask/report>
```
