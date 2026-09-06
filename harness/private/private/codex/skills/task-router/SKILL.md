---
name: task-router
description: Use when an orchestrated coding task needs docs-first research, installed skill or custom-agent selection, local catalog lookup, or safe asset promotion before implementation.
---

# Task Router

Task Router is the orchestrator's routing substep for documentation, skills, and custom agents. It is not a competing top-level workflow and does not replace `orchestrator-stage` or Superpowers.

Keep the mechanisms separate: `AGENTS.md` is project/folder rules, a skill is a
workflow/reference loaded from `SKILL.md`, and a specialist subagent is a custom
agent TOML from `~/.codex/agents/` or repository `.codex/agents/`. A configured
runtime directory is an additional source only when the current Codex client
actually exposes it.

## Pre-implementation Decision Gate

Apply the two independent gates owned by `orchestrator-stage` in
`references/autonomy-and-approvals.md`; do not duplicate them here. Inspect
available evidence first, ask only when a gate qualifies, otherwise record the
decision and proceed.

## Workflow

1. **Confirm orchestration context**
   - Use this after orchestrator-first triage classifies the task as medium/complex, docs-sensitive, unfamiliar, or likely to benefit from a skill or custom agent.
   - If the task is simple and quick, skip asset/catalog routing and let the orchestrator execute locally.
   - Root executes work it already holds the context for. `orchestrator-stage`
     delegates a stream only for a concrete parallel, context-isolation,
     specialist, or write-isolation benefit; unavailable subagents never block.

2. **Docs first**
   - For external or version-sensitive framework, library, API, CLI, platform, model, browser, or test-tool behavior, run `orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<API keywords>'` exactly once before relying on it. It resolves the lockfile version through `@neuledge/context` L1 and reports Context7/first-party fallback only when needed. Local-only work resolves nothing.
   - Local examples prove repository convention, not external guarantees; that is a reason to resolve a real dependency, not to record anything for a local change.
   - After compaction or resumption, re-establish the decision from current task truth; a reference loaded before compaction does not satisfy the current preflight.
   - If the repo enables `[knowledge_graph]` or has `graphify-out/GRAPH_REPORT.md`, remember that Graphify is an optional local aid. Consider it when architecture, impact, or unfamiliar code relationships matter and it is likely to save time; then read the report and run a focused `graphify query`, `graphify path`, or `graphify explain`.
   - The graph holds document names and headings, not their text, and matches node names rather than content: what a document says is found by reading and grepping it.
   - If the task is to enable, audit, or materially refresh Graphify, select `graphify-project` from `$HOME/.agents/skills/` when available; it owns hook trust and external-extraction authorization. Read-only audits and localized fixes do not refresh the graph; refresh only at an accepted relevant integration or release boundary when safe.
   - Do not paste `graphify-out/graph.json` into a prompt. Use the CLI/MCP surface to return only the focused subgraph needed for the task.

3. **Check installed assets**
   - Look first in Codex's native skill locations:
     - `$HOME/.agents/skills/`
     - `.agents/skills/` from the current directory up to the repository root
   - Also inspect these compatibility or managed-runtime locations when they
     already exist and the current runtime exposes them:
     - `$CODEX_HOME/skills/`
     - `${CODEX_ASSET_HOME:-${CODEX_HOME:-$HOME/.codex}}/superpowers/skills/`
     - `$HOME/.agents/skills/superpowers/` when present as a compatibility symlink
   - Look for matching custom agents in `.codex/agents/` at the repository root
     and `~/.codex/agents/`; also inspect `$CODEX_HOME/agents/` when that
     configured runtime directory exists.
   - Use custom agents for specialist spawned subagents such as deployment, correctness review, improvement review, documentation review, frontend, or database roles. Do not model a specialist subagent as `AGENTS.md`.
   - Prefer `docs_reviewer` for read-only documentation freshness review after structural, API/contract, migration, ops/deploy, or durable behavior changes.

### Design routing

- Use installed `impeccable` as the primary Impeccable craft workflow for websites, product UI, frontend surfaces, visual critique/polish, and visually designed HTML/CSS including HTML-to-PDF.
- Use Lazyweb when the task needs real-product screenshots, industry evidence, experiments, conversion research, or a hosted Lazyweb report or diagram. Use Impeccable to implement or refine accepted visual changes.
- Use Stitch only for an explicit Stitch request or an existing Stitch artifact. For visually designed HTML-to-PDF, combine Impeccable with the PDF skill for rendering, pagination, font/layout fidelity, and visual inspection; plain PDF operations stay with the PDF workflow.
- The same execution rule applies to design work. The stage skill separately
  decides whether multiple eligible design streams have enough benefit to run
  in parallel.

