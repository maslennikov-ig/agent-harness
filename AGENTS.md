# Agent Harness Rules

- This repo is public-core only. Do not commit real secrets, local state, `.beads/`, decrypted overlay files, logs, caches, or machine-specific config.
- Keep the bootstrap self-contained: Python stdlib and POSIX shell only for core install/update/doctor behavior.
- Treat `$CODEX_HOME`, `$AGENTS_HOME`, `$CLAUDE_HOME`, and `$HARNESS_HOME` as configurable; do not hardcode one machine's paths.
- Managed updates may overwrite only declared managed paths and must create backups before replacing existing content.
- Private overlay support must keep plaintext secrets temporary, `0600` where possible, and deleted after use.
- Run `python3 -m unittest discover -s tests -v`, `python3 -m harness_core.cli plan --json`, and `git diff --check` before claiming completion.

