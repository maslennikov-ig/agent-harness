---
name: orchestration-setup
description: Use when a repository or project folder needs the shared AGENTS-first orchestration baseline initialized, audited for drift, or reconciled to the current baseline.
---

# Orchestration Setup

## Overview

Initialize, audit, or reconcile `balanced-v2.20`. Keep `AGENTS.md` first,
contracts and navigation compact, acceptance root-owned, and Beads authoritative.

## When To Use

Use it to initialize a missing contract, audit possible drift, or reconcile an
older/heavy baseline. Do not use it for one-off work in an aligned repository.

## Pre-implementation Decision Gate

Apply the two independent gates owned by `orchestrator-stage` in
`references/autonomy-and-approvals.md`; do not duplicate them here. Inspect
available evidence first, ask only when a gate qualifies, otherwise record the
decision and proceed.

## Operating Modes

Pick one mode before editing:
- `initialize`: the repo is missing the live orchestration surface and needs the baseline created
- `audit`: the repo already has orchestration files; inspect whether it is `aligned`, `aligned_with_exceptions`, or `drifted`
- `reconcile`: bring a partially initialized or drifted repo back to the current baseline, auto-fixing safe contract drift and proposing any risky repo-specific decisions

## Required Decisions

Before editing, determine:
- repo topology: single-repo or multi-repo
- delivery mode: direct, PR-only, or mixed
- launch mode: direct execution or manual user launch
- canonical verification commands
- current stage id if you are migrating an active stage

## Managed Surface

Treat this as the live managed surface for baseline checks:
- `AGENTS.md`
- `.codex/orchestrator.toml`
- `.codex/handoff.md`
- `.codex/project-index.md`
- `.codex/stage-artifact-template.md`
- `.codex/stage-manifest-template.json`
- `.codex/scope-preservation-ledger-template.json`
- `.codex/scope-criterion-snapshot-template.json`
- `.codex/subagent-task-contract.md`
- `.codex/subagent-spawn-template.md`
- `scripts/orchestration/run_process_verification.sh`
- `scripts/orchestration/run_bounded_node_tests.py`
- `scripts/orchestration/validate_artifact.py`
- `scripts/orchestration/lint_stage_sizing.py`
- `scripts/orchestration/check_stage_ready.py`
- `scripts/orchestration/run_stage_closeout.py`
- `scripts/orchestration/record_stage_telemetry.py`
- `scripts/orchestration/cleanup_stage_workspace.py`

For repos with delegated or manual-launch child streams, also require:
- `scripts/orchestration/report_child_completion.py`
- `scripts/orchestration/review_completion_inbox.py`

For repos with `launch_mode = "manual_user_launch"`, also require:
- `.codex/manual-agent-prompt-template.md`

Historical archive files are not part of the managed surface unless the repo explicitly promotes them back into live use.

On every future run, compare the repo against this current skill baseline. If the skill gained a new managed file or required contract key, add it during `reconcile`.

## Bootstrap Contract

Create or refresh the Managed Surface above, including its launch-mode-specific
files. Do not create historical archive files unless the repo promotes them
back into live use.

Update `.gitignore` so tracked stage artifacts remain versioned:
- allow `.codex/project-index.md`
- allow `.codex/stage-artifact-template.md`
- allow `.codex/stages/`
- allow `.codex/stages/**`

Keep Beads as the only source of truth for durable task, decision, dependency, and status history. Query the selected goal lineage instead of copying the full backlog into prompts or Markdown.
Do not create `tasks.json`.

## Current Repo Baseline (`balanced-v2.20`)

`AGENTS.md` should stay short and stable:
- project shape
- canonical verification entrypoint
- autonomy policy
- safety boundaries
- where current operational state lives
- a short reminder that work starts with orchestrator-first triage: root
  executes work it already holds the context for, including medium work, and
  delegates a stream only for a concrete parallel, context, specialist, or
  write-isolation benefit
