---
name: dependency-docs-upgrade
description: "Use when verifying dependency upgrade diffs against version-routed Docs L1 packages, with Context7 only as fallback."
---

# Dependency Docs Upgrade

1. Inspect `git diff` and lockfile changes.
2. Identify changed production dependencies and exact old/new versions.
3. Derive tracks as `ecosystem/name@major.minor`.
4. Run Docs Resolver first: `orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<domain API keywords>'`, adding `--version <exact-version>` only when lockfile inference is unavailable.
5. Resolver `l1-hit` must select a local `@neuledge/context` package that is the same version as, or newer than, the highest dependency version in the track.
6. If Resolver reports a fallback track and cannot auto-download matching L1 docs, prepare `context install <ecosystem/name> <target-version>` or `context add <source> --name <name> --pkg-version <target-version>`.
7. Use Context7 MCP only when Resolver reports L1 missing, stale, cross-track, floating, or insufficient after local lookup/auto-download.
Close with `docs-reviewed: updated` or `docs-reviewed: no-change-needed` and the concrete dependency/docs reason.
