# Runtime portability contract

This distribution must remain useful when the optional local asset catalog,
GitHub reconciliation, and the author's Orchestration Console path are absent.
Local Beads tracking, installed skills, and native custom agents are the
baseline. Optional integrations add discovery or synchronization; their
absence does not invalidate local work.

## Native discovery from first-party documentation

### Codex

- OpenAI's [Build skills](https://developers.openai.com/codex/skills) page says
  Codex discovers repository skills from `.agents/skills/` between the current
  directory and repository root, and user skills from
  `$HOME/.agents/skills/`. It detects skill changes automatically, with a
  restart suggested only when an update does not appear.
- OpenAI's [Subagents](https://developers.openai.com/codex/subagents) page says
  personal custom agents are standalone TOML files in `~/.codex/agents/` and
  project agents are in `.codex/agents/`. Each requires `name`, `description`,
  and `developer_instructions`. The page explicitly warns that the custom-agent
  format may evolve.
- These pages do not establish arbitrary `AGENTS_HOME` or `CODEX_HOME`
  overrides as native discovery locations. A portable installer may use
  `$HOME/.agents/skills` and `~/.codex/agents`, or project-local native paths,
  without extra registration. Any configurable-home behavior needs a separate
  client test and must not be claimed from these sources.

### Claude Code

- Anthropic's [Plugins reference](https://code.claude.com/docs/en/plugins-reference)
  defines a plugin root with optional `.claude-plugin/plugin.json` and sibling
  `skills/` and `agents/` directories. Installed plugins automatically discover
  those components. The manifest's `name` supplies the namespace.
- Anthropic's [CLI reference](https://code.claude.com/docs/en/cli-usage) and
  [Create plugins](https://code.claude.com/docs/en/plugins) page document
  `claude --plugin-dir <plugin-root>` for the current session. Each flag takes
  one path and the flag may be repeated to load multiple plugins. Plugin skills
  use `/plugin-name:skill-name`; agents appear in `/agents`.
- Copying a complete plugin tree under `~/.claude/skills/` is not documented as
  plugin registration. Standalone user skills use
  `~/.claude/skills/<skill-name>/SKILL.md`; a nested
  `orchestration-bridge/skills/...` tree must therefore be installed or loaded
  as a plugin, not treated as proof of native discovery merely because the
  files exist.
- The reference includes behavior introduced in Claude Code 2.1.140 and
  2.1.142 for manifest diagnostics and single-root-skill plugins. This package
  uses ordinary root `skills/` and `agents/` directories, but the first external
  test still needs to record the user's Claude Code version.

The portable installer journals complete plugin roots at
`~/.agent-harness/plugins/orchestration-bridge` and
`~/.agent-harness/plugins/superpowers`. Its `harness claude [args...]` wrapper
must invoke the real client with both repeated flags:

```text
claude --plugin-dir ~/.agent-harness/plugins/orchestration-bridge \
  --plugin-dir ~/.agent-harness/plugins/superpowers [args...]
```

This preserves the documented plugin namespaces without changing a user's
Claude marketplace or settings. Loading is session-scoped: only sessions
started through `harness claude` receive these journaled plugins. Plain
`claude` discovery is not claimed.

## Optional local dependencies

Asset routing starts with natively installed skills and agents. A catalog under
`${CODEX_ASSET_HOME:-${CODEX_HOME:-$HOME/.codex}}/catalog` is optional. If its
files or refresh, vetting, and promotion helpers are missing, routing records
the reason and continues with installed assets, a visible built-in agent, or
local execution. It never fabricates or downloads a missing helper.

Beads remains the local task source of truth without GitHub enrollment or
credentials. GitHub reconciliation runs only for an enrolled repository with
available authentication and an installed executable script resolved from:

```text
${ORCHESTRATION_CONSOLE_ROOT:-${AGENTS_HOME:-$HOME/.agents}/orchestration-console}/scripts/github_sync.sh
```

If any condition is absent, record `GitHub sync: skipped - <reason>` after the
successful local Beads operation. Do not create a replacement sync script and
do not mutate a GitHub issue separately.

## User-session verification

Static file checks establish package shape only. They do not prove that a
client loaded a skill or agent. On a fresh user machine, record exact client
versions and perform these checks in new sessions:

1. Start Codex inside the training repository. Confirm the packaged skills are
   visible through `/skills` (or `$` mention), and confirm at least one packaged
   TOML agent can be selected or spawned. Repeat from a nested directory to
   exercise repository skill discovery.
2. Validate both Claude plugin roots, start a fresh session through
   `harness claude`, and inspect session initialization or debug output to
   confirm both paths loaded without plugin errors. Confirm
   `/orchestration-bridge:orchestrator-stage` is listed, one bridge agent
   appears in `/agents`, and a namespaced Superpowers skill is visible. Repeat
   with plain `claude` only to confirm the wrapper boundary; do not expect the
   journaled plugins there.
3. Temporarily omit the optional catalog and its helper scripts. Confirm task
   routing uses an installed asset or continues locally without a missing-file
   command.
4. In a repository with local Beads but no GitHub enrollment or credentials,
   create or update a task and confirm local state succeeds with an explicit
   skipped-sync record. Repeat an enrolled authenticated case separately if
   GitHub synchronization is part of the user's authorized scope.
5. Set `ORCHESTRATION_CONSOLE_ROOT` to a non-default checkout and confirm the
   sync command resolves there. Separately verify the `AGENTS_HOME` fallback.

Publication, license review, and real user-session verification remain
separate gates. Installation and `doctor` do not by themselves prove that a
real Codex or Claude session ingested every skill and agent.
