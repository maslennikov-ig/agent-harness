Use $orchestrator-stage for a read-only legacy/dead-code audit.

Goal: find removable legacy code, unused files/exports/dependencies/assets,
stale flags, and obsolete modules; classify without deleting.

Start from real entrypoints. Require `file:line` evidence; static analysis is
only a lead. Adversarially challenge every `safe-delete-candidate`. Deletion
needs explicit approval and a later implementation pass.

Delegate audit streams only for a concrete benefit; otherwise audit directly.
Root integrates the evidence and owns final acceptance.

Output: counts and tables for Safe delete candidates, Needs discussion, Keep,
Blocked/unknown, tooling gaps, approval batches, docs-reviewed, graph-reviewed.

Stop: do not delete, refactor, mutate config/remotes, or run destructive
commands. Ask before public API, data/migration, auth/privacy, billing,
deploy/runtime, generated code, external integrations, or flag-owner decisions.
