---
name: test-pass
description: "Use when Claude Code CLI work is ready for one root-owned final acceptance set or explicit epic/release verification."
---

# Claude Test Pass

Use only at final task acceptance or final epic/release acceptance. It is not an
inner-loop or per-correction workflow.

## Cadence

- Inner loop: do not invoke this skill. Optional narrow development commands are owned by `orchestrator-stage` verification routing.
- Final task acceptance: the root runs one explicit set after implementation and corrections are complete.
- Choose the smallest commands that prove the changed behavior. Add a check only when it covers a distinct touched boundary.
- Product variants use representative combinations unless the defect is dimension-specific; do not build a Cartesian matrix.
- Final epic/release acceptance: run only the configured release commands once. Review docs/Graphify only when their files or durable contracts were affected.
- If final checks fail, batch fixes and rerun failed/affected checks. Repeat the whole release set only when its contract or invalidated shared inputs require it; retain valid passing evidence.

1. Inspect repo truth: `AGENTS.md`, `CLAUDE.md`, README, package/build files, scripts, CI hints, Beads, stage/handoff, and current diff.
2. Name the exact commands and the distinct changed boundary each command proves.
3. For version-sensitive tooling or platform behavior, run `orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<API keywords>'` once and use its reported fallback.
4. Prefer repo-defined commands. Make no persistent dependency or lockfile changes unless explicitly in scope; do not invent a framework.
5. For Node suites that can retain timers, sockets, workers, or children, use the repo's bounded Node test runner; do not use `force-exit` to hide lifecycle leaks.
6. For browser checks and UX proof packages, use the UI/UX decision in
   `orchestrator-stage/references/verification-routing.md`. UI scope alone
   does not require either.
7. Keep final acceptance root-owned. Specialists inspect existing evidence
   unless final verification itself is their explicitly assigned stream.

Report:
- exact commands and the distinct boundary each proves
- commands run and pass/fail evidence
- defects and impact
- skipped or blocked checks with exact reason
- go/no-go recommendation
- `docs-reviewed` result
- `graph-reviewed` result when Graphify is configured

Perform in-scope reversible local changes required by the requested verification without a separate confirmation. Make no persistent dependency or lockfile changes unless explicitly in scope. Ask when continuation needs new trust, cost, live-system, destructive, or scope authority, such as a package source, paid/external service, live/prod test, destructive cleanup, plugin/settings scope expansion, or CI/deploy mutation.
