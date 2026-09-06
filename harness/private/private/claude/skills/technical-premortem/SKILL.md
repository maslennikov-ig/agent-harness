---
name: technical-premortem
description: Use when a planned technical change crosses a material risk boundary before implementation, especially data or migrations, auth or tenancy, security, concurrency, retries or idempotency, public contracts, deployment or runtime behavior, irreversible operations, or unknown consumers.
---

# Technical Premortem

Assume the planned change was merged, deployed, and failed. Work backward from
that outcome to expose evidence-backed failure mechanisms before implementation.
This complements planning, TDD, and review; it does not replace them.

## Trigger gate

Run it when the settled plan crosses or materially changes at least one boundary:

- persistent data, schema, migration, retention, or backfill;
- authentication, authorization, tenancy, secrets, or other security behavior;
- concurrency, queues, retries, ordering, locking, or idempotency;
- public API, event, type, file-format, or cross-service contract;
- deployment order, runtime configuration, infrastructure, or recovery;
- irreversible action, production mutation, or unknown consumers/blast radius.

An explicit user request also runs the skill.

Skip by default for documentation, copy, cosmetic changes, mechanical renames,
generated output, and low-risk non-behavioral configuration. Skip repeated
inner-loop use when the risk boundary is unchanged.

Rerun only if the plan changes a contract, data path, consumer set, deployment
order, recovery strategy, or an earlier assumption. Do not rerun merely because
implementation started.

## 1. Build the evidence map

Inspect the plan and available repository evidence first. Record:

`change -> direct dependents -> indirect consumers -> shared state/resources`

Include code, data, APIs, jobs, caches, sessions, queues, configuration, rollout,
and operators where relevant. Distinguish facts from assumptions. If a material
gap remains after safe lookups, mark it as an assumption gap and ask only
questions whose answers can change the verdict. Never invent project structure.

## 2. Reconstruct the failure

Investigate all four paths:

1. The intended behavior failed: logic, data shape, edge case, or invalid premise.
2. A neighbor regressed: hidden consumer, side effect, or implicit contract.
3. The system degraded silently: performance, security, observability,
   maintainability, cost, or developer experience.
4. Harm appeared later: production scale, load, partial rollout, delayed job, or
   rollback/recovery interaction.

Scan only relevant surfaces, not a quota: correctness and coupling; contracts,
data, and migrations; performance, security, reliability, and concurrency;
observability, deployment, recovery, and maintainability.

Always include **Executor error**: ambiguous instructions, hallucinated APIs,
unnecessary file changes, specification drift, unsafe assumptions, or skipped
verification.

## 3. Classify and decide

Use two independent axes for every scenario:

- **Evidence:** `confirmed` by inspected facts; `plausible` with a concrete
  mechanism but an unverified premise; `unsupported` speculation.
- **Disposition:** `block`, `preflight`, `monitor`, or `dismiss`.

Only a confirmed risk, or a plausible risk with a concrete mechanism and
material impact, may block. An unsupported hypothesis cannot block; convert it
to a bounded lookup or dismiss it. Do not inflate risk counts.

For every retained scenario state the observable symptom, affected surface,
detection signal, mitigation, and owner/check. A blocking risk without a
detection path creates a separate observability gap.

## 4. Prove recovery

Choose the safest evidence-backed recovery path: code/config rollback, data
restore, compensation, or roll-forward. State the trigger, exact sequence,
expected time, and treatment of data, caches, queues, and partially completed
work.

Lack of a simple rollback is not automatically fatal. It is a blocker when no
tested restore, compensation, or roll-forward path keeps the relevant invariant
safe. Flag any hard-to-reverse action that needs explicit authorization.

## Output contract

```markdown
# Technical Premortem: <change>
Verdict: GO | GO WITH CONDITIONS | REPLAN | BLOCKED
Scope: <affected code/contracts/data/runtime>
Reversibility: <strategy and confidence>

## Blast radius
<change -> dependents -> consumers -> shared state>

## Risk register
| Failure symptom | Evidence | Mechanism / affected surface | Detection | Mitigation | Disposition | Owner / check |

## Blocking findings
<evidence, violated invariant, preflight check, required test/guard>

## Recovery
<trigger, rollback/restore/compensation/roll-forward steps, time, data effects>

## Preflight checklist
- [ ] <specific check with observable pass condition>

## Harness handoff
<updates to the existing plan/stage/Beads risk tags, invariants, tests, rollout, and recovery>
```

Use `GO WITH CONDITIONS` only for explicit, checkable preconditions. Use
`REPLAN` when the approach must change. Use `BLOCKED` when missing evidence or a
violated invariant prevents safe implementation.

Fold durable findings into existing orchestration artifacts. Do not create a
separate premortem file unless the repository contract requires one. A fresh
read-only reviewer can improve context isolation for genuinely complex,
high-risk work, but only through the Harness delegation gate; do not spawn one
by default.
