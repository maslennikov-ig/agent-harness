Use $orchestrator-stage for a dependency target/LTS upgrade inspection.

Goal: verify that dependency changes and local documentation packages stay in sync before merge.

Workflow:
1. Inspect `git diff` and lockfile changes first. Identify changed production dependencies and their old/new exact versions.
<!-- fragment:docs-upgrade-workflow-steps -->
2. For each changed dependency, derive the lockfile-routed docs target as `ecosystem/name@exact-version` and the comparison track as `major.minor`.
3. Run Docs Resolver first: `orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<domain API keywords>'`. Pass `--version <exact-version>` only when the lockfile version is outside the current repo root or the resolver cannot infer it.
4. Treat resolver `l1-hit` as the authoritative local `@neuledge/context` path. The selected L1 docs package must be the same version as, or newer than, the highest target dependency version in that major.minor track.
<!-- /fragment:docs-upgrade-workflow-steps -->
5. If the resolver reports a fallback track and cannot auto-download matching L1 docs, prepare the exact safe command to update it:
   - registry package: `context install <ecosystem/name> <target-version>`
   - source docs: `context add <source> --name <name> --pkg-version <target-version>`
6. Fall back to Context7 MCP only as L2 when Docs Resolver reports L1 missing, stale, cross-track, floating, or insufficient after the local/auto-download attempt. Do not exceed free-tier limits; avoid bulk fallback checks.
7. Restart the relevant MCP client only when server visibility must be refreshed; do not treat the current thread's missing tools as definitive evidence.

Documentation block for agents:
- L1: Docs Resolver over `@neuledge/context`, local/global, version-routed by lockfile, with registry-backed auto-download on miss/stale.
- L2: Context7 MCP fallback, key from `CONTEXT7_API_KEY`, never hardcoded.
- Resolver topic wording must use domain terms and API names, not generic verbs, because L1 search is keyword/FTS based.

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