- a short reminder that Superpowers process skills still apply after routing: brainstorming for new behavior, writing-plans for multi-step execution, systematic-debugging for bugs, test-driven-development when appropriate, and verification-before-completion before completion claims
- a short reminder that Beads is the only durable task/history truth; query the selected goal lineage and initialize it with `bd init --init-if-missing --non-interactive --skip-agents --skip-hooks` when missing and policy allows local setup
- a short reminder that silent technical debt is not allowed: fix in-scope issues now, and make any real defer explicit, bounded, and tracked
- a short reminder that child prompts should be outcome-first, boundary-driven, docs-aware, and accompanied by a short Russian user brief
- a short reminder that native delegated prompts use goal, write zone,
  verification, and stop; add selected assets only when needed
- for repos with frontend or visually designed HTML/CSS surfaces, a short Design routing reminder: Impeccable is primary craft, Lazyweb is evidence/report/diagram, Stitch is explicit-only, and HTML-to-PDF pairs with PDF render verification; this rule never authorizes delegation
- a short reminder that child delivery, acceptance, and cleanup state is
  reconciled once at final stage closeout, not through an immediate per-child
  mini-closeout

New or reconciled repos should carry only a compact local reminder:

- triage first: root keeps coordination, shared decisions, integration, final
  acceptance, and delivery, and executes work it already holds the context
  for, including medium work; a stream is delegated through
  `orchestrator-stage` only for a concrete parallel, context, specialist, or
  write-isolation benefit
- if delegation is unavailable, continue locally instead of blocking
- launch additional eligible streams together only for a concrete latency,
  context-isolation, specialist-capability, or write-isolation benefit;
  independence or a PDM alone is insufficient
- delegated prompts use the four-field spawn template; the Documentation
  decision and task/skills/artifact pointers are all conditional
- Beads owns durable work history; handoff stays current-state only and Project Index stays navigation-only
- child delivery/acceptance/cleanup state is reconciled at final stage closeout;
  no per-child acceptance gate is added, and E2E/smoke and broad review remain
  risk-triggered
- keep `AGENTS.md` compact and route reusable detail back to the shared skills/templates
- do not vendor or copy the upstream Impeccable skill into the repository baseline; rely on the supported global installation and report its availability separately from baseline alignment

`.codex/orchestrator.toml` should stay thin and machine-readable:
- `role = "orchestrator-stage"`
- `[baseline]` with `profile = "balanced-v2.20"` and `source_skill = "orchestration-setup"`; valid v2.17/v2.18/v2.19 repositories remain compatible and are reported as `upgrade_available`
- `[orchestration_levels]` with default `slice_acceptance`, stage levels
  `slice_acceptance|integration|release`, and legacy aliases `inner|delta`
- topology
- launch mode
- configured release commands; task commands are passed explicitly to
  `run_stage_closeout.py`
- `[verification_policy]` with `mode = "explicit"`, default
  `slice_acceptance`, and `reuse_unchanged_evidence = false`; enable reuse only
  after the repo owns a complete `verification-manifest/v2`
- `verification-evidence/v2` fingerprints the exact required step set, commands,
  declared inputs (including ignored files), lockfiles, tools, captured
  environment, dependencies, cwd, platform, manifest, and producer; v1 receipts
  remain readable history but are never reusable
- when `verification_policy.reuse_unchanged_evidence = true`, final closeout
  automatically uses matching v2 evidence; `--reuse` remains compatible,
  `--must-run` executes every step, `--shadow` records would-hit decisions
  without serving cache, and
  `ORCHESTRATION_EVIDENCE_REUSE_DISABLED=1` is the kill switch
- the immutable aggregate PASS report lives under the Git common directory and
  the stage receipt links its byte digest and self-digest; nullable cost signals,
  foundation-slice guards, and
  `[stage_sizing]` from the v2.20 template
