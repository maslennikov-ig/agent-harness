Use `orchestration-bridge:prompt-authoring` for this manual handoff.

<!-- fragment:prepare-codex-goal-core -->
Goal: From task truth, prepare a self-contained objective for a new Astra-led Codex Goal Mode run.

Output: Write or replace a copy-ready English objective with exactly Outcome, Boundaries, Sources, Done, Progress, Stop, or a split recommendation to `.codex/next-goal.md`. Preserve context/proof. Do not print the objective in chat; return only its absolute path.

Autonomy: Delegate all in-scope choices to Astra. Workers ask Astra when unsure. Astra may launch one independent auditor if evidence leaves doubt, then chooses the best-supported in-scope option, continues without confirmation, and reports material assumptions and decisions. Escalate only a non-delegable authority boundary.

Stop: Artifact is the only allowed write. Do not alter source/task state, launch agents, or execute work. Use grounded assumptions, not questions.
<!-- /fragment:prepare-codex-goal-core -->

Context: Re-ground from repository instructions, task tracker, and named artifacts; require no pasted task.

Constraints: Keep the launch outcome-first. One cohesive task may stay one direct Goal; recommend a split for unrelated outcomes. Receiving Astra chooses sufficient decomposition, identifies genuinely independent work worth concurrency, recommends Luna, Terra, or Sol workers under active routing policy, inspects results, and runs final acceptance.
