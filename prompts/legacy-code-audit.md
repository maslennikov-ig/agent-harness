Target: Codex/Claude orchestrator using selected runtime/profile overlays.
Audience: agent launched from the orchestration panel.

Goal: run a read-only legacy/dead-code audit and produce an evidence-backed deletion decision report. Find removable files, exports, dependencies, assets, feature-flag paths, and modules; do not delete or edit anything.

Success criteria:
- Classify every candidate as `safe-delete-candidate`, `needs-decision`, `keep`, or `blocked`.
- `safe-delete-candidate` requires reachability proof, config/build/runtime/export checks, no generated/migration/public-API risk, and adversarial challenge.

Context:
- Read repo rules, orchestration state, Beads, package/lock/build/test config, and Graphify report if configured.
- Preserve behavior, keep public APIs stable, trace from real entrypoints, inspect config/build/deploy/test references, and require `file:line` proof.
- Prefer repo/stack tools: `rg`, Graphify, Knip/depcheck/ts-prune, ruff/vulture, and cargo/go/java equivalents.

Constraints:
- Read-only. No deletion, dependency removal, refactor, config mutation, process kill, remote mutation, or destructive cleanup.
- Create/select a Beads task before delegation or if the audit may last more than 15 minutes.
- Follow the kernel's documentation decision before relying on current tool behavior.
- Keep one shared workflow; profile overlays adapt Codex GPT, Fable, and Opus style.

Parallel plan:
- Delegate an audit stream when it has a concrete parallel, context-isolation, specialist, or write-isolation benefit; otherwise audit directly. The root retains coordination, shared decisions, integration, final acceptance, and delivery.
- Launch multiple eligible streams together only when the stage gate records concrete parallel latency, context isolation, specialist capability, or write isolation; independence alone is insufficient, and coupled streams stay sequential.
- Agent shortlist: Codex should consider `code_mapper`, `dependency_manager`, `correctness_reviewer`, `improvement_reviewer`, and `security_auditor`; Claude should inspect `/agents` first, then use visible code-map/dependency/security agents or fallback to `worker`, `correctness-reviewer`, and `improvement-reviewer`.

Method:
- Inventory entrypoints: routes, APIs, CLIs, jobs, migrations/seeds, tests, scripts, package exports, deploy hooks, generated assets.
- Trace imports/calls/usages; check dynamic usage such as reflection, registries, plugins, string dispatch, env gates, feature flags, templates, and webhooks.
- Treat coverage gaps and unused-tool output as candidates, not proof.

Output:
- Summary counts by classification and area.
- Table: candidate, path/symbol, area, evidence, counter-evidence, risk, verification command, classification, confidence, next action.
- Sections: Safe delete candidates, Needs discussion, Keep, Blocked/unknown, Tooling gaps, Recommended deletion batches.
- Approval request with numbered deletion batches, risks, and verification commands.
- Beads/docs/handoff impacts, `docs-reviewed`, `graph-reviewed`.

Stop:
- Ask before classifying as safe anything touching auth/security/privacy, billing, data/migrations, public API/package exports, deploy/runtime, generated code, external integrations, or feature flags without owner context.
- Do not rely on one LLM conclusion or one static-analysis result for deletion confidence.
