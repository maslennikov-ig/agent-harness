Use $orchestration-setup for the current repository.

Goal: initialize, audit, or reconcile the repository to the Codex AGENTS-first orchestration baseline `balanced-v2.20` while preserving repo truth.

Success criteria:
- Report baseline status with bounded next actions; only aligned states succeed.
- Configure or explicitly classify Beads, Superpowers, visible subagents, Docs L1/L2, verification, closeout, handoff, delivery, and every Setup decision below.
- Changed files pass the repository verification contract.

Preflight:
- Read `AGENTS.md`, `.codex/`, `.beads/`, Graphify/hooks, branches/worktrees, and `git status`.
- Check `bd --version` and `bd status --json`; verify `$CODEX_HOME/superpowers/skills`, QUALITY_PACK, installed skills, and `orch-prompts status`.
- Classify mode as `initialize`, `audit`, or `reconcile`. Audit mode is read-only.
- For file-changing setup, initialize missing Beads with `bd init --init-if-missing --non-interactive --skip-agents --skip-hooks` (`--stealth` when required), then create/select the Beads task. Do not create `tasks.json`.

Setup decisions:
Before optional writes, return an `enable / skip / blocked / not applicable` table with evidence/action.

- Graphify: use `$graphify-project` when triggered; external extraction/hooks need approval.
- Project dependencies: detect package managers/lockfiles; install only for verification and preserve lockfiles unless required.
- GitHub remote/repository: inspect `.git`, remotes, and `gh auth status`. Ask before create/link, owner/name/visibility, replace `origin`, or initial push. New repositories are private by default; GitHub Actions/secrets/deploy keys need separate approval.
- Beads ledger: because `bd init` skips hooks, check `bd hooks list`, `bd config get export.auto`, and `bd dolt remote list`; tracked `.beads/issues.jsonl` needs installed hooks plus `export.auto true`. Ask before adding a remote or the first `bd dolt push`.
- Beads↔GitHub reconciliation: for every eligible repository whose canonical
  Beads database matches `origin`, run
  `$HOME/.agents/orchestration-console/scripts/github_sync.sh --install-hooks
  [--dry-run] <repo...>`. It must replace the managed marker block, preserve
  unrelated hook content, and route both Git events to the directionless
  bounded trigger. A Beads upgrade must not replace this wrapper-owned status
  authority; rerun the installer and its dry-run audit after every upgrade
  instead of enabling raw GitHub sync hooks.
- Agents/skills/catalog: verify QUALITY_PACK and installed assets; sync stale catalog only when policy allows and never auto-promote catalog-only assets.
- Docs L1/L2: the kernel owns the documentation decision; verify `orch-prompts docs-resolve` works here.
- Browser/E2E tooling: for frontend flows, inspect repo commands and the Playwright skill/local CLI; add no dependencies without need.
- Secrets/config guard: inspect examples/docs, not secret-bearing files; report missing samples.
- Narrow hooks: allow only repository-policy Codex hooks; no Graphify git hooks by default. Beads hooks are separate. Trust new non-managed Codex hooks through `/hooks`.
- Dual-runtime Claude: leave Claude memory/plugin setup to the Claude setup prompt unless explicitly included.

Reconcile scope:
- Keep `AGENTS.md` compact and repository-specific; route to Superpowers, Beads, Docs L1/L2, visible subagents, verification, closeout, and delivery without copying skill bodies.
- Reconcile `.codex/`, `.codex/subagent-task-contract.md`, `.codex/subagent-spawn-template.md`, and `scripts/orchestration/` from `$HOME/.agents/skills/orchestration-setup`, preserving project commands and delivery rules.
- Run `orchestration-setup/support/audit_repo.py` before/after and `orchestration-setup/support/sync_support_files.py` for managed files.
- Require `balanced-v2.20`, cohesive `[stage_sizing]`, separate visible threads, no inline-only agents, and `[subagent_model_policy]` with `high_reasoning_triggers`. The machine contract includes `subagents_preauthorized_for_medium_complex = true`, `delegation_gate = "concrete_benefit"`, `delegation_unavailable_action = "continue_locally"`, and `independence_alone_sufficient = false`. Root keeps coordination, shared decisions, integration, final acceptance, and delivery, and executes work it already holds the context for. Delegate a stream only for a concrete latency, context-isolation, specialist-capability, or write-isolation benefit; independence alone is insufficient, and unavailable subagents never block.
- Treat v2.17-v2.19 as `upgrade_available`; migrate by reviewed dry-run/apply, reject ambiguous legacy state, and preserve accepted history.
- Delegated templates use `docs-resolve` with lockfile versions before `@neuledge/context` escalation; Context7/first-party fallback stays conditional.

Verification:
- Run `scripts/orchestration/run_process_verification.sh`, `bd status --json`, Beads ledger sync, `git diff --check`, and changed JSON/TOML validation.
- Search changes for stale docs routing, non-visible delegation,
  duplicated delivery policy, and retired directional GitHub sync bodies.
- Report unavailable checks with exact blockers; never infer alignment from file presence alone.

Stop rules:
- Ask before destructive Beads re-init, broad AGENTS rewrites, lockfile changes, GitHub create/link/visibility, replacing `origin`, initial push, GitHub Actions/secrets/deploy keys, Dolt remote setup, external Graphify extraction/hooks, delivery-policy changes, push/PR/deploy, or live mutations.
- Stop when baseline ownership, repo delivery rules, or verification commands cannot be established safely.

Output:
- Mode and baseline status.
- Files changed/reviewed and Setup decisions.
- Verification evidence, blockers, and explicit defers.
- `docs-reviewed` and `graph-reviewed` results.
