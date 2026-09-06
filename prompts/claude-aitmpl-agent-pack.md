Use `orchestration-bridge:orchestrator-stage` (Agent routing in its README and `references/delegation-and-isolation.md`) to select a Claude-native agent for the current task, considering aitmpl only as a Claude-only external candidate source.

Target runtime: Claude Code CLI in the VS Code integrated terminal on WSL.

Goal: choose the smallest useful Claude subagent set for the task without mixing Codex TOML agents into Claude runtime or installing unvetted third-party active components.

Success criteria:
- Installed Claude-native agents are preferred when they fit.
- If no installed agent fits, aitmpl is reported as candidate-only with an approval-required dry-run command.
- Any candidate copy/install path stops before execution unless explicitly authorized in the current task.
- The final answer records selected agents, rejected candidates, and remaining vetting gaps.

Constraints:
- Treat `npx claude-code-templates@latest ... --dry-run` as external code execution, even though it is dry-run.
- Do not run external dry-run commands, copy files, or install agents unless the user explicitly authorizes that action in the current task.
- Do not install aitmpl hooks, MCPs, settings, slash commands, or other active components in this workflow.
- Keep Codex TOML agents as reference material only until converted to Claude Markdown or packaged into a Claude plugin.

Routing order:
1. Prefer installed Claude agents visible through `/agents`: project `.claude/agents/`, user `~/.claude/agents/`, and enabled plugin `agents/`.
2. Prefer `orchestration-bridge` agents for core orchestration review/work: `correctness-reviewer`, `improvement-reviewer`, `docs-researcher`, `docs-reviewer`, `frontend-specialist`, `worker`.
3. Use `orch-prompts claude-aitmpl` to inspect the curated aitmpl candidate baseline when no installed Claude-native agent fits.
4. Treat Codex `$CODEX_HOME/agents/*.toml` as inspiration only. They are not directly spawnable by Claude unless converted to Claude Markdown or packaged into a Claude plugin.

aitmpl policy:
- Use aitmpl only for Claude.
- Consider agents only; do not install aitmpl hooks, MCPs, settings, or slash commands in this workflow.
- Run dry-run first only after current-task authorization, for example `npx claude-code-templates@latest --agent security/security-auditor --dry-run`.
- Inspect the generated Markdown agent frontmatter and body before installation or copying.
- Verify `name`, `description`, `tools`, `model`, write permissions, and whether the agent asks for hidden/unbounded delegation.
- Copy or install only after explicit current-task approval.
- Prefer project `.claude/agents/` for repo-specific agents and `~/.claude/agents/` for personal cross-project agents.
- Promote stable vetted agents into a versioned Claude plugin rather than leaving ad hoc copies scattered across projects.

Output:
- Selected installed Claude agent(s), or `none`.
- aitmpl candidate(s) considered with dry-run command(s), or `none`.
- Vetting result: accepted/rejected/deferred with reason.
- Installation target if accepted.
- Stop before running install commands unless explicitly authorized.

Stop rules:
- Stop before any external `npx` dry-run unless current-task authorization is present.
- Stop before copying or installing any agent file unless current-task authorization is present.
- Stop and ask if the candidate includes hooks, MCP servers, settings changes, slash commands, broad write permissions, secrets, or hidden/unbounded delegation.
