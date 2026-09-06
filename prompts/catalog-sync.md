Use $codex-catalog-sync to refresh the global Codex asset catalog.

Goal: refresh staged and already-promoted Codex catalog assets without changing trust policy or promoting new community assets.

Constraints:
- Read and follow `$codex-catalog-sync` when available.
- Resolve the asset home before running commands. `CODEX_HOME` may be an isolated session home with no catalog in it; use `${CODEX_ASSET_HOME:-${CODEX_HOME:-$HOME/.codex}}` only after confirming the path exists.
- Do not auto-promote catalog-only community assets.
- Do not install, promote, delete, or quarantine assets unless the skill explicitly allows it and policy permits it.
- Do not rely on Desktop automation dispatch when recent runs are stuck or unreliable; prefer the manual runner in that case.

Preflight:
1. Check for stuck/empty automation runs and report whether they affect this refresh.
2. Confirm these paths exist before use:
   - `${CODEX_ASSET_HOME:-${CODEX_HOME}}/bin/sync_catalog.py`
   - `${CODEX_ASSET_HOME:-${CODEX_HOME}}/bin/refresh_promoted_assets.py`
   - `${CODEX_ASSET_HOME:-${CODEX_HOME}}/catalog/`
3. Record current generated_at/counts if available so the refresh result can be compared.

Execution:
```bash
python3 "${CODEX_ASSET_HOME:-$CODEX_HOME}/bin/sync_catalog.py"
python3 "${CODEX_ASSET_HOME:-$CODEX_HOME}/bin/refresh_promoted_assets.py"
```

Success criteria:
- Catalog sync command exits successfully or reports exact sync errors.
- Promoted-asset refresh exits successfully or reports exact refresh errors.
- Final report includes generated_at, staged sources, staged skills, staged agents, installed skills, custom agents, promoted refresh status, and any source sync errors.

Stop rules:
- Stop before any promotion, install, delete, quarantine, trust-mode change, or command using an unresolved asset home.
- If a command fails, do not retry blindly; inspect the smallest relevant log/output and report the blocker.

Output:
- Status: refreshed, warnings, or blocked.
- Commands run, exit status, and evidence source.
- Before/after generated_at and counts when available.
- Errors and next exact safe action.
