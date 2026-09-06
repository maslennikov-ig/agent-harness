Use $codex-catalog-sync for Codex catalog refresh.

Goal: safely refresh staged assets and promoted assets so routing sees current installed skills/agents without auto-promoting unvetted community assets.

Must not forget: prefer installed assets first; sync catalog before relying on stale staged results; use asset_vetter before external/catalog-only promotion; do not install hooks/MCP/settings.

Output: sync commands/evidence, staged/promoted counts, source errors, assets refreshed, blockers, recommended follow-ups.

Stop: ask before promoting catalog-only assets, installing community code, changing runtime config, deleting assets, or running external commands outside the sync policy.
