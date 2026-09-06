Use `orchestration-bridge:dependency-docs-upgrade` for a dependency target/LTS upgrade inspection in Claude Code CLI.

Goal: verify that dependency changes and local documentation packages stay in sync before merge.

Workflow:
1. Inspect `git diff` and lockfile changes first. Identify changed production dependencies and old/new exact versions.
<!-- fragment:docs-upgrade-workflow-steps -->
2. For each changed dependency, derive the lockfile-routed docs target as `ecosystem/name@exact-version` and the comparison track as `major.minor`.
3. Run Docs Resolver first: `orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<domain API keywords>'`. Pass `--version <exact-version>` only when the lockfile version is outside the current repo root or the resolver cannot infer it.
4. Treat resolver `l1-hit` as the authoritative local `@neuledge/context` path. The selected L1 docs package must be the same version as, or newer than, the highest target dependency version in that major.minor track.
<!-- /fragment:docs-upgrade-workflow-steps -->
5. If Resolver reports a fallback track and cannot auto-download matching L1 docs, prepare the exact safe command: `context install <ecosystem/name> <target-version>` or `context add <source> --name <name> --pkg-version <target-version>`.
6. Fall back to Context7 MCP only when Docs Resolver reports L1 missing, stale, cross-track, floating, or insufficient after the local/auto-download attempt. Do not make Context7 the primary path.

Claude/VS Code notes:
- Add MCP servers from the integrated terminal with `claude mcp add`; manage them in the chat panel with `/mcp` when needed.
- If the Claude VS Code panel lacks a CLI-only capability, run the command directly in the integrated terminal.

<!-- fragment:docs-upgrade-tail -->
Success criteria:
- Every changed production dependency has an exact target version from the lockfile.
- Every docs track is `ok` or explicitly marked `fallback`; cross-track and floating docs are fallback conditions.
- Every registry-backed fallback track has a safe `context install` or `context add` command.
- Closeout reports `docs-reviewed: updated` or `docs-reviewed: no-change-needed` with the concrete dependency/docs reason.

Stop rules:
- Commit only when delivery is in scope and final acceptance passes. Stop before installing packages or editing project docs outside the accepted scope.
- Stop if the target dependency version cannot be resolved from lockfiles.

Output:
- Changed dependencies and exact old/new versions.
- Docs track status for each dependency: ok, fallback, or blocked.
- L1 commands needed, if any, and fallback sources used.
- Verification evidence and `docs-reviewed` result.
<!-- /fragment:docs-upgrade-tail -->