- one mandatory `orchestration-stage/v1` manifest before implementation, a write-once goal-level `scope-criterion-snapshot/v1` anchor, one active implementation stage per selected goal, parallel streams explicitly aggregated into that boundary, five exact split reasons with material evidence, and `scope-preservation-ledger/v1` on replan/split
- artifact paths
- completion inbox paths
- delivery toggles
  - default `delivery.push_after_closeout = "ask"` for unknown, team, protected, deploy-sensitive, or unclear repos
  - use `delivery.push_after_closeout = "allowed"` for trusted direct-delivery repos where ordinary push may run after successful closeout without asking again
  - allow worker/subagent feature-branch push only when the repo contract or task contract explicitly permits that branch and forbids protected/base branch push
- repo-specific exceptions
- enforcement entrypoints
- one-owner acceptance and closeout policy
- required `stage_limits.*` for cohesive vertical slices, selected-Beads-goal continuation, material-boundary replanning, cost-anomaly replan without a hard numeric stop, and correction caps; optional `agents.*`, `prompt_cache.*`, and `debt_scan.*` guardrails
- `[delegation]` with `launcher = "codex_subagents"`, separate spawned-thread
  visibility, `subagents_preauthorized_for_medium_complex = true`,
  `root_execution_scope = "holds_context"`,
  `medium_execution_default = "root_or_delegated_by_benefit"`,
  `complex_execution_default = "root_or_delegated_by_benefit"`,
  `delegation_gate = "concrete_benefit"`,
  `delegation_unavailable_action = "continue_locally"`,
  `simple_checks_owner = "orchestrator"`, and
  `independence_alone_sufficient = false`. Root retains coordination, shared
  decisions, integration, final acceptance, and delivery, and executes work it
  already holds the context for. Parallel execution is optional and used only
  for a concrete latency, context-isolation, specialist-capability, or
  write-isolation benefit; sequential execution needs no separate rationale
- `[subagent_model_policy]` with Astra as root, discretionary Luna/Terra/Sol
  starters for mechanical, simpler, and complex delegated streams, truthful
  capability fallback, and recorded role/model/effort/rationale
- `[token_efficiency]` with explicit `fork_turns="none"`, reasoned non-none
  override, four-field prompt, bounded-output, progress, verification, and
  benefit-gated parallelism defaults; these are strong defaults, never hard
  token caps
- for manual-launch repos: `manual_prompt_template` path
- for a project-local Codex hook: record that new or changed non-managed hooks are skipped until the user reviews and trusts the exact definition through `/hooks`; never bypass hook trust merely because setup wrote the file

`.codex/handoff.md` must be current-state only.
It must also leave:
- `Next stage id`
- `Recommended action`
- `Starter prompt for next orchestrator`
- `Explicit defers`
Detailed stage history belongs under `.codex/stages/<stage_id>/`.
Keep the repo-local handoff target at 200 lines with
`current_state_max_lines = 200`. Set `hard_limit_lines = 500` as the fixed
ceiling. If necessary current state cannot fit within 200 lines without losing
information needed for continuation, raise only `current_state_max_lines` to
the smallest adequate value up to 500. Preserve that local value during
reconcile, never raise `hard_limit_lines`, and restore the 200-line target after
the handoff is compacted. A repository may explicitly opt into a stricter local
limit.

`.codex/project-index.md` must be a stable navigation map:
- 80-150 lines by default
- runtime shape and primary entrypoints
- core subsystems and ownership boundaries
- integrations and source-of-truth precedence
- canonical verification commands
- durable repo-local conventions

Do not put task, release, deployment, stage, or handoff history in the project index.
Beads owns durable work history; the Project Index remains the stable navigation map.

## Audit Rules

Classify the repo as:
- `uninitialized`: missing core baseline files
- `partially_initialized`: some baseline files exist, but the live contract is incomplete
- `aligned`: baseline marker is present, managed surface is current, and process verification passes
- `aligned_with_exceptions`: the repo matches the baseline except for explicit repo-local exceptions recorded in `AGENTS.md` or `.codex/orchestrator.toml`
- `drifted`: baseline markers are missing, guardrail files are stale, handoff/report sprawl reappeared, a duplicate task ledger exists, or verification fails

