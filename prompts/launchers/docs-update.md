Use $orchestrator-stage for a Codex docs freshness pass; use $task-router only as its conditional docs/skills routing substep and finish with $orchestration-closeout.

Goal: check whether README/docs/ADR/project-index/handoff match changed behavior, APIs, verification commands, architecture, deploy/runtime notes, and current stage truth.

Must not forget: use Docs Resolver for current dependency/API behavior before fallback research; use docs_reviewer only when structural/API/deploy/runtime docs may be stale; keep docs updates minimal.

Output: docs changed or no-change-needed with concrete reason, files/sections reviewed, verification evidence, docs-reviewed result, graph-reviewed if configured.

Stop: ask before broad rewrites, public behavior changes, remote/live actions, or replacing project-specific operator notes.
