---
name: using-superpowers
description: Use at conversation start to select applicable skills before task work.
---

# Using Superpowers

At task start, compare the request with available skill descriptions.
Invoke a skill when the user names it or its trigger clearly matches.
Do not load a skill speculatively because it is installed, visible, or might
become useful.

Read each selected skill's current instructions before acting and announce its
purpose briefly. When several apply, use the smallest set that covers the task;
process skills precede implementation skills only when both triggers match.

Dispatched subagents executing a specific task do not reload this bootstrap.

User and repository instructions take precedence over skills. Report a real
conflict instead of expanding the workflow.

Read a harness reference only when the selected work uses its special
capability:

- Codex subagents, worktrees, or branch finishing:
  `references/codex-tools.md`
- Pi: `references/pi-tools.md`
- Antigravity: `references/antigravity-tools.md`
- Hermes Agent: `references/hermes-tools.md`
