# Delegation and Isolation

Root executes work it already holds the context for. Delegate a stream when it
has a concrete benefit: `parallel_latency` (independent work that can run at
the same time), `context_isolation` (large reads or noisy output that would
bloat the root context), `specialist_capability`, or `write_isolation`.
Independence alone is insufficient. If subagents are unavailable, continue
locally; unavailable delegation never blocks the task.

Launch eligible streams together when slots, dependencies, and write isolation
permit, and keep working while they run; step in when a stream drifts or lacks
context. Keep dependent streams sequential, isolate concurrent writers (read-only
streams may share state), and put finite slots on the critical path.
Accept no stream from a completion event alone: review its artifact or diff
and evidence, and return in-scope corrections to the same owner.

A Fable 5.1 lead may retain context-coupled or critical work together with task
framing, decisions, coordination, integration, and user communication at the
root. It may delegate bounded execution to the plugin's Opus 5 agents when one
of the benefits above applies, and keep independent lead work moving while they
run.

Choose the native agent by task shape. The shipped agents use the full
`claude-opus-5` model ID and set actual runtime effort in frontmatter:

- `mechanical-worker` + `low` for a narrow mechanical change;
- `worker` + `medium` for normal bounded execution;
- `complex-worker` + `high` for complex or risk-sensitive execution.

Specialists use the same Opus 5 model with the effort recorded in their
frontmatter. Reserve `xhigh` for the hardest work and expose it through a
task-specific native agent when evaluation or a clear task need supports the
extra cost. Do not try to change effort with prompt wording. Polling, file
discovery, formatting, and routine test monitoring stay with the lead or local
tools.

A same-session prompt supplies the goal, the assigned `write_zone`, focused
verification, and stop conditions; copy neither transcript history nor
reusable rules. Use Claude-native project, user, or plugin agents visible
through `/agents`; Codex TOML agents are not runnable Claude agents.
Prompt-check applies only to background, portable, cross-runtime, or durable
manual handoffs.

Return bounded output with a truncation signal: exit status, counts, first
actionable failure, and a short tail. Keep full logs outside model context and
never infer a pass or no findings from truncated output.

Prompt cards are root-only exact-ID fallbacks for a known workflow or explicit
user request. Use `orch-prompts prompt-get --id <id>`; do not browse the panel,
ask children to query it, or let a card authorize delegation or verification.
