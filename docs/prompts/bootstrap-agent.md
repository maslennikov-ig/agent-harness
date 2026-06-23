# Bootstrap Agent Prompt

Copy this prompt into Codex or Claude on a new or stale machine.

```text
Target: universal agent running in WSL, Linux, or macOS.
Audience: executor agent with shell access.
Goal: install or update the portable agent harness from the public core repo and, when available, apply the private encrypted overlay.

Inputs:
- Public core repo: https://github.com/maslennikov-ig/agent-harness.git
- Optional private overlay repo: git@github.com:maslennikov-ig/agent-harness-private.git
- Preferred install dir: ~/.agent-harness-src

Success criteria:
- Public core repo is cloned or fast-forwarded.
- `bin/harness plan` runs successfully.
- `bin/harness bootstrap --profile full --yes --private <private repo>` runs when the private repo is accessible; otherwise public bootstrap runs and the missing private overlay is reported clearly.
- `bin/harness doctor` runs and reports each component as ok/warn with actionable details.
- A lock snapshot exists under `~/.agent-harness/state/locks/latest-lock.json`.
- No plaintext secret file is left behind.

Steps:
1. Detect the platform and shell. On WSL, keep Linux paths in shell commands; open browser URLs through Windows only if a browser is needed.
2. If `~/.agent-harness-src/.git` exists, run `git -C ~/.agent-harness-src pull --ff-only`. Otherwise clone the public repo into `~/.agent-harness-src`.
3. Run:
   `~/.agent-harness-src/bin/harness plan`
4. Try the private overlay path:
   `~/.agent-harness-src/bin/harness bootstrap --profile full --yes --private git@github.com:maslennikov-ig/agent-harness-private.git`
   If the private repo is not accessible, run:
   `~/.agent-harness-src/bin/harness bootstrap --profile full --yes`
   and report that private assets were skipped.
5. Run:
   `~/.agent-harness-src/bin/harness doctor`
6. If this is a source machine where local private agents/skills have changed, update the private overlay repo with:
   `~/.agent-harness-src/bin/harness export-local --scope private --target /path/to/agent-harness-private --yes`
   Then inspect `git diff` in that private repo before committing.

Constraints:
- Never commit plaintext secrets. Use `bin/harness secrets init|edit|check` for encrypted secrets.
- Do not overwrite unmanaged user files outside harness-managed paths.
- Prefer fast-forward git pulls. Stop and report if a repo is diverged.
- If `bd`, `graphify`, or `age` is missing, report it as a prerequisite warning unless the manifest has a supported installer for it.

Output:
- Short status summary.
- Commands run and their final status.
- Any warnings from `doctor`.
- Lock snapshot path.
- Whether private overlay was applied or skipped.

Stop:
- Stop if git history is diverged, a secret-like plaintext file is detected during export, or private repo access fails in a way that requires credentials.
```
