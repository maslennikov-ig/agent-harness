from __future__ import annotations

from copy import deepcopy
from typing import Any


def merge_mcp_config(existing: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    """Merge MCP templates without overwriting user-defined servers/settings."""
    merged = deepcopy(existing)
    merged_servers = merged.setdefault("mcpServers", {})
    for name, server in (template.get("mcpServers") or {}).items():
        if name not in merged_servers:
            merged_servers[name] = deepcopy(server)
    for key, value in template.items():
        if key == "mcpServers":
            continue
        merged.setdefault(key, deepcopy(value))
    return merged
