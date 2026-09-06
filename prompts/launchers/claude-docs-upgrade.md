Use `orchestration-bridge:dependency-docs-upgrade`.

Goal: verify Claude-side dependency/lockfile changes through one Docs Resolver call per affected dependency and use its reported fallback.

Must not forget: inspect exact old/new versions; derive lockfile-routed docs targets; run one `orch-prompts docs-resolve` call per affected dependency before fallback research; keep commands dry-run unless authorized.

Output: changed deps, L1 status, fallback need, proposed docs sync commands, verification evidence, docs-reviewed result.

Stop: ask before dependency install, lockfile mutation, external docs ingestion, plugin/settings changes, or live/prod checks.
