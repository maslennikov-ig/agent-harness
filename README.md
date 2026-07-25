# Agent Harness

Portable bootstrap for a Codex + Claude agent workflow: orchestration console,
generic skills and agents, Docs L1/L2 routing, MCP templates, Beads, Graphify,
and private encrypted overlays.

The harness is split into two GitHub layers:

- **Public core**: this repo. It contains installer/update/doctor code,
  public templates, generic skills/agents, and no secrets.
- **Private overlay**: your private repo. It can contain personal agents,
  personal prompts, preferences, and encrypted secrets.

If you want another agent to install or update the whole harness, copy the
prompt from [`docs/prompts/bootstrap-agent.md`](docs/prompts/bootstrap-agent.md).

## Install Or Update

Fresh machine:

```bash
git clone https://github.com/maslennikov-ig/agent-harness.git ~/.agent-harness-src
~/.agent-harness-src/bin/harness plan
~/.agent-harness-src/bin/harness bootstrap --profile full --yes
~/.agent-harness-src/bin/harness doctor
```

Existing machine with stale components:

```bash
cd ~/.agent-harness-src
git pull --ff-only
bin/harness update --yes
bin/harness doctor
```

The default model is **latest + lock snapshot**: install/update pulls the latest
configured upstream sources, then writes a lock snapshot with installed
versions and component health.

## Commands

```bash
harness plan
harness bootstrap --yes
harness update --yes
harness doctor
harness rollback --lock ~/.agent-harness/state/locks/latest-lock.json
harness init-project /path/to/repo
harness export-local --scope private --target /path/to/agent-harness-private --yes
harness secrets init --file secrets.enc.json --set OPENAI_API_KEY='<value>'
harness secrets check --file secrets.enc.json
```

`bootstrap` and `update` are idempotent. They write only declared managed paths.
When a managed destination file already exists with different content, harness
backs it up under `~/.agent-harness/state/managed/backups/` before replacing it.

## Managed Components

The default manifest manages:

- `orchestration-console`: cloned from `codex-orchestration-console`, then
  installed through its own `scripts/install.sh`; the Claude Code
  `orchestration-bridge` plugin is also synced into `$CLAUDE_HOME/skills`.
- `codex-public-skills`: copied into `$AGENTS_HOME/skills`.
- `codex-public-agents`: copied into `$CODEX_HOME/agents`.
- `mcp-public-templates`: copied into `$HARNESS_HOME/mcp/templates`.
- `context`: the local Docs L1 MCP server from `@neuledge/context`.
- `context7` and `playwright`: npx-backed MCP templates for fallback docs and
  browser automation.
- `bd`, `graphify`, `age`, `node`, and `npx`: installed or checked as machine
  prerequisites.

Docs lookup is two-tiered: agents should use `orch-prompts docs-resolve` first,
which routes by lockfile package/version over local `@neuledge/context` L1
packages. Context7 MCP or first-party docs are fallback only when L1 is missing,
stale, or insufficient.

Register MCP servers when the client is installed:

```bash
codex mcp get context >/dev/null 2>&1 || codex mcp add context -- context serve
codex mcp get context7 >/dev/null 2>&1 || codex mcp add context7 -- npx -y @upstash/context7-mcp
codex mcp get playwright >/dev/null 2>&1 || codex mcp add playwright -- npx -y @playwright/mcp

claude mcp get context >/dev/null 2>&1 || claude mcp add --scope user context -- context serve
claude mcp get context7 >/dev/null 2>&1 || claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp
claude mcp get playwright >/dev/null 2>&1 || claude mcp add --scope user playwright -- npx -y @playwright/mcp
```

The installer preserves unmanaged local files in those target directories.

## Updating From Local Changes

Local agents and skills change over time. Use `export-local` from the source
machine to refresh the repo layer you want to preserve:

```bash
# Personal/private assets only.
harness export-local --scope private --target /path/to/agent-harness-private --yes

# Conservative public allowlist, currently harness-owned public skill/agent.
harness export-local --scope public --target /path/to/agent-harness --yes
```

`export-local` scans text files for obvious token/key patterns before writing.
If it finds secret-like content, it stops before copying. Always inspect
`git diff` in the target repo before committing. Personal Claude skills are
exported from `$CLAUDE_HOME/skills`; the Harness-managed
`orchestration-bridge` plugin is excluded because the public console owns it.

## Private Overlay And Secrets

Use a separate private repo for personal assets:

```text
private/
  codex/agents/
  codex/skills/
  claude/agents/
  claude/skills/
  claude/settings.templates/
overlay.manifest.json
secrets.enc.json
```

Plain private repo files may contain personal preferences, but real tokens and
API keys should be encrypted:

```bash
harness secrets init --file secrets.enc.json --set ANTHROPIC_API_KEY=...
harness secrets check --file secrets.enc.json
```

The v1 vault is password-based and self-contained in Python stdlib so bootstrap
works before dependencies are installed. `age` is still a recommended machine
prerequisite and is checked by `harness doctor`.

## Project Init

Project setup is separate from machine setup:

```bash
harness init-project /path/to/repo
```

This copies only project-local baseline files such as `AGENTS.md` and `.codex/`
templates. It does not mutate global Codex, Claude, MCP, Beads, or Graphify
state.

## Development

Run tests:

```bash
python3 -m unittest discover -s tests -v
python3 -m harness_core.cli plan --json
git diff --check
```

CI runs on Ubuntu and macOS. WSL is a first-class supported target and should be
smoke-tested manually before release.
