from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    pass


def _expand(value: str, env: dict[str, str]) -> str:
    expanded = value
    for key, replacement in env.items():
        expanded = expanded.replace("${" + key + "}", replacement)
    return os.path.expanduser(expanded)


def _command_list(raw: Any) -> list[list[str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ManifestError("command fields must be lists")
    result: list[list[str]] = []
    for command in raw:
        if isinstance(command, str):
            result.append([command])
        elif isinstance(command, list) and all(isinstance(part, str) for part in command):
            result.append(command)
        else:
            raise ManifestError(f"invalid command entry: {command!r}")
    return result


@dataclass(frozen=True)
class Component:
    name: str
    type: str
    target: Path | str | None = None
    source: Path | str | None = None
    ref: str = "latest"
    install: list[list[str]] = field(default_factory=list)
    doctor: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    components: list[Component]
    path: Path

    @classmethod
    def load(cls, path: str | Path, env: dict[str, str] | None = None) -> "Manifest":
        manifest_path = Path(path)
        base_dir = manifest_path.resolve().parent
        env_map = dict(os.environ)
        env_map.setdefault("HARNESS_REPO", str(base_dir))
        if env:
            env_map.update(env)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema_version = int(data.get("schema_version", 1))
        components: list[Component] = []
        for item in data.get("components", []):
            if not isinstance(item, dict):
                raise ManifestError("component entries must be objects")
            name = item.get("name")
            component_type = item.get("type")
            if not name or not component_type:
                raise ManifestError("component entries need name and type")
            target = item.get("target")
            source = item.get("source")
            source_path = Path(_expand(source, env_map)) if isinstance(source, str) and component_type in {"copy_tree", "git"} else source
            if isinstance(source_path, Path) and not source_path.is_absolute():
                source_path = base_dir / source_path
            components.append(Component(
                name=str(name),
                type=str(component_type),
                target=Path(_expand(target, env_map)) if isinstance(target, str) and component_type != "binary" else target,
                source=source_path,
                ref=str(item.get("ref", "latest")),
                install=_command_list(item.get("install")),
                doctor=list(item.get("doctor") or []),
                raw=item,
            ))
        return cls(schema_version=schema_version, components=components, path=manifest_path)

    def component(self, name: str) -> Component:
        for component in self.components:
            if component.name == name:
                return component
        raise KeyError(name)