Safe `reconcile` fixes:
- add missing baseline files and `[baseline]` markers
- refresh repo-local guardrail scripts from this skill's templates
- move human-readable policy out of `.codex/orchestrator.toml` when `AGENTS.md` should own it
- compact `.codex/handoff.md` back to current-state only
- create `.codex/stages/<stage_id>/summary.md` and tracked artifacts when migrating active stage history
- add or refresh the repo-local closeout entrypoints and policy markers when the shared baseline gained them
- add or refresh the delegated completion inbox entrypoints and contract when the shared baseline gained them
- add or refresh the explicit `## Explicit defers` handoff section; use `- none` when there is no justified deferred work
- create `.codex/project-index.md` when missing; preserve existing canonical content, copy legacy `.Codex/project-index.md` when present, otherwise fill a compact repo-specific scaffold from the actual repo shape
- add `.codex/manual-agent-prompt-template.md` when the repo uses `manual_user_launch`; preserve repo-specific customizations if the file already exists
- refresh the outcome-first prompt skeleton and closeout debt-marker checks when the shared baseline gained them

For any older `balanced-v2` profile, first finish or explicitly retire active
stage/child work, then run `python3 support/sync_support_files.py <repo> --force
--migrate-contract --dry-run`. After reviewing its hashes, apply that exact plan
with `--apply --reviewed-plan-hash <hash>`. Migration governs future work only:
never rewrite accepted manifests/summaries or silently close Beads. Every new
stage id requires the v2.20 manifest and stable goal anchor, and every new
delegated stream artifact must be listed v3.
In machine-contract terms, every post-migration stage id requires the v2.20
manifest; historical accepted work remains immutable.
For completion transport, every new delegated stream artifact uses v3 and must match its manifest task, stream owner, and repo-relative path.

Do not guess on repo-specific delivery rules, topology, deployment flows, or architecture constraints. If those are unclear, stop and propose the exact decision that still needs confirmation.

## Support Files

Read `templates/baseline.toml` to see the current managed surface and profile marker.

Use the bundled helpers first:
- `python3 support/audit_repo.py <repo-path>` for a fast baseline audit. It emits `uninitialized`, `partially_initialized`, `aligned`, `aligned_with_exceptions`, `upgrade_available`, or `drifted`; the aligned and `upgrade_available` states exit successfully. It also compares the content of the managed `scripts/orchestration/` helpers against this skill's templates and lists any mismatch in `drifted_support_files`, so a current profile marker can no longer hide an older script generation. Refresh those with `sync_support_files.py --force`.
- `python3 support/sync_support_files.py <repo-path> --dry-run` to preview a
  deterministic plan with HEAD and preimage hashes, then `--apply
  --reviewed-plan-hash <hash>` to transactionally refresh template-managed
  support files according to `delegation.launcher`. The target must be a clean
  regular Git worktree without active/child work; the helper rechecks state and
  rolls back every preimage on failure. First project-`AGENTS.md` adoption needs
  `--adopt-agents-block`; custom marker overlap is deferred. Completion-inbox
  helpers are delegated/manual only, and the manual prompt template is
  manual-only.
- `python3 support/sync_support_files.py <repo-path> --token-efficiency-only
  --dry-run` to inspect the two-file policy delta even while stage work is
  active. Apply only after stage and child work are idle; apply rechecks and
  refuses active work. This mode may touch only
  `.codex/subagent-spawn-template.md` and an absent canonical
  `[token_efficiency]` section. An exact canonical subset upgrades additively;
  unknown keys or changed values fail closed. Review its hash before `--apply`;
  conflicting migration, force, or adoption flags fail.
- `python3 scripts/orchestration/run_bounded_node_tests.py -- <test-files...>` for Node suites that can retain timers, sockets, workers, or child processes. It rejects a duplicate cwd/test-set run, applies a 30 s Node timeout and 60 s outer deadline by default, and terminates only its own process group on timeout or leak.

