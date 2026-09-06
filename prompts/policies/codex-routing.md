# Codex Routing Policy

Stable routing rules for Codex orchestration prompt cards. Cards reference this
file instead of restating it. Resolve it at
`${AGENTS_HOME:-$HOME/.agents}/orchestration-console/prompts/policies/codex-routing.md`.

## Installed assets and catalog

- Start with repo `AGENTS.md`, project `.codex` files, Beads/handoff/stage
  truth, and the smallest installed skill/agent lookup that could change the
  outcome.
- Treat `$CODEX_HOME/agents/QUALITY_PACK.md` as the local agent source of
  truth. Read `$CODEX_HOME/agents/`, `$CODEX_HOME/skills/`,
  `${AGENTS_HOME:-$HOME/.agents}/skills`, and catalog only when the task needs
  specialist routing or installed assets do not fit.
- Prefer installed agents from QUALITY_PACK; search catalog only for missing or
  ultra-specific specialists.
- Use `skill_scout` before catalog when installed-agent routing is unclear,
  `asset_vetter` before external asset promotion, and `docs_researcher` for
  version-sensitive docs.
- For spawned `agent_type`, prefer TOML `name` values; console lists may show
  hyphenated filename slugs. If a newly installed agent is not visible in the
  runtime spawn list, report that Codex needs refresh/restart and use the best
  visible fallback.
- If catalog is stale and needed, run the user-level `codex-catalog-sync`
  package when it is installed — it is external to this repository — or resolve
  `CODEX_HOME` and run `${CODEX_ASSET_HOME:-$CODEX_HOME}/bin/sync_catalog.py` plus
  `${CODEX_ASSET_HOME:-$CODEX_HOME}/bin/refresh_promoted_assets.py`.

## Execution ownership

- `orchestrator-stage` owns execution routing. Root executes work it already
  holds the context for and delegates a stream only for a concrete parallel,
  context-isolation, specialist, or write-isolation benefit; unavailable
  subagents never block.
- Root retains coordination, shared decisions, integration, final acceptance,
  and delivery. Parallel fan-out remains stage-owned; independence alone is
  insufficient.

## Astra orchestration and GPT-5.6 workers

- Astra is the root orchestrator. Choose useful workers and integrate their
  results; keep critical decisions or tightly coupled work yourself when that
  is more effective. Small tasks may need no delegation.
- Luna is a useful default for narrow, well-specified, mechanical work; Terra
  for ordinary bounded substantive work; Sol for ambiguity, cross-boundary or
  high-risk work, and difficult diagnosis. These are recommendations, not hard
  partitions; repository evidence may justify another choice.
- Adjust supported model and reasoning controls to complexity. The stage
  delegation reference owns launch details and capability fallbacks; the
  panel profile changes prompt text, not the model running the conversation.

## Quality and review anchors

- Consider `correctness_reviewer` and `improvement_reviewer` for quality gates;
  run the same lenses locally only when the work is simple and quick.
- `improvement_reviewer` must include reuse/build-vs-buy: existing
  code/components/helpers/APIs, installed dependencies, mature libraries, and
  evidence for custom code when reuse would be smaller, safer, or clearer.
- Use read-only review roles for review streams; use writable development/fix
  roles only after a bounded write zone is chosen.
- Use `docs_reviewer` when public behavior, API/contracts, migrations/data,
  deploy/runtime, architecture/entrypoints, verification commands, or durable
  docs may change; use `documentation_engineer` only for accepted docs writes.

## Design routing

- Use installed `impeccable` as the primary craft workflow for websites,
  product UI, frontend surfaces, visual critique/polish, and visually designed
  HTML/CSS including HTML-to-PDF.
- Use Lazyweb when the decision needs real-product screenshots, industry
  evidence, experiments, conversion research, or a hosted Lazyweb report or
  diagram. Use Impeccable to implement or refine accepted visual changes.
- Use Stitch only for an explicit Stitch request or an existing Stitch artifact.
  For visually designed HTML-to-PDF, pair Impeccable with the PDF skill for
  rendering, pagination, font/layout fidelity, and visual inspection; plain PDF
  operations stay with the PDF workflow.
- The execution-ownership rule above applies to design work; selecting a design
  workflow does not alter delegation or parallel-launch policy.

## Agent role shortlists

Use these as starting points after reading QUALITY_PACK and installed agent
descriptions; prefer a better installed specialist when its description fits.
Each list is a candidate pool: select exactly one primary role for a stream,
then use the canonical delegation policy for model and effort. A shortlist is
not a role matrix and does not authorize extra agents.

- Review/fix: `correctness_reviewer`, `improvement_reviewer`, then
  `security_auditor`, `performance_engineer`, `docs_reviewer`,
  `frontend_specialist`, or `qa_expert` by trigger.
- Test/E2E: `qa_expert`, `ui_ux_tester`, `accessibility_tester`,
  `frontend_specialist`, `performance_engineer`, `security_auditor`,
  `risk_manager`, `deploy_specialist`, or `deployment_engineer` by risk area.
