# Information and Authorization Gates

Two independent gates: needing an answer is not needing permission; permission
does not supply intent.

## Gate 1 — information / intent

Inspect available context first. Ask only when the missing fact is owned by the
user or organization, two or more materially viable choices remain and no
evidence-backed option is clearly best, and the answer can materially change behavior,
acceptance, priority, scope, workflow, risk, cost, privacy, reliability, or
expensive rework. A technical default cannot replace user or organization intent.

Do not ask what repository truth, documentation, tools, or convention answer;
what cannot change the plan or acceptance; where one technical option clearly
dominates; or for status, ceremony, or cosmetics. If one option is clearly best
and in scope, record the decision and proceed; missing confirmation is not a
blocker when the gate did not qualify. A risk category alone does not require user approval: architecture,
data, public contract, user-visible, security, authorization, and scope risks
strengthen invariants and review.

Ask one highest-leverage question at a time in the user's language and plain
words. Say why it matters, recommend among 2–3 concrete options with visible
consequences, and accept free-form or "не знаю". If the user delegates, decide
from evidence, record the assumption, and proceed. Do not repeat answered
questions. Stop when intent is decision-complete and the rest is technical.
For fuzzy visible requests cover missing problem, behavior/examples,
failure/edges, priorities, unacceptable outcomes, non-goals, and acceptance.

## Gate 2 — authorization

Reversible work proceeds. Commits and ordinary push follow final acceptance and closeout.
An ordinary non-force push to an existing configured tracking branch is
preauthorized when fetch proves the remote is not ahead or diverged, target
ownership and worktree scope are safe, and repo policy allows it. Ask before
force-push, remote deletion, merge/deploy, production/live
mutation, destructive cleanup, paid calls, real-user messaging, secrets/access
changes, or material scope expansion. State the exact external or
hard-to-reverse action. Never phrase a product question as a permission request.

Remember only non-default authority for the current stage, with exact action,
target, bounds, expiry, and exclusions. It is never transitive. Do not ask again
while that exact authority remains current; changed identity or scope needs a
new decision.

Use one content-free readiness preflight only at a provider-write, live, deploy,
or production boundary. Reuse it for the same source, runtime, and provider
identity. Local work has no readiness preflight.

Superpowers remains mandatory when triggered. Focused risk-selected TDD may run
during implementation; mandatory acceptance, package, review, and freshness
defer to work-first routing. Interactive design/spec approval remains
conditional on the decision gate.
