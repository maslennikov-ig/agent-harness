Use $orchestration-setup for Codex project initialization.

Goal: initialize or reconcile the repo to the current Codex AGENTS-first baseline with Beads, Superpowers, Docs L1/L2, visible Codex subagents, verification, closeout, and handoff.

Must not forget: run setup decisions for Graphify, dependencies/lockfiles, agents/skills/catalog, Docs L1/L2 readiness, Browser/E2E tooling, secrets/config guard, hooks, and dual-runtime Claude; never pass `--skip-hooks` to `bd init`, enable `export.auto`, and prove the Beads ledger is in sync; keep AGENTS.md compact.

Output: mode, files changed/reviewed, setup decisions table, runtime prerequisites, baseline status, verification evidence, docs-reviewed, graph-reviewed, explicit defers.

Stop: ask before destructive Beads re-init, broad AGENTS rewrites, Graphify git hooks, external extraction, delivery-policy changes, push/PR/deploy.
