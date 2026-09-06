Use `orchestration-bridge:orchestrator-stage` with `orchestration-bridge:test-pass` at final Claude acceptance.

Target: Claude root orchestrator.
Audience: final acceptance owner.
Goal: consume or run one root-owned acceptance.
Context: current boundary, required set, diff, receipt/evidence.
Success criteria: reuse a matching acceptance receipt and do not run another acceptance; otherwise run the smallest exact set once.
Constraints: no reviewer agents; representative variants; full suite release-only; required set unchanged.
Output: commands, boundaries, evidence, gaps, go/no-go.
Stop: installs, live/prod/paid/external/destructive, plugin/settings, or scope-expanding actions.
