Use $orchestrator-stage for dependency + docs upgrade review; use $task-router only as its conditional docs/skills routing substep.

Goal: verify dependency/lockfile changes through one Docs Resolver call per affected dependency and use its reported fallback.

Must not forget: inspect lockfile-routed versions; run one `orch-prompts docs-resolve` call per affected dependency before fallback research; do not mutate lockfiles opportunistically; record install/add commands separately from execution.

Output: changed deps, L1 status, fallback need, proposed docs sync commands, verification evidence, docs-reviewed result.

Stop: ask before dependency install, lockfile mutation, package upgrades, external docs ingestion, or live/prod checks.