4. **Consult the optional local catalog when available**
   - If no obvious installed asset fits and a local catalog exists, consult:
     - `${CODEX_ASSET_HOME:-${CODEX_HOME:-$HOME/.codex}}/catalog/index.md`
     - `${CODEX_ASSET_HOME:-${CODEX_HOME:-$HOME/.codex}}/catalog/assets.json`
   - If neither catalog file exists, skip catalog routing cleanly and continue
     with installed assets, the closest visible agent, or local execution. The
     catalog is an optional enhancement, not a prerequisite.
   - If the catalog is stale or source sync errors are present, refresh it only
     when the corresponding installed helper exists:
     - `python3 "${CODEX_ASSET_HOME:-${CODEX_HOME:-$HOME/.codex}}/bin/sync_catalog.py"`
     - `python3 "${CODEX_ASSET_HOME:-${CODEX_HOME:-$HOME/.codex}}/bin/refresh_promoted_assets.py"`
   - If a refresh helper is absent, record the catalog as unavailable and keep
     working from installed assets. Never invent, download, or call an
     uninstalled catalog helper.
   - Treat external skill packs as reference candidates, not as replacements for the active repo workflow.
   - Use `skill_scout` if ranking the options will help.
   - If a trusted staged asset is the best fit, vet and promote it automatically
     only when both installed helpers exist:
     - `python3 "${CODEX_ASSET_HOME:-${CODEX_HOME:-$HOME/.codex}}/bin/vet_asset.py" --source <id> --type <skill|agent> --name "<name>"`
     - `python3 "${CODEX_ASSET_HOME:-${CODEX_HOME:-$HOME/.codex}}/bin/promote_asset.py" --source <id> --type <skill|agent> --name "<name>"`
   - Without those helpers, catalog entries remain lookup-only candidates;
     prefer installed assets or local execution.
   - Record the full routing decision at the root. Pass only applicable results to the child; do not serialize empty routing fields into a native prompt.
   - A delegated prompt carries a compact `Documentation` decision — the exact `docs-resolve` result — only when its stream touches external/versioned behavior. Omit the field for a local stream; the child stops before relying on an external claim it was not given.
   - Pass focused Graphify output only when the child needs it. Attach selected `SKILL.md` files structurally when supported; otherwise add a short pointer.
   - Select the installed `agent_type` structurally. Do not copy its role body into the task prompt.
   - Children should not repeat catalog discovery unless the prompt marks it as specialist-blocked.

5. **Routing output contract**
   - Before launching a subagent or drafting a manual fallback prompt, record at the root:
     - `Documentation`: exact `docs-resolve` result when the stream is external/versioned; omitted otherwise.
     - `Knowledge Graph`: `Graphify used - <report/query/path>` or `not configured/not relevant - <reason>`
     - `Selected skills`: exact skill names/paths, or `none - <reason>`
     - `Selected agents/personas`: exact agent names/paths, or `none - <reason>`
     - `Agent type to spawn`: built-in/custom `agent_type`, or `none - <reason>`
     - `Skill items to attach`: exact `SKILL.md` paths for structured `skill` items, or `none - <reason>`
     - `Catalog candidates`: promoted/lookup-only candidate names, or `none - <reason>`
   - A native child prompt remains `Goal`, `Write zone`, `Verification`, and `Stop`; carry Documentation inside Verification and add only applicable task, graph, skill, agent, or artifact pointers.
   - Include only assets that lower risk or improve execution; do not add decorative or generic assets or empty `none` blocks to the child.
   - If a suitable installed skill or agent exists, prefer naming it over asking the child to rediscover assets.
   - If descriptions and `QUALITY_PACK` do not resolve a material specialist choice, use `skill_scout`; otherwise select the closest installed role or the default visible worker.

## Agent Role Shortlists

Use these after checking installed agent descriptions and QUALITY_PACK; pick the installed specialist that best matches the actual task.

- Review/fix: `correctness_reviewer`, `improvement_reviewer`, then `security_auditor`, `performance_engineer`, `docs_reviewer`, `frontend_specialist`, or `qa_expert` by trigger.
- Test/E2E: `qa_expert`, `ui_ux_tester`, `accessibility_tester`, `frontend_specialist`, `performance_engineer`, `security_auditor`, `risk_manager`, `deploy_specialist`, or `deployment_engineer` by risk area.
- Legacy/dead-code audit: `code_mapper`, `dependency_manager`, `correctness_reviewer`, `improvement_reviewer`, and `security_auditor` for sensitive auth/privacy/billing/data paths.
- GitHub issue intake: `code_mapper` for impact mapping, `docs_researcher` when current behavior matters, then the implementation or reviewer specialist matching the selected cluster.
- Docs/update: `docs_reviewer` for freshness, `docs_researcher` for current external facts, and `documentation_engineer` only for accepted docs writes.
- Prompt/agent/LLM workflow: `prompt_regression_tester`, `llm_architect`, `ai_engineer`, `responsible_ai_reviewer`, and `risk_manager` by risk.

6. **Promotion rule**
   - Prefer already-installed assets.
   - Official OpenAI skills may be auto-installed on demand.
   - Community assets may be auto-promoted only when the local policy marks the source as `vetted-community` and static vetting passes.
   - Never auto-promote `catalog-only` community sources, including Codex-native community agents; use them for lookup or ask before changing trust mode.
   - Never describe a catalog-only asset as installed or directly spawnable.
   - If vetting fails, prefer an already installed asset. When no suitable
     visible subagent remains, continue locally: unavailable delegation never
     blocks the work.

7. **Hand off to the normal workflow**
   - New behavior or non-trivial change -> `brainstorming`
   - Multi-step task -> `writing-plans`
   - Bug or failure -> `systematic-debugging`
   - Code changes -> `test-driven-development` when appropriate
   - Before claiming done -> `verification-before-completion`

8. **Beads discipline**
   - If work will change files, last more than about 15 minutes, or may need handoff, create or select a Beads task first.
