# Orchestration Bridge

Claude Code CLI plugin for the shared orchestration workflow.

Target runtime: Claude Code CLI from the VS Code integrated terminal on WSL.

Current version: `0.7.0`. Model/effort routing targets Claude Code `2.1.242+`,
where `/tasks` reports each subagent's effective model and effort.

Install from this repository with:

```bash
./scripts/install_claude_plugin.sh
claude plugin validate ~/.claude/skills/orchestration-bridge
claude plugin list
```

The installer syncs this plugin and merges the managed
`shared-orchestration/v1` kernel plus the prompt-free stage-routing block into:

```text
$HOME/.claude/skills/orchestration-bridge
$HOME/.claude/CLAUDE.md
```

The plugin does not store MCP credentials or API keys. Use `claude mcp add`
from the integrated terminal for local MCP configuration.

## Quick Start

1. Install and validate the plugin (commands above).
2. For medium/complex work, invoke `orchestration-bridge:orchestrator-stage`
   (or use the `/stage <task>` command; prompt cards from the orchestration
   console do this for you). Its small router loads only the stage reference
   required by the next decision. The root executes work it already holds
   the context for, including medium work, and delegates a stream only for a
   concrete parallel, context, specialist, or write-isolation benefit. The
   root retains coordination, shared decisions, integration, final acceptance,
   and delivery. If delegation is unavailable, work continues locally.
   Risk-triggered TDD stays inside its focused red-green target.
3. Inline same-session Agent prompts use the compact `goal`, `write_zone`,
   `verification`, and `stop` contract directly. They need neither
   `prompt-authoring` nor prompt-check, and no per-call Agent hook is installed.
4. Use `orchestration-bridge:prompt-authoring` plus
   `orch-prompts prompt-check --runtime claude` only for portable, background,
   cross-runtime, and manual-handoff prompts.
5. Before claiming completion, run `orchestration-bridge:closeout`
   (closeout-lite for the medium tier).

## Skills

| Skill | Use for |
|---|---|
| `orchestrator-stage` | Medium/complex work: benefit-gated bounded delegation, qualified parallelism, verification, closeout |
| `prompt-authoring` | Drafting/reviewing/repairing portable, background, cross-runtime, or manual-handoff prompts |
| `test-pass` | Risk-based verification pass: repo checks, unit/build, browser/E2E, smoke |
| `closeout` | One final acceptance set, docs-reviewed / graph-reviewed, Beads update before the final answer |
| `docs-context` | Inspecting or refreshing the Docs L1/L2 stack |
| `dependency-docs-upgrade` | Verifying dependency upgrade diffs against Docs L1, Context7 as fallback |
| `cleanup-audit` | Read-only audit of stale branches, worktrees, sessions, and runtime leftovers |
| `graphify-project` | Local project knowledge graph: read report, focused queries, no auto git-hooks |
| `system-stability` | Diagnostics for Claude CLI, VS Code/WSL, MCP, hooks; no config mutation |

## Agents

| Agent | Role | Writes |
|---|---|---|
| `mechanical-worker` | Narrow mechanical or repetitive work | assigned write zone |
| `worker` | One bounded substantive execution stream with a write zone and stop rules | assigned write zone; read-only is valid |
| `complex-worker` | One bounded complex or risk-sensitive execution stream | assigned write zone; read-only is valid |
| `correctness-reviewer` | Bugs, regressions, security issues, missing tests, verification gaps | one Markdown artifact only |
| `improvement-reviewer` | Simpler/more maintainable alternatives, reuse/build-vs-buy | one Markdown artifact only |
| `docs-reviewer` | README/CLAUDE.md/AGENTS.md/runbook freshness vs changed behavior | one Markdown artifact only |
| `docs-researcher` | Authoritative version-sensitive docs via Docs Resolver L1 first | one Markdown artifact only |
| `frontend-specialist` | UI, responsiveness, accessibility, browser behavior, visual polish | code when implementing |

Plugin agents use Claude-native `model` and `effort` frontmatter, so a Fable
5.1 lead delegates to actual `claude-opus-5` children. Choose
`mechanical-worker`/low for a narrow mechanical change, `worker`/medium for
normal bounded execution, and `complex-worker`/high for complex or
risk-sensitive execution. A task-specific project, user, or session agent may
use `xhigh` for the hardest work when evaluation or a clear task need supports
it. Prompt wording does not change runtime effort. Read-only reviewers have a
single write exception — creating one Markdown artifact at an explicit
orchestrator-provided path.

Keep Agent prompts to `goal`, `write_zone`, `verification`, and `stop`. Return
compact outcomes and bounded evidence; retain full logs outside model context
and state when output was truncated. These are strong defaults, not hard token,
turn, or agent-count limits.

Agent routing is Claude-native:

- `/agents` shows available subagent definitions from project `.claude/agents/`,
  user `~/.claude/agents/`, enabled plugin `agents/`, and built-ins.
- `claude agents` is agent view for background sessions; do not use it as the
  installed subagent inventory.
- Codex TOML agents are reference material only until converted to Claude
  Markdown or packaged into a Claude plugin.
- `aitmpl` may be used as a Claude-only external agent candidate source. Treat
  dry-run as external code execution that requires current-task authorization,
  then vet generated Markdown and stop before copy/install unless explicitly
  authorized in the current task. Do not install third
  party hooks, MCPs, settings, or slash commands as part of agent routing.

If an already-running Claude session does not see updated skills or agents,
run `/reload-plugins` inside that session.
