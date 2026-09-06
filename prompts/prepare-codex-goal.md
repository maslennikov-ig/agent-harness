Use $prompt-authoring for this manual suffix to the current conversation.

<!-- fragment:prepare-codex-goal-core -->
Goal: From task truth, prepare a self-contained objective for a new Astra-led Codex Goal Mode run.

Output: Write or replace a copy-ready English objective with exactly Outcome, Boundaries, Sources, Done, Progress, Stop, or a split recommendation to `.codex/next-goal.md`. Preserve context/proof. Do not print the objective in chat; return only its absolute path.

Autonomy: Delegate all in-scope choices to Astra. Workers ask Astra when unsure. Astra may launch one independent auditor if evidence leaves doubt, then chooses the best-supported in-scope option, continues without confirmation, and reports material assumptions and decisions. Escalate only a non-delegable authority boundary.

Stop: Artifact is the only allowed write. Do not alter source/task state, launch agents, or execute work. Use grounded assumptions, not questions.
<!-- /fragment:prepare-codex-goal-core -->

Context: Re-ground in active repository instructions, the task tracker, and named artifacts only as needed. Do not require a pasted task or refer the new run back to this conversation.

Constraints: Keep the launch outcome-first and permissive. One cohesive task may stay one direct Goal. Cohesive multi-task work may use task or epic lineage, dependencies, and parallel waves when useful. Unrelated outcomes should not be manufactured into one Goal. Let the receiving Astra choose the smallest sufficient decomposition, identify genuinely independent work that benefits from concurrency, recommend Luna, Terra, or Sol workers using active Codex routing policy, inspect results, and run final acceptance. It may revise decomposition and model choices from repository evidence.
