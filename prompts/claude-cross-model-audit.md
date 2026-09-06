Use `orchestration-bridge:orchestrator-stage` for a cross-model review.

Target: Claude Opus 5
Audience: independent auditor of work completed by ChatGPT/Codex.

Goal: audit the completed in-scope work independently from repository evidence, not from the claimed summary.
You are the one primary read-only reviewer; do not spawn an additional reviewer. Use the active delegation policy for role/model/effort.

## Начальная задача

[Paste the request, constraints, and acceptance criteria.]

## Выполненные задачи

[Paste changes, files, evidence, limits, and unfinished work.]

Context:

- Read nearest instructions, Git state/diff, changed files, tests, docs, and evidence. Claims navigate; repository bytes prove.

Success criteria:

<!-- fragment:review-quality-core -->
Map requirements→evidence. Review correctness/completeness, regressions, normal/failure/edge test gaps, reuse, architecture, and project two-level docs. For touched external/versioned behavior, run fresh `docs-resolve` L1/L2; compare implementation before verdict. Report severity/confidence/file:line/evidence/impact/fix, coverage, residual risk, verdict.
<!-- /fragment:review-quality-core -->

Constraints: report turn is read-only except documentation retrieval/cache. Read the diff and matching acceptance receipt when present; never rerun acceptance.

After report: ask local fix or original-model return prompt; wait. Local fix uses one bounded worker/focused red-green. Changed or unaccepted boundary gets one root acceptance; otherwise reuse the receipt. Never commission a second matching acceptance. Return prompt makes no source/config edits.

Output: the core report, then that one choice.

Stop: for the report turn, before edits, plugin/settings changes, commits, push/merge/deploy, deletion, external messages, paid calls, or wider scope. After the answer, follow the chosen path and its authority boundaries.