- Legacy/dead-code audit: `code_mapper` for reachability,
  `dependency_manager` for packages, `correctness_reviewer` and
  `improvement_reviewer` for challenge, plus `security_auditor` for sensitive
  auth/privacy/billing/data paths.
- GitHub issue intake: `code_mapper` for repo/impact mapping,
  `docs_researcher` when current behavior matters, then the implementation or
  reviewer specialist matching the selected issue cluster.
- Docs/update: `docs_reviewer` for freshness, `docs_researcher` for current
  external facts, and `documentation_engineer` only for accepted docs writes.
- Prompt/agent/LLM workflow: `prompt_regression_tester`, `llm_architect`,
  `ai_engineer`, `responsible_ai_reviewer`, and `risk_manager` by risk.

## Prompt and orchestration changes

- Treat the official OpenAI Prompt guidance as source of truth:
  `https://developers.openai.com/api/docs/guides/prompt-guidance`.
- Include `prompt_regression_tester` or a local equivalent checklist covering
  outcome-first structure, Goal/Success/Constraints/Output/Stop rules,
  risk-based tool/delegation use, verification/eval expectations, manifest/TOML
  parsing, CRLF byte estimate, role-routing scenarios, and UI/API visibility.

## Graphify mechanics

- If Graphify is configured, remember it as an optional local orientation aid.
  Use `graphify-out/GRAPH_REPORT.md` and focused `graphify query/path/explain`
  when useful for unfamiliar structure, relationships, or impact; never paste
  `graph.json`.
- The graph answers code-structure questions. It holds document file names and
  headings but not document text, and it matches node names rather than
  content, so information inside docs, ADRs, runbooks, and research notes is
  found by reading and grepping them, not by querying the graph.
- Read-only audits and localized fixes do not refresh Graphify. Refresh the
  local graph only at an accepted relevant integration or release boundary
  after code, architecture docs, entrypoints, routes, integrations, contracts,
  durable workflow/instructions, or module boundaries changed. If refresh is
  unsafe or blocked by parallel work/dirty ownership, record
  `graph-reviewed: blocked`; otherwise record `graph-reviewed: no-change-needed`
  with a reason.

## GitHub issue sync

Beads is the durable tracker; GitHub issues are its external view. The wrapper,
not a raw Beads GitHub command or an agent's separate `gh issue` edit, owns
reconciliation.

- Configure `github.owner` and `github.repo` from `origin`. Keep the token in
  `GITHUB_TOKEN`, read from `gh auth token`; `.beads/config.yaml` is tracked by
  git, so a token written there leaks with the next commit.
- A GitHub-only issue may be imported once when no exact local reference
  exists. A Beads-only task may be created or deterministically adopted once.
  After a link exists, Beads owns open/closed state: discovery never changes an
  existing Bead, and divergence is corrected outward on GitHub.
- After each successful local task mutation, enqueue exactly one bounded
  `$HOME/.agents/orchestration-console/scripts/github_sync.sh --trigger --bead
  <ID> <repo>` call. It coalesces
  repeated work and returns without waiting for network convergence. Do not
  create, edit, reopen, or close the GitHub issue as a second agent action.
- Generic repository events use
  `$HOME/.agents/orchestration-console/scripts/github_sync.sh --trigger
  <repo>`. Manual or periodic repair uses the same global launcher with
  `--reconcile [--dry-run] <repo>`.
- Automatic local coverage is limited to all non-closed tasks plus recently
  changed closed tasks and independently discovered GitHub issues. The old
  closed archive is outside the hot path; use the documented manual archive
  audit when historical repair is needed.
- Cover every eligible repository. Fail closed on no `origin`, a missing or
  mismatched canonical database, ambiguous database/slug ownership, or
  explicit current manifest exclusions; do not carry historical directory
  exclusions forward. Worktrees share the main checkout's database and
  reconciliation state.
- For eligible repositories, the global launcher at
  `$HOME/.agents/orchestration-console/scripts/github_sync.sh --install-hooks
  [--dry-run] <repo...>` replaces the managed marker block while preserving
  unrelated hook content. Beads installation or upgrade hooks do not own or
  replace these reconciliation semantics.

## Docs L1/L2

- Use Docs L1/L2 when current dependency/API/platform/model behavior matters:
  run `orch-prompts docs-resolve --cwd <repo> --package <name> --topic
  <domain/API keywords>` first. The resolver routes by lockfile package/version,
  queries `@neuledge/context` L1 directly, auto-downloads registry-backed L1 docs
  on miss/stale, and if an exact registry version is unavailable it tries a
  browsed newer-patch L1 package in the same major.minor track before reporting Context7 MCP or
  official-docs fallback. Otherwise state why no docs lookup is needed.
- For L1 keyword queries, use domain terms and API names rather than generic
  verbs; search is keyword/FTS based.
