---
name: harness-bootstrap
description: Use when installing, updating, auditing, or repairing the portable agent harness across Codex, Claude, MCP, Beads, Graphify, and orchestration-console components.
---

# Harness Bootstrap

Use `harness plan`, `harness bootstrap`, and `harness doctor` before changing a machine-level setup.

Rules:
- Keep public assets free of secrets and local runtime state.
- Use managed paths only; do not overwrite unmanaged user files.
- Run `harness doctor` after install/update.
- For project setup, prefer `harness init-project <repo>` over copying global files.

