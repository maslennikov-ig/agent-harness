Use `orchestration-bridge:orchestrator-stage`.
Target: root orchestrator.
Audience: selected reviewer; fix worker only for accepted findings.
Goal: review final diff; fix confirmed in-scope findings.
Context: requirements, final diff, docs, existing evidence.
Success criteria:
Use one primary read-only reviewer for both lenses; delegation policy owns role/model/effort.
<!-- fragment:review-quality-core -->
Map requirements→evidence. Review correctness/completeness, regressions, normal/failure/edge test gaps, reuse, architecture, and project two-level docs. For touched external/versioned behavior, run fresh `docs-resolve` L1/L2; compare implementation before verdict. Report severity/confidence/file:line/evidence/impact/fix, coverage, residual risk, verdict.
<!-- /fragment:review-quality-core -->
Constraints:
Reuse a matching acceptance receipt when present; reviewer never reruns acceptance. Fix with one bounded worker/focused red-green. Changed or unaccepted boundary gets one root acceptance; otherwise reuse. Never commission a second matching acceptance.
Output: findings, fixes, receipt/evidence, defers.
Stop: scope, ownership, or authority boundary.
