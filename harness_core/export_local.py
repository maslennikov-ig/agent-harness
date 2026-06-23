from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


class ExportLocalError(ValueError):
    pass


@dataclass(frozen=True)
class ExportSource:
    name: str
    source: Path
    target: Path


@dataclass(frozen=True)
class ExportResult:
    scope: str
    target: Path
    copied: int
    skipped_sources: list[str]

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "target": str(self.target),
            "copied": self.copied,
            "skipped_sources": self.skipped_sources,
        }


SKIP_DIR_NAMES = {
    ".git",
    ".harness",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "graphify-out",
    "node_modules",
    "venv",
    ".venv",
}
SKIP_FILE_NAMES = {".DS_Store"}
SECRET_PATTERNS = [
    ("openai-style-token", re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("anthropic-token", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("assignment-token", re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}")),
]


PRIVATE_OVERLAY_MANIFEST = {
    "schema_version": 1,
    "components": [
        {
            "name": "private-codex-agents",
            "type": "copy_tree",
            "source": "${HARNESS_REPO}/private/codex/agents",
            "target": "${CODEX_HOME}/agents",
        },
        {
            "name": "private-codex-skills",
            "type": "copy_tree",
            "source": "${HARNESS_REPO}/private/codex/skills",
            "target": "${AGENTS_HOME}/skills",
        },
        {
            "name": "private-claude-agents",
            "type": "copy_tree",
            "source": "${HARNESS_REPO}/private/claude/agents",
            "target": "${CLAUDE_HOME}/agents",
        },
    ],
}


def export_local(scope: str, target: str | Path, yes: bool = False, env: dict[str, str] | None = None) -> ExportResult:
    if not yes:
        raise ExportLocalError("export-local is write-capable; pass --yes after reviewing the target path")
    active_env = env or os.environ
    target_path = Path(target).expanduser().resolve()
    if scope == "private":
        return export_private(target_path, active_env)
    if scope == "public":
        return export_public(target_path, active_env)
    raise ExportLocalError(f"unknown export scope: {scope}")


def export_private(target: Path, env: dict[str, str]) -> ExportResult:
    codex_home = Path(env.get("CODEX_HOME", str(Path.home() / ".codex")))
    agents_home = Path(env.get("AGENTS_HOME", str(Path.home() / ".agents")))
    claude_home = Path(env.get("CLAUDE_HOME", env.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))))
    sources = [
        ExportSource("codex agents", codex_home / "agents", target / "private" / "codex" / "agents"),
        ExportSource("codex skills", agents_home / "skills", target / "private" / "codex" / "skills"),
        ExportSource("claude agents", claude_home / "agents", target / "private" / "claude" / "agents"),
    ]
    result = write_export(scope="private", target=target, sources=sources)
    ensure_private_overlay_manifest(target)
    return result


def export_public(target: Path, env: dict[str, str]) -> ExportResult:
    codex_home = Path(env.get("CODEX_HOME", str(Path.home() / ".codex")))
    agents_home = Path(env.get("AGENTS_HOME", str(Path.home() / ".agents")))
    sources = [
        ExportSource(
            "public harness skill",
            agents_home / "skills" / "harness-bootstrap",
            target / "assets" / "codex" / "skills" / "harness-bootstrap",
        ),
        ExportSource(
            "public harness agent",
            codex_home / "agents" / "harness-tooling-engineer.toml",
            target / "assets" / "codex" / "agents" / "harness-tooling-engineer.toml",
        ),
    ]
    return write_export(scope="public", target=target, sources=sources)


def write_export(scope: str, target: Path, sources: list[ExportSource]) -> ExportResult:
    plans: list[tuple[Path, Path]] = []
    skipped = []
    for item in sources:
        if not item.source.exists():
            skipped.append(item.name)
            continue
        plans.extend(collect_files(item.source, item.target))
    for src, _dst in plans:
        assert_no_secret_like_content(src)
    copied = 0
    for src, dst in plans:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.is_file() and src.read_bytes() == dst.read_bytes():
            continue
        shutil.copy2(src, dst)
        copied += 1
    return ExportResult(scope=scope, target=target, copied=copied, skipped_sources=skipped)


def collect_files(source: Path, target: Path) -> list[tuple[Path, Path]]:
    if source.is_file():
        return [(source, target)]
    files = []
    for src in sorted(source.rglob("*")):
        if not src.is_file():
            continue
        if should_skip(src, source):
            continue
        files.append((src, target / src.relative_to(source)))
    return files


def should_skip(path: Path, root: Path) -> bool:
    if path.name in SKIP_FILE_NAMES:
        return True
    relative = path.relative_to(root)
    return any(part in SKIP_DIR_NAMES for part in relative.parts)


def assert_no_secret_like_content(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise ExportLocalError(f"secret-like content in {path}: {name}")


def ensure_private_overlay_manifest(target: Path) -> None:
    manifest = target / "overlay.manifest.json"
    if manifest.exists():
        return
    target.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(PRIVATE_OVERLAY_MANIFEST, indent=2) + "\n", encoding="utf-8")
