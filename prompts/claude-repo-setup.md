Use `orchestration-bridge:orchestrator-stage` for Claude Code CLI project memory and orchestration baseline setup.

Goal: initialize or reconcile a repository so Claude Code CLI can follow compact project memory, route through `orchestration-bridge`, use Docs L1/L2, verify work, and close out consistently.

Preflight:
1. Read repo `AGENTS.md`, `CLAUDE.md`, README/docs, Beads state when available, Graphify configuration, hooks, and `git status`.
2. Classify the run as audit-only or reconcile. If the user asked only for audit, do not write files.
3. Create/select a Beads task before file-changing setup when Beads is available.
4. Prove Claude runtime context before changing files: report `claude --version`, enabled `orchestration-bridge` plugin status, available relevant plugin skills/agents, and the exact Docs Resolver / Docs L1/L2 rule loaded from global/project memory, including `orch-prompts docs-resolve` over `@neuledge/context` L1.
5. Check runtime/project surfaces: run `claude mcp list` and `orch-prompts claude-agents` from the intended repo root; report global plugin agents separately from project-local `.claude/agents`.

Reconcile scope:
- Keep `CLAUDE.md` concise and project-specific.
- If a modern `AGENTS.md` exists, make `CLAUDE.md` a thin adapter that imports `@AGENTS.md` and adds only Claude-specific runtime notes.
- Move reusable process detail into Claude plugin skills, prompt cards, repo docs, or `AGENTS.md`; do not expand `CLAUDE.md` into a long workflow manual.
- Remove stale positive routing to `template-bridge`, `unified-workflow`, “Context7 first”, blanket push rules, and outdated Claude Desktop assumptions.
- Preserve real project-specific commands, stack notes, deploy notes, MCP notes, and local safety constraints.
- Project MCP baseline: when reconcile/full setup is requested and no project MCP exists, create a secretless `.mcp.json` only for common local servers already supported by the environment, such as `context`, `context7`, `playwright`, and `shadcn`; do not template credentials, tokens, Supabase refs, GitHub tokens, or hosted account auth.
- Project-local agents: when the repo should show baseline agent files, use `orch-prompts claude-agent-install --agent <name> --scope project` from the repo root to create vetted Markdown agents under `.claude/agents`; otherwise report the available plugin agents and exact install commands instead of silently skipping them.
- Beads ledger: a Git-tracked `.beads/issues.jsonl` is an export, not the source of truth or cross-machine sync. Check `bd hooks list`, `bd config get export.auto`, and `bd dolt remote list`. Install the Beads hooks and set `export.auto true` when either is missing; both are needed, because the commit hook exports only while `export.auto` is on. Ask before `bd dolt remote add` and the first `bd dolt push`, which write to the remote.
- Beads↔GitHub reconciliation: set `github.owner`/`github.repo` from `origin`
  and keep the token in `GITHUB_TOKEN` from `gh auth token`, never in tracked
  `.beads/config.yaml`. For every eligible repository with one matching
  canonical database, run
  `$HOME/.agents/orchestration-console/scripts/github_sync.sh --install-hooks
  [--dry-run] <repo...>`. It must replace the managed marker block, preserve
  unrelated hook content, and route both Git events to the directionless
  bounded trigger. A Beads upgrade must not replace this wrapper-owned status
  authority; rerun the installer and its dry-run audit after every upgrade
  instead of enabling raw GitHub sync hooks.
- Configure Graphify only when in scope; do not install Graphify git hooks unless explicitly asked. Beads hooks are separate and not covered by that restriction.

Success criteria:
- Repo has compact Claude project memory or an explicit audit result explaining what is missing.
- Claude routing, Docs L1/L2, Beads, Graphify review, verification, closeout, and delivery policy are configured or marked not applicable with reasons.
- Verification evidence proves changed Markdown/JSON/TOML files parse or are syntactically valid where practical.

Verification:
- Run repo setup/check scripts when present.
- Run `git diff --check`.
- Validate JSON/TOML files changed.
- For migrated `CLAUDE.md`, grep for stale strings: `template-bridge:`,
  `unified-workflow`, `Context7 first`, `Context7 MCP first`, blanket push
  rules, and retired directional GitHub sync bodies.
- Grep `AGENTS.md`, `CLAUDE.md`, and `.claude/rules/**/*.md` for stale docs routing such as Context7-primary instructions, direct `context query` as the primary path, or wording that treats Docs L1/L2 itself as an MCP server; replace with Docs Resolver over `@neuledge/context` L1 and Context7/first-party fallback.
- Compare the Beads issue count with the line count of a tracked `.beads/issues.jsonl`; a mismatch means the ledger drifted and needs `bd export -o .beads/issues.jsonl` before delivery, so a pushed commit never lands without its task record.
- Report unavailable checks with exact blockers.

Stop rules:
- Ask before Graphify git hooks, external model/API-backed extraction, broad docs rewrites, or changing project-specific operational rules.
- Stop if baseline ownership or repo policy conflicts cannot be resolved from local evidence.

Output:
- Mode: audit-only or reconciled.
- Files changed or reviewed-no-change.
- Runtime/memory proof: Claude version, memory files inspected, plugin/skills/agents visibility, and effective Docs L1/L2 policy.
- Verification evidence.
- Remaining explicit defers.
- `docs-reviewed` result.
- `graph-reviewed` result.
