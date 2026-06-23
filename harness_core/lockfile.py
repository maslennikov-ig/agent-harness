from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LockSnapshot:
    components: list[dict[str, Any]]
    created_at: str
    schema_version: int = 1

    @classmethod
    def create(cls, components: list[dict[str, Any]]) -> "LockSnapshot":
        normalized = []
        for component in components:
            normalized.append({
                "name": component.get("name", ""),
                "type": component.get("type", ""),
                "target": str(component.get("target", "")),
                "version": str(component.get("version", "")),
                "status": component.get("status", "unknown"),
            })
        return cls(
            components=normalized,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "components": self.components,
        }

    def write(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
