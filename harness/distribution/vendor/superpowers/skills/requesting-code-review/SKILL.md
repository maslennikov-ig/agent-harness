---
name: requesting-code-review
description: Use when completing tasks, implementing major features, or before merging to verify work meets requirements
---

# Requesting Code Review

Review the cohesive completed delta once when changed risk requires it. A
routine task, worker return, or local correction does not create a review gate.

## Selection

Use a combined correctness and improvement review when the change has a real
risk trigger: unfamiliar or public contracts, security, concurrency, data or
migration behavior, integration boundaries, high blast radius, or an explicit
audit requirement.

Keep the review local unless a reviewer subagent provides material context
isolation, specialist capability, parallel latency, or required independence.
Independence by itself is not enough unless the accepted risk contract requires
an independent reviewer.

## Inputs

Provide:

- the accepted requirements or plan;
- the cohesive base and head;
- the changed scope and known risk;
- current acceptance evidence;
- a read-only boundary and concise findings contract.

Use [code-reviewer.md](code-reviewer.md) when dispatching. Ask for every finding
with severity, confidence, file:line, and a concrete failure case. Let severity
filter the result; do not pre-filter what the reviewer may report.

## Acting on findings

- Fix P0/P1 findings before acceptance.
- Batch related P2+ findings into one correction wave when they are in scope.
- Rerun only failed or affected acceptance checks after the correction.
- Do not automatically dispatch a re-review after each fix.
- Add a second lens only for a distinct risk or an explicit independent-review
  requirement.

Push back on incorrect feedback with repository evidence. Stop when a real
load-bearing finding cannot be resolved within the accepted scope.
