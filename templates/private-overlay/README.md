# Private Overlay Template

Use a separate private repository for personal prompts, agents, preferences, and encrypted secrets.

Recommended layout:

```text
private/
  codex/agents/
  codex/skills/
  claude/agents/
  claude/settings.templates/
overlay.manifest.json
secrets.enc.json
```

Create encrypted secrets:

```bash
harness secrets init --file secrets.enc.json --set OPENAI_API_KEY='<value>'
```

Refresh this overlay from the current machine:

```bash
scripts/update-from-local.sh
git diff
git add private overlay.manifest.json
git commit -m "Update private harness overlay"
git push
```

Do not commit plaintext secret files.
