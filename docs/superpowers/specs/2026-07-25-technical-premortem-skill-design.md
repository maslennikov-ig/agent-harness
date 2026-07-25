# Technical Premortem Skill Design

## Goal

Add one global, English-language `technical-premortem` skill for Codex and
Claude. Both runtimes must receive the same `SKILL.md`, while the Harness keeps
one explicit installation path for each runtime.

## Trigger model

The skill runs once after a plan direction is settled and before implementation
when the change crosses a material risk boundary: data or migrations, auth or
security, tenancy, concurrency or idempotency, public contracts, deployment or
runtime behavior, irreversible operations, or an unknown consumer/blast radius.

It skips documentation, copy, cosmetic, mechanical, and other low-risk
non-behavioral changes by default. It also skips repeated inner-loop use while
the risk boundary is unchanged. It reruns only when the plan changes a
contract, data path, consumer set, recovery path, or an earlier assumption.

## Analysis contract

The agent assumes the change was merged, deployed, and failed. It reconstructs
the blast radius from repository evidence, then checks four failure paths:
intended behavior failed, a neighbor regressed, silent degradation occurred, or
delayed production/recovery harm appeared.

Findings use two independent axes:

- evidence: confirmed, plausible, or unsupported;
- disposition: block, preflight, monitor, or dismiss.

The output includes a verdict, blast radius, concise risk register, blocking
details, recovery strategy, and preflight checklist. Executor error is a
mandatory risk surface. Unsupported hypotheses cannot block implementation.

## Harness integration

- Canonical Codex skill:
  `private/codex/skills/technical-premortem/SKILL.md`
- Canonical Claude skill:
  `private/claude/skills/technical-premortem/SKILL.md`
- Runtime Codex target:
  `${AGENTS_HOME}/skills/technical-premortem/SKILL.md`
- Runtime Claude target:
  `${CLAUDE_HOME}/skills/technical-premortem/SKILL.md`

The two canonical files are byte-identical. The private overlay gains a Claude
skills component. Public `export-local --scope private` and its overlay template
gain the same path so future exports do not silently drop personal Claude
skills.

`export-local` excludes the Harness-managed `orchestration-bridge` plugin from
the Claude personal-skills source. The plugin remains owned and updated by the
public orchestration-console component rather than being duplicated into the
private overlay.

The skill folds durable findings into the existing plan, stage, Beads task,
invariants, tests, and rollback fields. It does not create a new mandatory
lifecycle artifact and does not duplicate global `AGENTS.md` policy.

## Verification

- static contracts for parity, English-only content, triggers, skip/rerun rules,
  evidence/disposition fields, executor error, and recovery;
- export-local tests for Claude personal skills and manifest generation;
- representative high-risk and low-risk prompt evaluations;
- canonical repo test suites and byte comparison against installed copies.
