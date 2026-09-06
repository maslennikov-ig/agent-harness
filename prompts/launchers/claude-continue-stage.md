Use `orchestration-bridge:orchestrator-stage` to continue the current Claude task.

Goal: recover current truth and finish the same cohesive outcome without duplicate work or verification.

Context: use the existing task, diff, artifacts, and acceptance receipt; replan only at a material boundary.

Output: current state, remaining work, blockers, reused evidence, and next action.

Stop: ask only on qualified ambiguity, ownership conflict, plugin/settings mutation, unsafe scope expansion, or destructive/remote/live action.
