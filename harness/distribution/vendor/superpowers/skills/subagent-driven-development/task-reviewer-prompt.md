# Final Combined Reviewer Prompt Template

Use this template only at cohesive final task acceptance when changed risk
requires review and a reviewer subagent passes the material-benefit or explicit
independence gate. It is not a per-worker or per-plan-checkbox gate.

```
Subagent (general-purpose):
  description: "Review the cohesive completed delta"
  model: [MODEL]
  prompt: |
    Review the completed cohesive delta once through two lenses:
    requirements/correctness and implementation quality.

    ## Requirements
    [PLAN_OR_REQUIREMENTS]

    ## Changed scope and risk
    [CHANGED_SCOPE_AND_RISK]

    ## Review package
    [DIFF_FILE]

    ## Acceptance evidence
    [EVIDENCE_FILE]

    Read the supplied artifacts once. This review is read-only: do not mutate
    the checkout and do not rerun tests already represented by matching
    evidence. Inspect additional repository context only when a concrete
    changed-risk question requires it.

    Do this review yourself. Do not spawn another subagent or reviewer. If the
    evidence looks truncated or unreadable, re-read its stated path; report a
    genuine gap instead of rerunning the suite.

    If the requirements batch several files or same-shape edits, check every
    listed item against the diff. A listed change absent from the diff is a
    missing requirement even when the rest of the batch is clean.

    Report every finding, then let severity filter the result. For each:
    - severity: P0 | P1 | P2 | P3
    - confidence: high | medium | low
    - file:line
    - concrete failure case
    - concise remediation when it is not obvious

    Name missing evidence separately; do not convert absence of unrelated broad
    evidence into a code defect.

    ## Output

    ### Findings
    [ordered by severity, or "None"]

    ### Acceptance gaps
    [missing changed-risk proof, or "None"]

    ### Verdict
    [accept | correct one related finding batch | blocked by P0/P1]
```

Placeholders:

- `[MODEL]` — a model capable of the changed risk.
- `[PLAN_OR_REQUIREMENTS]` — accepted requirements or their file path.
- `[CHANGED_SCOPE_AND_RISK]` — touched scope, invariants, and review trigger.
- `[DIFF_FILE]` — cohesive base-to-head review package.
- `[EVIDENCE_FILE]` — current final acceptance evidence.
