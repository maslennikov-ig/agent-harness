# Bootstrap Agent Prompt

Copy this prompt into Codex or Claude on a new or stale machine.

```text
Target: universal coding agent running in WSL, Linux, or macOS.
Audience: executor agent with shell access.
Goal: install or update the portable agent harness, then verify Codex/Claude, MCP, Docs L1/L2, Beads, and the private overlay.

Inputs:
- Public core repo: https://github.com/maslennikov-ig/agent-harness.git
- Private overlay repo: git@github.com:maslennikov-ig/agent-harness-private.git
- Preferred source dir: ~/.agent-harness-src

Context:
- This may be a fresh machine with no installed harness skills, so follow this prompt directly.
- The harness has two layers: public installer/core plus optional private overlay.
- Codex and Claude use different agent/plugin surfaces, but both should share the same Docs L1/L2, MCP and Beads workflow.

Success criteria:
- Public repo is cloned or fast-forwarded at ~/.agent-harness-src.
- Private overlay is applied when GitHub SSH access is available; otherwise public bootstrap completes and the missing private access is reported clearly.
- `bin/harness bootstrap --profile full --yes` runs, installs/checks prerequisites, and writes `~/.agent-harness/state/locks/latest-lock.json`.
- `bin/harness doctor` reports component status and actionable warnings.
- Codex and Claude assets are present where the local clients expect them.
- Claude Code has the `orchestration-bridge` plugin installed under `~/.claude/skills/orchestration-bridge` when Claude is used.
- MCP templates include `context` (`@neuledge/context` L1), `context7` fallback, and `playwright`.
- Codex and/or Claude MCP configs register `context`, `context7`, and `playwright` when those clients are installed.
- Docs routing is L1/L2: use `orch-prompts docs-resolve` with lockfile-routed package/version over `@neuledge/context` first; use Context7 MCP or first-party docs only when L1 is missing, stale, or insufficient.
- Beads (`bd`) is available on PATH.
- No plaintext secret file is left behind.

Steps:
1. Detect shell/platform. On WSL, keep shell commands in Linux paths; open any browser URL through Windows only if needed.
2. Ensure basic tools are present or install them with the OS package manager when safe: `git`, `curl`, `python3`, and Node.js/npm with `node --version` and `npx --version`.
3. Clone or update the public harness:
   - If `~/.agent-harness-src/.git` exists: `git -C ~/.agent-harness-src pull --ff-only`
   - Otherwise: `git clone https://github.com/maslennikov-ig/agent-harness.git ~/.agent-harness-src`
4. Run the plan:
   `~/.agent-harness-src/bin/harness plan`
5. Check private overlay access:
   `ssh -T git@github.com`
   If SSH access is configured for `maslennikov-ig/agent-harness-private`, run:
   `~/.agent-harness-src/bin/harness bootstrap --profile full --yes --private git@github.com:maslennikov-ig/agent-harness-private.git`
   If access is missing, run:
   `~/.agent-harness-src/bin/harness bootstrap --profile full --yes`
   and report that private Codex/Claude agents and personal skills were skipped until GitHub access is granted.
6. Run:
   `~/.agent-harness-src/bin/harness doctor`
7. Verify command surfaces:
   - `bd --version`
   - `context --version`
   - `npx --version`
   - `orch-prompts status` if `orch-prompts` is on PATH
   - `orch-prompts docs-context` if `orch-prompts` is on PATH
8. Register MCP servers where clients are installed:
   - Codex:
     `codex mcp get context >/dev/null 2>&1 || codex mcp add context -- context serve`
     `codex mcp get context7 >/dev/null 2>&1 || codex mcp add context7 -- npx -y @upstash/context7-mcp`
     `codex mcp get playwright >/dev/null 2>&1 || codex mcp add playwright -- npx -y @playwright/mcp`
   - Claude:
     `claude mcp get context >/dev/null 2>&1 || claude mcp add --scope user context -- context serve`
     `claude mcp get context7 >/dev/null 2>&1 || claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp`
     `claude mcp get playwright >/dev/null 2>&1 || claude mcp add --scope user playwright -- npx -y @playwright/mcp`
   Skip the client-specific commands for clients that are not installed and report the skip.
9. Verify MCP visibility where clients are installed:
   - Codex: `codex mcp list` if `codex` is on PATH.
   - Claude: `claude mcp list`, `claude plugin list`, and `claude plugin validate ~/.claude/skills/orchestration-bridge` if `claude` is on PATH.
   If either client is missing, report that the harness assets were installed but that client-specific runtime verification was skipped.
10. For a project repo, initialize local orchestration only when asked:
   `~/.agent-harness-src/bin/harness init-project /path/to/repo`

Constraints:
- Do not commit or print plaintext secrets. Use `bin/harness secrets init|check` for encrypted overlay secrets.
- Prefer fast-forward pulls. Stop and report if any repo is diverged.
- Do not overwrite unmanaged user files outside harness-managed paths.
- Do not route dependency docs as Context7-first. The required order is Docs L1 via `@neuledge/context`, then Context7 or first-party fallback.

Output:
- Short install/update summary.
- Commands run and final status.
- Private overlay applied or skipped.
- Doctor warnings, if any.
- Lock snapshot path.
- MCP/Docs L1/L2/Beads verification results.
- Next action for missing GitHub SSH, missing client binaries, or missing OS prerequisites.

Stop:
- Stop if public repo history is diverged, private repo access requires credentials, bootstrap detects secret-like plaintext during export, or a prerequisite installer needs interactive OS access that the user has not approved.
```
