Use $orchestrator-stage.
Goal: cross-model audit as the one primary read-only reviewer; do not spawn an additional reviewer.
<!-- fragment:review-quality-core -->
Map requirements→evidence. Review correctness/completeness, regressions, normal/failure/edge test gaps, reuse, architecture, and project two-level docs. For touched external/versioned behavior, run fresh `docs-resolve` L1/L2; compare implementation before verdict. Report severity/confidence/file:line/evidence/impact/fix, coverage, residual risk, verdict.
<!-- /fragment:review-quality-core -->
Read diff and matching acceptance receipt when present; never rerun acceptance. Ask local fix or original-model return prompt; wait. Fix via one bounded worker/focused red-green. Changed/unaccepted boundary gets one root acceptance; otherwise reuse. Never commission a second matching acceptance. Return prompt: no source/config edits.
Output: report/choice
Stop: report turn only.
