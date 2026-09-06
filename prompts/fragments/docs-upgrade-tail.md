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
