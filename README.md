# Agent Harness

Portable bootstrap for a Codex + Claude agent workflow: orchestration console,
generic skills and agents, MCP templates, Beads, Graphify, and private encrypted
overlays.

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
  installed through its own `scripts/install.sh`.
- `codex-public-skills`: copied into `$AGENTS_HOME/skills`.
- `codex-public-agents`: copied into `$CODEX_HOME/agents`.
- `mcp-public-templates`: copied into `$HARNESS_HOME/mcp/templates`.
- `bd`, `graphify`, and `age`: checked by doctor as machine prerequisites.

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
`git diff` in the target repo before committing.

## Private Overlay And Secrets

Use a separate private repo for personal assets:

```text
private/
  codex/agents/
  codex/skills/
  claude/agents/
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
