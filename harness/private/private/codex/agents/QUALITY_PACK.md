# Codex Quality and Development Agent Pack

Source: local catalog `voltagent-codex-subagents`, manually vetted and adapted into `$CODEX_HOME/agents`.
This is a local adapted pack, not blind catalog promotion. Future updates from catalog-only sources require fresh vetting before replacement.

Policy:
- Prefer installed agents from this file before searching the catalog.
- Role lists are candidate pools. Select exactly one primary role for a stream;
  role, model, and effort follow the active `orchestrator-stage` delegation
  policy rather than a copied matrix here.
- For spawned `agent_type`, prefer the TOML `name` value; console lists may show hyphenated filename slugs for the same agents.
- Newly added TOML agents may require restarting/refreshing Codex before they appear as spawnable runtime roles.
- Use visible spawned Codex subagents only; do not use hidden inline delegation.
- Review roles are read-only by default.
- Implementation roles may write only inside the parent prompt write zone.
- Catalog-only agents remain lookup candidates until vetted and adapted.
- For external/versioned behavior, resolve it with `orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<API keywords>'` before relying on it. Purely local work records nothing.

## Routing and asset governance

- `skill_scout` - choose installed skills/agents before catalog when routing is unclear.
- `asset_vetter` - vet staged or catalog-only assets before promotion or installation.
- `docs_researcher` - fetch current official docs for version-sensitive APIs, libraries, CLIs, platforms, or model behavior.
- `docs_reviewer` - decide whether README/docs/ADR/project-index/handoff are stale after durable changes.

## Final quality review

A combined final review covers two lenses when changed risk requires review:
- correctness - bugs, regressions, security/privacy, missing tests, edge cases, verification gaps;
- improvement - better alternatives, simplicity, UX/API, maintainability, performance, accessibility, overbuilt/underbuilt areas.

Root may perform simple, quick review. Small verification uses zero subagents and consumes one root acceptance or a
matching receipt. Medium work has no reviewer by default. When changed risk or
an explicit review request requires substantive medium or complex review,
delegate one bounded reviewer stream: one primary combined read-only reviewer
covers both lenses, reads the diff and existing evidence, and never reruns
acceptance. Root integrates and adjudicates findings and owns acceptance.

For a high-risk category named by verification routing, use one independent
specialist reviewer at final acceptance. A second reviewer requires a distinct
documented risk boundary; never fan out merely because several roles look
relevant.

## Additional quality specialists

The roles below are candidates, not a launch list. Select one primary role for
the current stream.

- `reviewer` - PR-style correctness, security, behavior regression, and missing-test review.
- `code_health_reviewer` - maintainability, design clarity, risky implementation choices.
- `qa_expert` - risk-based test strategy, acceptance coverage, release confidence.
- `architect_reviewer` - architecture, boundaries, coupling, long-term maintainability.
- `security_auditor` - auth, permissions, secrets, input validation, infra/config exposure.
- `performance_engineer` - latency, hot paths, DB/query/rendering regressions, scalability.
- `accessibility_tester` - keyboard, focus, labels, ARIA, contrast, assistive tech behavior.
- `ui_ux_tester` - UI flows, error/empty states, visual issues, interaction failures.
- `api_designer` - API contracts, validation/error model, compatibility, idempotency.
- `postgres_pro` - Postgres schema, locking, indexes, migrations, operational behavior.
- `database_optimizer` - query plans, indexes, data access patterns, DB performance.
- `prompt_regression_tester` - prompt/model/tool workflow regressions and eval coverage.
- `responsible_ai_reviewer` - fairness, transparency, misuse risk, human oversight.
- `risk_manager` - product, operational, financial, compliance, and architecture risk.
- `docs_reviewer` - documentation freshness after structural, API/contract, migration, ops, or durable behavior changes.

## Core development specialists

- `backend_developer` - scoped backend implementation or backend bug fixes.
- `frontend_developer` - scoped frontend implementation or UI bug fixes.
- `frontend_specialist` - existing local frontend specialist for UI implementation or accepted UI fixes with browser evidence.
- `ui_fixer` - smallest safe patch for an already reproduced UI issue.
- `code_mapper` - read-only code path and ownership mapping before changes.
- `typescript_pro` - TypeScript types, interfaces, refactors, compiler-driven fixes.
- `python_pro` - Python runtime, packaging, typing, testing, framework-adjacent work.
- `debugger` - deep bug isolation across code paths, traces, runtime, failing tests.
- `error_detective` - logs, exceptions, stack traces, likely failure source.
- `refactoring_specialist` - low-risk behavior-preserving structural refactors.
- `tooling_engineer` - internal tooling, scripts, automation glue, workflow utilities.
- `build_engineer` - build graph, bundling, compiler pipeline, CI build stabilization.
- `dependency_manager` - dependency upgrades, package graph, version policy, library risk.
- `dx_optimizer` - setup time, local workflows, feedback loops, dev friction.
- `cli_developer` - CLI features, shell UX, argument parsing, command workflows.
- `documentation_engineer` - accepted docs writes: code-faithful technical docs, examples, and operator workflows.
- `db_migration_specialist` - existing DB/migration/data-integrity specialist.
- `deploy_specialist` - existing deploy/env/preview/runtime delivery specialist.
- `deployment_engineer` - release strategy, rollback, deploy sequencing, runtime safety for accepted fixes or bounded config work.
- `devops_engineer` - CI/CD, pipeline, release automation, environment config for accepted fixes or bounded config work.
- `ai_engineer` - model-backed app features, agent flows, evaluation hooks.
- `llm_architect` - prompts, tool use, retrieval, evaluation, multi-step LLM architecture.

## Review vs fix routing

For `review-fix`, route the first pass to read-only agents only. Use writable implementation roles only after the orchestrator accepts a finding and creates a bounded fix stream with a write zone.

Common review triggers:
- UI/frontend candidates: `ui_ux_tester`, `accessibility_tester`, `performance_engineer`, `code_health_reviewer`.
- DB/schema/query candidates: `postgres_pro`, `database_optimizer`, `api_designer`, `security_auditor` for RLS/auth boundaries.
- Deploy/CI/runtime candidates: `reviewer`, `security_auditor`, `risk_manager`, `qa_expert`; use writable deploy/devops roles only for accepted fixes.
- Prompt/agent/orchestration candidates: `prompt_regression_tester`, `llm_architect`, `risk_manager`, `asset_vetter` for new external assets.
- Docs: `docs_reviewer` for freshness review, `docs_researcher` for external facts, `documentation_engineer` only for accepted docs writes.

## Specialist search fallback

Search the catalog only when no installed agent fits, or when the task is clearly ultra-specific:
mobile, Rust, Swift, Kotlin, Java, Angular, Vue, Kubernetes, Terraform, Stripe/payments,
blockchain, M365, HIPAA/GDPR, scientific literature, SEO, or another narrow platform/domain.
