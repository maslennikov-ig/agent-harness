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

Do not commit plaintext secret files.
