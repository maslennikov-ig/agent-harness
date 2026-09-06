# Delegation and Isolation

Root executes work it already holds the context for. Delegate a stream when it
has a concrete benefit: `parallel_latency` (independent work that can run at
the same time), `context_isolation` (large reads or noisy output that would
bloat the root context), `specialist_capability`, or `write_isolation`.
Independence alone is insufficient. If subagents are unavailable, continue
locally; unavailable delegation never blocks the task.

Launch eligible streams together when slots, dependencies, and write isolation
permit, and keep working while they run; step in when a stream drifts or lacks
context. Keep dependent streams sequential, isolate concurrent writers, and put
finite slots on the critical path. Use visible Codex subagents, not inline
summaries. Accept from artifact/diff and evidence, not completion alone; return
corrections to the same owner unless scope or isolation changed.

The root runs on `gpt-6-astra`. It may keep the highest criticality, most
complex, or context-coupled work when that gives the best outcome. Delegation
is discretionary: choose `role`, `model`, and `reasoning_effort` by the actual
stream, with these starting directions rather than quotas:

- mechanical or repetitive work: `worker`, `gpt-5.6-luna`, usually `low`;
- simpler implementation, exploration, or support: fitting role,
  `gpt-5.6-terra`, usually `medium`;
- complex delegated implementation, integration, or analysis: fitting role,
  `gpt-5.6-sol`, usually `high`.

Adjust the starter when the task or available capability warrants it and record
one task-specific rationale. Routing alone creates no spawn or review. If an
exact model, effort, or role is unavailable, use the closest supported option
or keep the stream with Astra. A specialist role may fix its own reasoning
effort; record that actual configured effort and the fallback reason instead of
claiming the starter was applied.

Native Codex calls pass `fork_turns="none"`. Override only with a task-specific
rationale and when essential facts are not reachable through the nearest
`AGENTS.md`, selected Beads goal, or exact existing reference. This is
guidance, not a context or token cap.

Prompts state `goal`, `write zone`, `verification`, and `stop`. Give writers an
owned zone and preserve other owners' work. Copy neither transcript history nor
reusable rules.

Coalesce routine progress updates while reporting blockers, decisions, material artifacts,
final result, and platform heartbeat. Prefer bounded summarized tool output with
a truncation signal: exit status, counts, first actionable failure, and a short
tail. Keep full logs outside model context. Never infer a pass or no findings
from truncated output: narrow it or expand with a reason.

Prompt cards are root-only exact-ID fallbacks for a known workflow or explicit
request. Use `orch-prompts prompt-get --id <id>`; do not browse the panel, ask
children to query it, or let a card authorize delegation or verification.
