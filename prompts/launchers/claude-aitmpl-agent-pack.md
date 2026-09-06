Use `orchestration-bridge:orchestrator-stage` (Agent routing in its README and `references/delegation-and-isolation.md`) for Claude-only aitmpl agent selection.

Goal: inspect installed Claude-native agents first, then use `orch-prompts claude-aitmpl` as a candidate list only when no installed agent fits.

Must not forget: aitmpl is Claude-only; dry-run external commands require current authorization; vet before copy/install; do not install hooks, MCPs, settings, commands, or non-agent assets.

Output: installed agents considered, aitmpl candidates if needed, vetting decision, recommended install target or undecided target, exact dry-run command, stop-before-install note.

Stop: ask before running npx, copying/installing agents, changing Claude settings/plugins, or using candidates for Codex.