Copy the guardrail scripts and artifact template from this skill's `templates/` directory into the target repo, then adapt only the repo-specific verification commands, topology, delivery rules, and justified repo-local exceptions.
Create or refresh `.codex/project-index.md` as repo-specific content; do not overwrite an existing valid index during reconcile.
For manual-launch repos, also bootstrap `.codex/manual-agent-prompt-template.md` from the shared template if it does not already exist.

Use stage artifact context fields (`epic_id`, `session_id`, `milestone`,
`milestone_status`, `orchestration_level`, `risk_tags`, `affected_surfaces`, and
`invariants`) to describe new work. Historical `verification_tier` remains
readable, but v3 artifacts do not emit it. Metadata strengthens reasoning and
review; it never selects commands.

For long or staged work, record known checkpoint telemetry with `scripts/orchestration/record_stage_telemetry.py --stage <stage-id> ...`. The sidecar at `.codex/stages/<stage-id>/telemetry.json` records worker wall time, cumulative agent time, queue time, review rounds, P0/P1 findings, integration/rebase time, and per-check duration. Never estimate missing measurements: leave them `null` with `coverage: unavailable`. The Panel is a read-only projection, not task or acceptance truth. Bounded medium work does not need a sidecar.

Sizing diagnostics are canonical telemetry, not raw sidecar edits. Record
`suspicious_micro_stage` with `--sizing-diagnostic`. Repeated unchanged
acceptance is handled by the v2 receipt plus its immutable aggregate report. A
v1 receipt is historical only.

Completion-inbox decisions are immutable. For a P0/P1 correction, report the correction event with `--resolves-review <finding-event-id>` and mark that correction accepted; do not overwrite the original review finding. Stage closeout enforces the linked acceptance when `stage_limits.p0_p1_block_acceptance = true`.

When reconciling an existing repo:

- refresh copied support files from the current templates when safe, using the target launch mode so delegated/manual-only files are not added to ineligible repos
- install the managed `verification_evidence.py` and manifest template without
  inventing or changing the repo's required step/command set; v2.19 upgrades
  require explicit `--migrate-contract`, and v2.16 migration is refused; when
  stale immutable artifacts make the legacy active-stage candidates ambiguous,
  `--legacy-active-stage-id <discovered-id>` records the one repo/Beads truth
  identifies without rewriting historical artifacts
- route a configured evidence manifest only to its `[evidence].level` (default
  `release`); other levels keep exact command acceptance and cannot request v2
  reuse or shadow mode without their own routed manifest
- preserve repo verification commands, delivery constraints, tracked stage history, and explicit `push_after_closeout = "allowed"` only where the repo already chose trusted direct delivery
- create or update Project Index only from stable repo structure; keep handoff current-state only
- preserve or add the compact reminder above, including benefit-gated
  delegation, benefit-gated parallel fan-out, the four-field native prompt, central
  artifacts, and explicit debt tracking
- do not expand `AGENTS.md` into the skill body or rewrite historical archives without an explicit cleanup request

## Verification

After initialize or reconcile:
- run `scripts/orchestration/run_process_verification.sh`
- if you migrated an active stage, validate it with `python3 scripts/orchestration/check_stage_ready.py <stage_id>`
- confirm the repo contract mentions Beads as the only task truth and does not introduce `tasks.json`
- confirm `.codex/handoff.md` includes a non-empty `## Explicit defers` section
- confirm `.codex/project-index.md` exists, has the required navigation sections, stays within the line limit, and does not duplicate handoff/history state
- for a new high-risk stage, confirm its artifact declares an orchestration
  level, risk tags, affected surfaces, and invariants; confirm the root supplied
  exact commands and each proves a distinct touched boundary
- for a frontend/design repo, confirm the compact Design routing rule is present at the applicable global or repo scope and report whether the external Impeccable installation is available; missing external tooling is a dependency-health result, not permission to vendor it or silently mark an otherwise aligned repo drifted
- report the result as `aligned`, `aligned_with_exceptions`, or `drifted`
