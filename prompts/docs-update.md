Use $orchestrator-stage for a documentation review/update pass.

Goal: make project documentation match the current code, stage state, and user-facing behavior without creating bulky or aspirational docs.

Route first:
- Read repo rules, `.codex/project-index.md`, `.codex/handoff.md`, relevant stage summaries/artifacts, Beads state, README/docs/ADRs/runbooks, relevant diffs, and Graphify report when configured.
- Use `docs_reviewer` for read-only freshness review.
- Before claims about an external API, library, CLI, platform, or model, run `orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<API keywords>'` once and use its reported fallback.
- Use `documentation_engineer` only for accepted docs writes with a bounded write zone.
- Agent shortlist: `docs_reviewer` for freshness, `docs_researcher` for current external facts, and `documentation_engineer` only for accepted docs writes.

<!-- fragment:docs-trigger-matrix -->
Docs trigger matrix:
- User-facing behavior/workflows changed -> README, help/operator/user docs, examples.
- API/contracts/schema/env changed -> API docs, examples, `.env` docs, contract notes.
- Migration/data/deploy/runtime changed -> migration notes, runbook, rollback/smoke steps.
<!-- /fragment:docs-trigger-matrix -->
- Architecture/module boundaries/entrypoints changed -> project-index, ADR/architecture notes.
- Verification commands changed -> README/project-index/handoff commands.
- Current stage truth changed -> handoff and stage summary only; do not turn handoff into long-term docs.

<!-- fragment:docs-update-rules-verification -->
Rules:
- Keep docs code-faithful, compact, and useful to the next operator or developer.
- Prefer updating the smallest existing file/section; create new docs only when there is a durable reader and no good existing home.
- Include exact commands, paths, env names, and limitations when they matter.
- Separate confirmed facts from inference. Do not document planned behavior as shipped behavior.
- Do not touch unrelated docs or reformat broad files.

Verification:
- Check links/paths/commands you changed where practical.
- Run repo docs/lint/build checks when available; otherwise explain why no docs-specific check exists.
- Report `docs-reviewed: updated - <what changed>` or `docs-reviewed: no-change-needed - <reason>`.
<!-- /fragment:docs-update-rules-verification -->
- For Graphify-enabled repos, docs/architecture/durable workflow changes make the next accepted relevant integration or release boundary eligible for refresh; a localized docs fix records `graph-reviewed: no-change-needed` instead of rebuilding.

<!-- fragment:docs-update-stop-output -->
Stop rules:
- Stop before broad docs rewrites, publishing, or changing project-specific operational rules without explicit approval.
- Stop if code truth and docs truth conflict and cannot be resolved from local evidence.

Output:
- Mode: reviewed-no-change or updated.
- Files reviewed and files changed.
- Confirmed facts vs inferences.
- Verification evidence or blocked checks.
- Remaining docs gaps, if any, with owner/next action.
<!-- /fragment:docs-update-stop-output -->
