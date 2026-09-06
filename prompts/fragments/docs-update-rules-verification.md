Rules:
- Keep docs code-faithful, compact, and useful to the next operator or developer.
- Prefer updating the smallest existing file/section; create new docs only when there is a durable reader and no good existing home.
- Include exact commands, paths, env names, and limitations when they matter.
- Separate confirmed facts from inference. Do not document planned behavior as shipped behavior.
- Do not touch unrelated docs or reformat broad files.

Verification:
- Check links/paths/commands you changed where practical.
- Run repo docs/lint/build checks when available; otherwise explain why no docs-specific check exists.
- Report `docs-reviewed: updated - <what changed>` or `docs-reviewed: no-change-needed - <reason>`.
