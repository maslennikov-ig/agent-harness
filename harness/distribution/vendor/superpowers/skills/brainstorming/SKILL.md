---
name: brainstorming
description: "Use before creative work that needs product intent, requirements, alternatives, or design decisions clarified."
---

# Brainstorming Ideas Into Designs

Turn an idea into an implementable design without creating a ceremonial
approval loop.

## Two independent gates

**Information/intent:** ask one plain-language question when a missing fact is
owned by the user or organization, two or more materially viable outcomes
remain, and the answer changes behavior, acceptance, scope, cost, or rework. A
credible technical default does not remove that need.

**Authority:** ask separately only when the next action is external or
hard-to-reverse, and name that exact action. Never phrase a product question as
a permission request.

If repository truth makes one in-scope option clearly best, record the decision
and continue. If the user delegates the choice, decide from evidence and state
the assumption.

## Scale the artifact

- A feasibility spike ends with a recommendation; label any exploratory code
  as throwaway unless keeping it becomes an accepted implementation task.
- A bounded simple change may use a short design in the working checklist.
- Medium, complex, architectural, or handoff-prone work gets a durable spec.

If hidden complexity appears, increase the design depth. Do not use a lighter
label to skip a material decision or contract.

## Process

1. Inspect relevant files, documentation, recent changes, and existing
   conventions.
2. Identify the goal, constraints, success criteria, non-goals, consumers, and
   meaningful risks.
3. Ask only questions that pass the information gate, one at a time.
4. Compare alternatives only when multiple materially viable approaches remain.
   Lead with the evidence-backed recommendation.
5. Produce the smallest design that makes behavior, boundaries, data flow,
   failure handling, rollback, and proof unambiguous.
6. Self-review once for placeholders, contradictions, ambiguity, and scope.
7. Write a durable spec for medium/complex or handoff-prone work. A simple
   reversible change may keep the design in the working checklist.
8. Continue to `superpowers:writing-plans` when a durable multi-step plan is
   useful; otherwise implement directly under the accepted scope.

## User review

Request design or written-spec review only when the information gate still
qualifies after repository inspection. Do not ask for duplicate approval when
the user already accepted the outcome, delegated the decision, or repository
evidence leaves one clearly best in-scope design.

## Visual companion

Use a visual companion only when a diagram or mockup materially clarifies a
real design choice. Do not offer it merely because the topic is UI, and do not
turn every question into a browser interaction.

## Stop

Stop before implementation only when a material intent question remains
unanswered or implementation needs new authority. Risk categories strengthen
invariants, tests, and final review; they do not create an approval gate by
themselves.
