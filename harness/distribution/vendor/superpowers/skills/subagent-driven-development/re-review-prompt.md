# Residual High-Risk Finding Audit Template

This is not a routine re-review step. Use it only when a final correction leaves
an unresolved P0/P1 question or the accepted risk contract explicitly requires
an independent post-fix verdict.

```
Subagent (general-purpose):
  description: "Audit residual high-risk findings"
  model: [MODEL]
  prompt: |
    Audit only the named final-review findings against the correction delta.

    ## Requirements
    [PLAN_OR_REQUIREMENTS]

    ## Findings to audit
    [FINDINGS]

    ## Correction package
    [DIFF_FILE]

    ## Current affected-check evidence
    [EVIDENCE_FILE]

    This audit is read-only. Do not rerun tests and do not broaden into a new
    whole-branch review. For every named finding, return:
    - ADDRESSED | OPEN | CANNOT VERIFY
    - confidence
    - file:line
    - concrete remaining failure case, if any

    Report new P0/P1 breakage only when it is introduced by the correction
    delta. Lower-severity observations do not create another loop.

    Do this audit yourself. Do not spawn another subagent or reviewer. If the
    supplied evidence is truncated or unreadable, re-read its stated path;
    report a genuine evidence gap instead of rerunning the suite.

    ## Verdict
    [high-risk findings closed | explicit blocker remains]
```

Placeholders:

- `[MODEL]` — model selected for the distinct high-risk lens.
- `[PLAN_OR_REQUIREMENTS]` — accepted requirements.
- `[FINDINGS]` — only the unresolved P0/P1 or independence-bound findings.
- `[DIFF_FILE]` — final correction delta.
- `[EVIDENCE_FILE]` — failed/affected checks rerun after the correction.
