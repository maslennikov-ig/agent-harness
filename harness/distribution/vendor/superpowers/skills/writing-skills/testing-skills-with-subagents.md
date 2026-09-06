# Optional independent skill evaluation

Use an independent agent only when a significant skill decision benefits from
behavioral evidence and the task authorizes the required tools and cost.
Ordinary metadata and deterministic wording corrections use proportionate
static checks or scenario inspection at final acceptance.

Give the evaluator a realistic user request, the candidate skill, and the
minimum raw artifacts needed to act. Keep the expected answer and proposed
fix out of its prompt. Use an isolated temporary workspace when writes are
part of the scenario, with an explicit write zone and authority boundary.

Assess the useful result: preserved intent, scope, correct sources, appropriate
verification, and honest uncertainty. Compare with an existing baseline when
available. A missing baseline is a limit on conclusions, not a reason to force
an expensive repeated model loop.

Fix a demonstrated problem; repeat only the affected scenario if the result is
still uncertain. Preserve valid working code and explicit user instructions.
Do not use pressure language, invented urgency, or automatic model runs to
force ritual compliance. Static checks do not prove future agent behavior.
