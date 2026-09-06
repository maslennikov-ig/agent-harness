<!-- orchestration-setup: token-efficiency/v1 -->
## Orchestration Defaults

- Route medium or complex work through `orchestrator-stage`; add parallel streams only for a recorded material benefit.
- Native Codex spawns explicitly use `fork_turns="none"` by default. Any non-`none` override needs a task-specific rationale and must keep essential facts reachable through the nearest `AGENTS.md`, the selected Beads goal, or an exact existing reference.
- Spawn prompts contain only Goal, Write zone, Verification, and Stop. Reference current sources; do not copy transcript history or reusable rules.
- Coalesce routine progress. Always surface blockers, decisions, material artifacts, the final result, and platform heartbeats.
- Prefer bounded summarized tool output with an explicit truncation signal. Expand output only for a recorded task-specific reason.
- Workers run only assigned focused RED/GREEN checks. Root owns one final acceptance; the full suite is epic/release-only.
- Reuse the model routes in `orchestrator-stage/references/delegation-and-isolation.md`; do not restate them here.
