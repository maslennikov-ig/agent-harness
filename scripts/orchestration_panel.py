#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import textwrap
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback.
    tomllib = None


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from orch_panel.beads import ISSUE_LIMIT as BEADS_ISSUE_LIMIT  # noqa: E402
from orch_panel.beads import beads_board_payload  # noqa: E402
from orch_panel.context_policy import (  # noqa: E402
    compose_prompt,
    composition_metadata,
    inspect_kernel_file,
    runtime_kernel_path,
)
from orch_panel.github import issues_payload as github_issues_payload  # noqa: E402
from orch_panel.github import sync_status as github_sync_status  # noqa: E402
from orch_panel.github import tails_pr_payload  # noqa: E402
from orch_panel.prompts_sync import check as fragments_drift_check  # noqa: E402
from orch_panel.radar import radar_row  # noqa: E402
from orch_panel.coordination.safety import redact_sensitive_text  # noqa: E402
from orch_panel.telemetry import stage_telemetry_payload  # noqa: E402
from orch_panel.throughput import throughput_payload  # noqa: E402
from orch_panel.tools import tool_health  # noqa: E402
from simulate_proportional_orchestration import (  # noqa: E402
    REPRESENTATIVE_WORKLOAD,
    simulate as simulate_proportional_orchestration,
)

CONSOLE_DIR = Path(__file__).resolve().parents[1]
PANEL_BUILD_ID = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]
WEB_ROOT = CONSOLE_DIR / "web"


def resolve_web_dir(web_root: Path) -> Path:
    web_dist_dir = web_root / "dist"
    return web_dist_dir if web_dist_dir.is_dir() else web_root


WEB_DIST_DIR = WEB_ROOT / "dist"
WEB_DIR = resolve_web_dir(WEB_ROOT)
PROMPTS_DIR = CONSOLE_DIR / "prompts"
PROMPT_MANIFEST_PATH = PROMPTS_DIR / "manifest.json"
STATE_DIR = CONSOLE_DIR / "state"
USAGE_PATH = STATE_DIR / "usage.json"
USAGE_LOG_PATH = STATE_DIR / "usage-log.jsonl"
NOTES_PATH = CONSOLE_DIR / (
    "state/AGENT_NOTES.md" if (CONSOLE_DIR / "release-manifest.json").is_file()
    else "AGENT_NOTES.md"
)
CLAUDE_AGENT_LIBRARY_DIR = CONSOLE_DIR / "claude-agent-library" / "agents"
CLAUDE_AGENT_CACHE_DIR = STATE_DIR / "claude-agent-library" / "agents"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
CATALOG_RUNNER_NAME = "sync_catalog.py"
DEFAULT_CLAUDE_HOME = Path.home() / ".claude"
DEFAULT_WORKSPACE = Path.home() / "code"
DEFAULT_AGENTS_HOME = Path.home() / ".agents"
PANEL_SETTINGS_SCHEMA = "orchestration-console-settings/v1"

PROMPT_CHECK_RUNTIMES = {"codex", "claude"}
PROMPT_CHECK_PROFILES = {"gpt-6-astra", "fable-5.1", "opus-5"}
PROMPT_CHECK_KINDS = {"worker", "review", "handoff", "question", "fallback", "launcher", "prompt-card"}
# The checker may receive the rendered launcher; source launchers keep their
# separate 1,000-character library guard through task_launcher_chars.
PROMPT_KIND_BUDGETS = {"question": 1500, "handoff": 1500, "worker": 3000, "review": 4500, "fallback": 6000, "launcher": 4500, "prompt-card": 6000}


AITMPL_DOCS_URL = "https://docs.aitmpl.com/"
AITMPL_AGENTS_URL = "https://www.aitmpl.com/agents"
AITMPL_NPM_PACKAGE = "claude-code-templates@latest"
AITMPL_INSTALL_POLICY = "Claude-only, agents-only, external-code dry-run requires current authorization; vet before copy/install; do not auto-install hooks, MCPs, settings, or commands."
AITMPL_VETTING_CHECKLIST = [
    "Confirm dry-run output is a Markdown agent only.",
    "Inspect YAML frontmatter: name, description, tools, model.",
    "Review body for task scope, bounded tool use, and no hidden delegation.",
    "Reject hooks, MCP servers, settings, slash commands, secrets, and broad write permissions.",
    "Before promotion, record resolved package version and generated Markdown sha256.",
    "Stop before copy/install unless explicitly authorized in the current task.",
]
AITMPL_BASELINE_AGENTS = [
    {
        "name": "security-auditor",
        "category": "security",
        "purpose": "General security review and vulnerability assessment.",
    },
    {
        "name": "api-security-audit",
        "category": "security",
        "purpose": "REST/API authentication, authorization, and OWASP API risk review.",
    },
    {
        "name": "frontend-developer",
        "category": "development-team",
        "purpose": "Frontend implementation and review for React, Vue, and Angular projects.",
    },
    {
        "name": "backend-developer",
        "category": "development-team",
        "purpose": "Server-side APIs, service boundaries, and backend implementation.",
    },
    {
        "name": "devops-engineer",
        "category": "development-team",
        "purpose": "Infrastructure, deployment, CI/CD, and runtime operations.",
    },
    {
        "name": "supabase-schema-architect",
        "category": "database",
        "purpose": "PostgreSQL/Supabase schema, migration, RLS, and database architecture review.",
    },
    {
        "name": "dx-optimizer",
        "category": "development-tools",
        "purpose": "Developer workflow, build, test, and local tooling performance optimization.",
    },
    {
        "name": "code-reviewer",
        "category": "development-tools",
        "purpose": "General code quality, maintainability, and correctness review.",
    },
    {
        "name": "technical-writer",
        "category": "documentation",
        "purpose": "Durable technical documentation and operator-facing docs.",
    },
    {
        "name": "ml-engineer",
        "category": "data-ai",
        "purpose": "Machine learning implementation, evaluation, and data workflow review.",
    },
    {
        "name": "data-scientist",
        "category": "data-ai",
        "purpose": "Data analysis, metrics, and modeling workflows.",
    },
]


def env_path(name: str, fallback: Path | None = None) -> Path | None:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else fallback


def first_existing(paths: list[Path], fallback: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return fallback


def codex_home_score(path: Path) -> int:
    if not path.exists():
        return -1
    score = 1
    if (path / "config.toml").exists():
        score += 1
    if (path / "AGENTS.md").exists():
        score += 5
    score += min(50, len(list((path / "agents").glob("*.toml"))) * 2) if (path / "agents").exists() else 0
    score += min(50, len(list((path / "skills").glob("*/SKILL.md")))) if (path / "skills").exists() else 0
    score += min(50, len(list((path / "superpowers" / "skills").glob("*/SKILL.md")))) if (path / "superpowers" / "skills").exists() else 0
    if (path / "catalog" / "assets.json").exists():
        score += 5
    return score


def best_codex_home(paths: list[Path], fallback: Path) -> Path:
    candidates = [path for path in paths if path.exists()]
    if not candidates:
        return fallback
    return max(candidates, key=codex_home_score)


def codex_asset_score(path: Path) -> int:
    """Score a home by the assets a catalog reads, not by the session state.

    `codex_home_score` rewards `AGENTS.md` and `config.toml`, which a dedicated
    runtime home copies to stay a usable Codex home. Only the catalog, its sync
    runner, and the installed skills and agents tell the populated home apart.
    """

    if not path.exists():
        return -1
    score = 0
    if (path / "catalog" / "assets.json").exists():
        score += 5
    if (path / "bin" / CATALOG_RUNNER_NAME).exists():
        score += 3
    score += min(50, len(list((path / "agents").glob("*.toml")))) if (path / "agents").exists() else 0
    score += min(50, len(list((path / "skills").glob("*/SKILL.md")))) if (path / "skills").exists() else 0
    score += min(50, len(list((path / "superpowers" / "skills").glob("*/SKILL.md")))) if (path / "superpowers" / "skills").exists() else 0
    return score


def best_codex_asset_home(paths: list[Path], fallback: Path) -> Path:
    candidates = [path for path in paths if path.exists()]
    if not candidates:
        return fallback
    best = max(candidates, key=codex_asset_score)
    return best if codex_asset_score(best) > 0 else fallback


def windows_codex_homes() -> list[Path]:
    users_root = env_path("CODEX_WINDOWS_USERS_ROOT") or Path("/mnt/c/Users")
    if not users_root.exists():
        return []
    paths = [path for path in users_root.glob("*/.codex") if path.exists()]
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)


def panel_settings_path() -> Path:
    return env_path("ORCH_PANEL_SETTINGS_PATH") or (STATE_DIR / "panel-settings.json")


def panel_settings() -> dict[str, Any]:
    payload = load_json(panel_settings_path(), {})
    if not isinstance(payload, dict) or payload.get("schema_version") != PANEL_SETTINGS_SCHEMA:
        return {}
    return payload


def panel_settings_payload() -> dict[str, Any]:
    stored = panel_settings()
    return {
        "schema_version": PANEL_SETTINGS_SCHEMA,
        "codex_home": str(codex_home()),
        "source": "panel-setting" if stored.get("codex_home") else "environment-or-discovery",
        "codex_asset_home": str(codex_asset_home()),
        "asset_source": "panel-setting" if stored.get("codex_asset_home") else "environment-or-discovery",
    }


def settings_home(payload: dict[str, Any], key: str) -> Path | None:
    raw = str(payload.get(key) or "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{key} must be an absolute path")
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise ValueError(f"{key} is not a directory: {raw}")
    return resolved


def update_panel_settings(payload: dict[str, Any]) -> dict[str, Any]:
    resolved = settings_home(payload, "codex_home")
    if resolved is None:
        raise ValueError("codex_home must be an absolute path")
    stored: dict[str, Any] = {"schema_version": PANEL_SETTINGS_SCHEMA, "codex_home": str(resolved)}
    # Absent means "keep discovering"; the asset home is optional on purpose so
    # a single-home install never has to name the same path twice.
    asset_home = settings_home(payload, "codex_asset_home")
    if asset_home is not None:
        stored["codex_asset_home"] = str(asset_home)
    save_json(panel_settings_path(), stored)
    clear_home_caches()
    with RUNTIME_CACHE_LOCK:
        RUNTIME_CACHE.clear()
    return panel_settings_payload()


@lru_cache(maxsize=1)
def codex_home() -> Path:
    """Resolve the active Codex home once per process.

    Scoring the candidates globs `/mnt/c/Users/*/.codex`, and a single overview
    payload asked for it five times: half of that payload's runtime was the same
    walk across the Windows filesystem, which WSL serves slowly. Callers that
    change `CODEX_HOME` or the candidate set must call `codex_home.cache_clear()`.
    """

    stored = panel_settings().get("codex_home")
    if isinstance(stored, str) and stored:
        configured_home = Path(stored).expanduser()
        if configured_home.is_absolute() and configured_home.is_dir():
            return configured_home.resolve()
    configured = env_path("CODEX_HOME")
    if configured:
        return configured
    return best_codex_home([DEFAULT_CODEX_HOME, *windows_codex_homes()], DEFAULT_CODEX_HOME)


@lru_cache(maxsize=1)
def codex_asset_home() -> Path:
    """Resolve the home that owns the asset catalog and its sync runner.

    The runtime home is deliberately separate: a dedicated `.codex-console`
    keeps App Server sessions, logs, and auth out of the everyday Codex home.
    That separation used to hide the catalog, because the panel read assets out
    of the runtime home and found an empty directory while the populated home
    sat next to it. The runtime home still wins when it carries the assets, so
    a single-home install resolves to exactly one path as before.

    Cached like `codex_home()`; callers that change either home must call both
    `cache_clear()` functions.
    """

    stored = panel_settings().get("codex_asset_home")
    if isinstance(stored, str) and stored:
        configured_home = Path(stored).expanduser()
        if configured_home.is_absolute() and configured_home.is_dir():
            return configured_home.resolve()
    configured = env_path("CODEX_ASSET_HOME")
    if configured:
        return configured
    runtime_home = codex_home()
    candidates = [runtime_home, DEFAULT_CODEX_HOME, *windows_codex_homes()]
    return best_codex_asset_home(candidates, runtime_home)


def clear_home_caches() -> None:
    """Forget both resolved homes; the asset home is derived from the runtime one."""
    codex_home.cache_clear()
    codex_asset_home.cache_clear()


def claude_home() -> Path:
    configured = env_path("CLAUDE_HOME") or env_path("CLAUDE_CONFIG_DIR")
    if configured:
        return configured
    return DEFAULT_CLAUDE_HOME


def workspace_root() -> Path:
    configured = env_path("CODEX_WORKSPACE")
    if configured:
        return configured
    return first_existing([DEFAULT_WORKSPACE, Path.cwd()], DEFAULT_WORKSPACE)


def agents_home() -> Path:
    configured = env_path("AGENTS_HOME")
    if configured:
        return configured
    return first_existing([DEFAULT_AGENTS_HOME, CONSOLE_DIR.parent], DEFAULT_AGENTS_HOME)


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 8) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        message = f"Timed out after {timeout}s: {shlex.join(cmd)}"
        stderr = f"{stderr.rstrip()}\n{message}".strip()
        return subprocess.CompletedProcess(cmd, 124, stdout, stderr)


def read_text(path: Path, limit: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    if limit is not None and len(text) > limit:
        return text[:limit] + "\n..."
    return text


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


@dataclass
class Prompt:
    id: str
    title: str
    category: str
    description: str
    text: str
    tags: list[str]
    source: str
    priority: int
    library_visibility: str = "system"
    runtimes: list[str] = field(default_factory=lambda: ["codex"])
    launcher_text: str = ""
    situations: dict[str, Any] = field(default_factory=dict)

    def supports_runtime(self, runtime: str | None) -> bool:
        if not runtime:
            return False
        return "shared" in self.runtimes or runtime in self.runtimes

    def to_dict(
        self,
        usage: dict[str, int],
        runtime: str | None = None,
        profile: "PromptProfile | None" = None,
        kernel_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        full_text = self.text.strip()
        launcher_text = (self.launcher_text or self.text).strip()
        has_launcher = bool(self.launcher_text.strip()) and launcher_text != full_text
        profile_payload: dict[str, Any] | None = None
        if profile and profile.append_text and runtime == profile.runtime and self.supports_runtime(runtime):
            # Resolved once per payload by the caller: for Codex this globs
            # /mnt/c/Users/*/.codex, which cost ~200 ms when done per prompt.
            if kernel_state is None:
                kernel_state = inspect_kernel_file(runtime_kernel_path(runtime))
            recommended_mode = "native" if kernel_state["matched"] else "portable"
            launcher_text = compose_prompt(
                launcher_text,
                profile.append_text,
                mode="native",
                kernel_state=kernel_state,
            )
            full_text = compose_prompt(
                full_text,
                profile.append_text,
                mode="portable",
                kernel_state=kernel_state,
                fallback_reason=(
                    "explicit portable export"
                    if kernel_state["matched"]
                    else None
                ),
            )
            profile_payload = profile.to_dict(include_text=False)
        else:
            recommended_mode = "native"
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "text": full_text,
            "launcher_text": launcher_text,
            "full_text": full_text,
            "launcher_chars": len(launcher_text),
            "task_launcher_chars": len((self.launcher_text or self.text).strip()),
            "full_chars": len(full_text),
            "has_launcher": has_launcher,
            "tags": self.tags,
            "source": self.source,
            "priority": self.priority,
            "library_visibility": self.library_visibility,
            "runtimes": self.runtimes,
            "situations": self.situations,
            "usage_count": int(usage.get(self.id, 0)),
            "profile": profile_payload,
            "recommended_mode": recommended_mode,
        }


@dataclass
class PromptProfile:
    id: str
    label: str
    runtime: str
    description: str
    source: str
    priority: int
    append_text: str = ""
    overlays: list[str] = field(default_factory=list)
    default: bool = False

    def to_dict(self, include_text: bool = True) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "label": self.label,
            "runtime": self.runtime,
            "description": self.description,
            "source": self.source,
            "priority": self.priority,
            "default": self.default,
            "has_overlay": bool(self.append_text),
            "overlays": self.overlays,
        }
        if include_text:
            payload["append_text"] = self.append_text
        return payload


def normalize_prompt(text: str) -> str:
    text = textwrap.dedent(text).replace("\r\n", "\n").strip()
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def safe_prompt_file(file_name: str) -> Path | None:
    if not file_name:
        return None
    path = (PROMPTS_DIR / file_name).resolve()
    try:
        path.relative_to(PROMPTS_DIR.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def manifest_prompts() -> list[Prompt]:
    data = load_json(PROMPT_MANIFEST_PATH, {})
    items = data.get("prompts") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    prompts: list[Prompt] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompt_id = str(item.get("id") or "").strip()
        file_name = str(item.get("file") or "").strip()
        launcher_file_name = str(item.get("launcher_file") or "").strip()
        if not prompt_id or not file_name:
            continue
        path = safe_prompt_file(file_name)
        if not path:
            continue
        text = normalize_prompt(read_text(path))
        if not text:
            continue
        launcher_text = ""
        if launcher_file_name:
            launcher_path = safe_prompt_file(launcher_file_name)
            if launcher_path:
                launcher_text = normalize_prompt(read_text(launcher_path))
        prompts.append(
            Prompt(
                id=prompt_id,
                title=str(item.get("title") or prompt_id),
                category=str(item.get("category") or "General"),
                description=str(item.get("description") or ""),
                text=text,
                tags=[str(tag) for tag in item.get("tags", []) if isinstance(tag, str)],
                source=str(item.get("source") or f"prompts/{file_name}"),
                priority=int(item["priority"]) if "priority" in item else 100,
                library_visibility=str(item.get("library_visibility") or "system"),
                runtimes=[str(runtime) for runtime in item.get("runtimes", []) if isinstance(runtime, str)] or ["codex"],
                launcher_text=launcher_text,
                situations=item.get("situations") if isinstance(item.get("situations"), dict) else {},
            )
        )
    return prompts


def prompt_get_payload(prompt_id: str, runtime: str, mode: str) -> dict[str, Any]:
    selected = next((prompt for prompt in manifest_prompts() if prompt.id == prompt_id), None)
    if selected is None:
        raise ValueError(f"unknown prompt id: {prompt_id}")
    if not selected.supports_runtime(runtime):
        raise ValueError(f"prompt {prompt_id} does not support runtime {runtime}")
    text = selected.text if mode == "full" else (selected.launcher_text or selected.text)
    return {
        "id": selected.id,
        "runtime": runtime,
        "mode": mode,
        "text": text,
        "source": selected.source,
        "library_visibility": selected.library_visibility,
    }


def default_profiles() -> list[PromptProfile]:
    return [
        PromptProfile(
            id="fable-5.1",
            label="Fable 5.1",
            runtime="claude",
            description="Default Claude Fable 5.1 prompt profile.",
            source="fallback",
            priority=0,
            default=True,
        ),
        PromptProfile(
            id="opus-5",
            label="Opus 5",
            runtime="claude",
            description="Claude Opus 5 prompt profile.",
            source="fallback",
            priority=10,
        ),
        PromptProfile(
            id="gpt-6-astra",
            label="GPT-6 Astra",
            runtime="codex",
            description="GPT-6 Astra profile for Sol, Terra, and Luna.",
            source="fallback",
            priority=0,
            default=True,
        ),
    ]


def manifest_profiles() -> list[PromptProfile]:
    data = load_json(PROMPT_MANIFEST_PATH, {})
    items = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return default_profiles()

    profiles: list[PromptProfile] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        profile_id = str(item.get("id") or "").strip()
        runtime = str(item.get("runtime") or "").strip()
        if not profile_id or not runtime:
            continue
        file_name = str(item.get("file") or "").strip()
        overlays = item.get("overlays")
        if isinstance(overlays, list):
            overlay_files = [str(file).strip() for file in overlays if str(file).strip()]
        else:
            overlay_files = [file_name] if file_name else []
        overlay_texts: list[str] = []
        for overlay_file in overlay_files:
            path = safe_prompt_file(overlay_file)
            if path:
                overlay_texts.append(normalize_prompt(read_text(path)))
        append_text = normalize_prompt("\n\n".join(text for text in overlay_texts if text))
        source = str(item.get("source") or (f"prompts/{file_name}" if file_name else "manifest"))
        profiles.append(
            PromptProfile(
                id=profile_id,
                label=str(item.get("label") or profile_id),
                runtime=runtime,
                description=str(item.get("description") or ""),
                source=source,
                priority=int(item["priority"]) if "priority" in item else 100,
                append_text=append_text,
                overlays=overlay_files,
                default=bool(item.get("default")),
            )
        )

    return sorted(profiles or default_profiles(), key=lambda item: (item.runtime, item.priority, item.label))


def prompt_profiles_payload(runtime: str | None = None) -> list[dict[str, Any]]:
    profiles = manifest_profiles()
    if runtime:
        profiles = [profile for profile in profiles if profile.runtime == runtime]
    return [profile.to_dict(include_text=False) for profile in profiles]


def select_prompt_profile(runtime: str | None, profile_id: str | None) -> PromptProfile | None:
    if not runtime:
        return None
    profiles = [profile for profile in manifest_profiles() if profile.runtime == runtime]
    if not profiles:
        return None
    if profile_id:
        for profile in profiles:
            if profile.id == profile_id:
                return profile
        valid = ", ".join(sorted(profile.id for profile in profiles))
        raise ValueError(
            f"invalid profile {profile_id!r} for runtime {runtime}; valid profiles: {valid}"
        )
    for profile in profiles:
        if profile.default:
            return profile
    return sorted(profiles, key=lambda item: (item.priority, item.label))[0]


def prompt_has_section(text: str, lower: str, aliases: list[str]) -> bool:
    if any(alias in lower for alias in aliases):
        return True

    headings = {
        match.group("label").strip().removesuffix(":").strip().lower()
        for match in re.finditer(
            r"(?im)^\s{0,3}#{1,6}\s+(?P<label>[^#\r\n]+?)\s*#*\s*$",
            text,
        )
    }
    return any(alias.removesuffix(":").strip() in headings for alias in aliases)


def prompt_check_payload(prompt_text: str, runtime: str, profile: str, kind: str) -> dict[str, Any]:
    text = normalize_prompt(prompt_text or "")
    lower = text.lower()
    errors: list[str] = []
    warnings: list[str] = []

    if runtime not in PROMPT_CHECK_RUNTIMES:
        errors.append(f"invalid runtime: {runtime}")
    if profile not in PROMPT_CHECK_PROFILES:
        errors.append(f"invalid profile: {profile}")
    if kind not in PROMPT_CHECK_KINDS:
        errors.append(f"invalid kind: {kind}")
    if not text:
        errors.append("prompt is empty")

    char_count = len(text)
    budget = PROMPT_KIND_BUDGETS.get(kind, 3000)
    if budget and char_count > budget:
        warnings.append(f"oversized prompt for {kind}: {char_count} chars > {budget} target")

    has_skill_entrypoint = bool(re.search(r"\buse\s+(?:\$|`?orchestration-bridge:)", lower))
    has_target = any(marker in lower for marker in ["target:", "target runtime:", "audience:", "runtime:"]) or has_skill_entrypoint
    if text and kind not in {"launcher", "prompt-card"} and not has_target:
        errors.append("missing target/audience: add Target and Audience or Runtime")

    section_aliases = {
        "goal": ["goal:"],
        "success criteria": ["success criteria", "success:"],
        "context": ["context:", "context to use:", "first route", "re-orient", "before writing", "inputs to establish"],
        "constraints": ["constraints:", "inherited constraints:", "rules:", "execution rules:", "prompt rules:", "routing:"],
        "output": ["output:"],
        "stop": ["stop:", "stop rules:"],
    }
    required_by_kind = {
        "worker": ["goal", "success criteria", "context", "constraints", "output", "stop"],
        "review": ["goal", "success criteria", "context", "constraints", "output", "stop"],
        "fallback": ["goal", "success criteria", "context", "constraints", "output", "stop"],
        "handoff": ["goal", "context", "output"],
        "question": ["goal", "output"],
        "launcher": ["goal", "output", "stop"],
        "prompt-card": ["goal", "output", "stop"],
    }
    # A native same-session Agent prompt is exactly goal/write zone/verification/
    # stop, so it has no Output section by design. Match the four fields as real
    # leading labels, not as words in prose: a substring match would let any text
    # that merely mentions the contract pass as a card. Launchers keep Output --
    # they are slash-command entrypoints, not agent contracts.
    native_contract = kind == "prompt-card" and all(
        re.search(rf"(?im)^\s*{re.escape(marker)}", text)
        for marker in ("goal:", "write zone:", "verification:", "stop:")
    )
    required_sections = required_by_kind.get(kind, [])
    if native_contract:
        required_sections = [
            section for section in required_sections if section != "output"
        ]
    for section in required_sections:
        if not prompt_has_section(text, lower, section_aliases[section]):
            errors.append(f"missing {section} section")

    if kind == "launcher" and not has_skill_entrypoint:
        errors.append("launcher missing skill/plugin entrypoint")

    if kind == "worker":
        # The field is carried when the stream touches external or versioned
        # behavior, and omitted otherwise. Demanding a boilerplate
        # "no external/versioned boundary" line on every local worker prompt
        # bought nothing: the spawned agent already stops before relying on an
        # external claim it was not given. What still has to be right is the
        # field when it *is* present.
        documentation_match = re.search(r"(?im)^\s*documentation:\s*(.+)$", text)
        documentation_text = documentation_match.group(1).strip().lower() if documentation_match else ""
        if documentation_match and "docs-resolve" not in documentation_text:
            no_external = re.search(
                r"no\s+external/versioned\s+boundary\s*-\s*(\S.*)$",
                documentation_text,
            )
            if not no_external:
                errors.append(
                    "invalid documentation decision: use docs-resolve for external/versioned behavior "
                    "or state no external/versioned boundary with a reason"
                )

    def negated(pattern: str, window_chars: int = 24) -> bool:
        matches = list(re.finditer(re.escape(pattern), lower))
        if not matches:
            return False
        return all(
            any(
                token in re.split(
                    r"[.!?\n]",
                    lower[max(0, match.start() - window_chars):match.start()],
                )[-1]
                for token in ["do not ", "don't ", "no ", "not ", "never ", "without "]
            )
            for match in matches
        )

    stale_removal_context = any(token in lower for token in ["remove stale", "grep", "stale docs", "stale strings", "stale pattern", "remove "])
    if ("context7 first" in lower or "use context7 first" in lower) and not stale_removal_context:
        errors.append("stale Context7 first routing: use Docs L1 first, Context7 only as fallback")
    if "template-bridge" in lower and not (negated("template-bridge") or "remove stale" in lower or "remove stale patterns" in lower or "remove template-bridge" in lower):
        errors.append("stale template-bridge reference")

    if any(phrase in lower for phrase in ["hidden inline delegation", "inline-only delegation", "hidden inline-only"]):
        if not (negated("hidden inline") or negated("inline-only") or "remove stale" in lower or "remove stale patterns" in lower or "remove " in lower):
            errors.append(
                "hidden inline delegation is forbidden; require a visible/inspectable agent"
            )

    if any(phrase in lower for phrase in ["never push anything", "do not push under any circumstances", "forbid all pushes", "never push under any circumstances"]):
        errors.append("blanket push ban conflicts with contract-owned ordinary push policy")

    if any(phrase in lower for phrase in ["reveal your internal", "show your internal", "chain of thought", "hidden reasoning"]):
        if not (negated("internal") or negated("chain of thought") or negated("hidden reasoning")):
            errors.append("do not request internal reasoning; ask for concise rationale and evidence")

    if kind == "worker" and "assigned final verification" not in lower:
        goal_match = re.search(
            r"(?ims)^goal:\s*(.*?)(?=^[A-Za-z][^\n:]{0,40}:|\Z)",
            text,
        )
        worker_goal = goal_match.group(1).lower() if goal_match else ""
        acceptance_amplifiers = {
            "full/release suite": (
                ("full configured suite", "full suite", "release suite", "release_commands"),
                (),
            ),
            "rerun acceptance": (("rerun tests", "re-run tests", "rerun acceptance", "re-run acceptance"), ()),
            "reviewer": (("use a reviewer", "spawn a reviewer", "reviewer to"), ()),
            "documentation": (
                ("complete docs-reviewed", "docs-reviewed", "review documentation", "update documentation", "documentation review"),
                ("documentation", "docs"),
            ),
            "Graphify": (("graphify", "graph-reviewed"), ("graphify", "graph")),
            "final closeout": (("final closeout", "complete closeout", "run closeout"), ()),
            "product matrix": (("browser matrix", "all viewports", "every viewport", "all languages", "all themes"), ()),
        }
        found_amplifiers: list[str] = []
        for label, (phrases, allowed_goal_markers) in acceptance_amplifiers.items():
            if allowed_goal_markers and any(marker in worker_goal for marker in allowed_goal_markers):
                continue
            if any(
                phrase in lower and not negated(phrase, window_chars=60)
                for phrase in phrases
            ):
                found_amplifiers.append(label)
        if found_amplifiers:
            warnings.append(
                "worker prompt expands root-owned acceptance ("
                + ", ".join(found_amplifiers)
                + "): keep only an assigned focused red/green target; reviewers, "
                "docs/Graphify decisions, full suite, and final closeout stay with root"
            )

    caps_hits = sorted(set(re.findall(r"\b(CRITICAL|MUST|NEVER|ALWAYS)\b", text)))
    if caps_hits and "aggressive caps intensifiers" not in lower:
        warnings.append(
            "aggressive CAPS intensifiers (" + ", ".join(caps_hits) + ") can cause overtriggering on current models; prefer plain conditional phrasing"
        )

    if kind == "review":
        review_filters = [
            "only material",
            "only high-severity",
            "only report high",
            "be conservative",
            "don't nitpick",
            "do not nitpick",
        ]
        # A prompt that forbids pre-filtering contains the same phrases as one
        # that demands it. The negation sits further away here ("do not narrow
        # the report to only material findings"), so widen the window.
        found_filters = [
            phrase
            for phrase in review_filters
            if phrase in lower and not negated(phrase, window_chars=56)
        ]
        if found_filters and "qualitative pre-filters" not in lower:
            warnings.append(
                "review pre-filter reduces recall ("
                + "; ".join(found_filters)
                + "): ask for every finding with severity/confidence and filter downstream"
            )

    if profile == "fable-5.1" and any(phrase in lower for phrase in ["ask before every step", "wait for confirmation after each step"]):
        warnings.append("Fable 5.1 prompt may over-constrain autonomy")
    if (
        profile == "opus-5"
        and "use subagents" in lower
        and not (
            has_skill_entrypoint and "stage skill's delegation contract" in lower
        )
        and not any(
            word in lower
            for word in [
                "when",
                "if",
                "parallel",
                "specialist",
                "isolation",
                "qualified stream",
            ]
        )
    ):
        warnings.append(
            "Opus 5 subagent routing is vague; say when a stream is delegated (parallel, context-isolation, specialist, or write-isolation benefit)"
        )
    mandatory_delegation_cues = [
        "must be delegated",
        "never execute medium or complex work locally",
        "never execute medium/complex work locally",
        "report blocked instead of continuing locally",
        "report blocked; do not continue locally",
        "block instead of using local fallback",
        "root executes only simple, quick substantive work",
    ]
    found_mandatory_delegation = [
        phrase for phrase in mandatory_delegation_cues if phrase in lower
    ]
    if found_mandatory_delegation:
        warnings.append(
            "mandatory delegation is stale ("
            + ", ".join(found_mandatory_delegation)
            + "): root executes work it already holds the context for; delegate only for a concrete parallel, context-isolation, specialist, or write-isolation benefit, and continue locally when subagents are unavailable"
        )
    verifier_cues = [
        "double-check",
        "re-check",
        "recheck",
        "verifier agent",
        "verify it again",
        "second verification pass",
    ]
    found_verifier = [
        phrase
        for phrase in verifier_cues
        if phrase in lower and not negated(phrase, window_chars=60)
    ]
    if found_verifier:
        warnings.append(
            "routine re-check/verifier-agent steps add latency ("
            + ", ".join(found_verifier)
            + "): reuse matching evidence; mandatory verification runs only "
            "once at final task or epic/release acceptance"
        )
    repeated_ux_cues = [
        "ux proof after every commit",
        "ux evidence after every change",
        "screenshots after every edit",
        "regenerate ux proof for every sha",
    ]
    if any(cue in lower and not negated(cue, window_chars=60) for cue in repeated_ux_cues):
        warnings.append(
            "Repeated UX proof collection adds latency: use the stage skill's "
            "UI/UX evidence decision; preserve explicit delivery requirements"
        )
    if profile == "opus-5":
        verbosity_cues = [
            "exhaustive narrative",
            "narrative log",
            "verbose report",
            "log of every step",
            "document every step",
        ]
        found_verbosity = [phrase for phrase in verbosity_cues if phrase in lower]
        if found_verbosity:
            warnings.append(
                "Opus 5 keeps user updates and durable artifacts concise ("
                + ", ".join(found_verbosity)
                + "): ask for the outcome and material decisions instead"
            )
    if profile == "gpt-6-astra":
        batching_cues = [
            "never batch",
            "do not batch",
            "one tool call at a time",
            "its own separate tool call",
            "one at a time, never batching",
        ]
        found_batching = [phrase for phrase in batching_cues if phrase in lower]
        if found_batching:
            warnings.append(
                "GPT-6 Astra batches independent calls by the canonical Code Mode rule ("
                + ", ".join(found_batching)
                + "): keep only genuinely dependent work sequential"
            )
        cadence_cues = [
            "after every single step",
            "after each step",
            "update after every step",
            "narrate every tool call",
            "progress update after every",
        ]
        found_cadence = [phrase for phrase in cadence_cues if phrase in lower]
        if found_cadence:
            warnings.append(
                "GPT-6 Astra avoids fixed update cadence ("
                + ", ".join(found_cadence)
                + "): update at phase changes, material plan changes, or blockers"
            )
        if "restate the code mode batching rule" in lower or "repeat the batching rule" in lower:
            warnings.append(
                "GPT-6 Astra relies on the canonical global batching rule; do not restate it in task prompts"
            )

    return {
        "ok": not errors,
        "runtime": runtime,
        "profile": profile,
        "kind": kind,
        "char_count": char_count,
        "budget": budget,
        "errors": errors,
        "warnings": warnings,
    }


def prompt_check_text(payload: dict[str, Any]) -> str:
    lines = [
        "prompt-check: " + ("pass" if payload.get("ok") else "fail"),
        f"runtime/profile/kind: {payload.get('runtime')}/{payload.get('profile')}/{payload.get('kind')}",
        f"chars: {payload.get('char_count')} / single-prompt target {payload.get('budget')}",
    ]
    for label in ["errors", "warnings"]:
        values = payload.get(label) or []
        if values:
            lines.append(f"{label}:")
            lines.extend(f"- {value}" for value in values)
    return "\n".join(lines)


def read_prompt_check_input(file_name: str | None) -> str:
    if file_name and file_name != "-":
        return Path(file_name).read_text(encoding="utf-8")
    return sys.stdin.read()

def prompt_payload(runtime: str | None = None, profile_id: str | None = None) -> dict[str, Any]:
    usage = load_json(USAGE_PATH, {})
    manifest_items = manifest_prompts()
    source_prompts = manifest_items
    if runtime:
        source_prompts = [prompt for prompt in source_prompts if prompt.supports_runtime(runtime)]
    active_profile = select_prompt_profile(runtime, profile_id)
    kernel_state = (
        inspect_kernel_file(runtime_kernel_path(runtime))
        if runtime and active_profile and active_profile.append_text
        else None
    )
    prompts = [
        prompt.to_dict(
            usage, runtime=runtime, profile=active_profile, kernel_state=kernel_state
        )
        for prompt in source_prompts
    ]
    prompts.sort(key=lambda item: (-int(item["usage_count"]), int(item["priority"]), item["title"]))
    payload = {
        "prompts": prompts,
        "source": "manifest" if manifest_items else "missing",
        "manifest_path": str(PROMPT_MANIFEST_PATH),
        "runtime": runtime,
        "active_profile": active_profile.to_dict(include_text=False) if active_profile else None,
        "profiles": prompt_profiles_payload(runtime),
        "recent_copies": recent_usage_entries(10),
        "fragments": cached_runtime("fragments-drift", 60, fragments_status),
    }
    if runtime and active_profile:
        payload["composition"] = composition_metadata(
            runtime, active_profile.append_text, kernel_state=kernel_state
        )
    if not manifest_items:
        payload["error"] = f"prompt manifest missing or unreadable: {PROMPT_MANIFEST_PATH}"
    return payload


def fragments_status() -> dict[str, Any]:
    try:
        problems = fragments_drift_check()
    except OSError:
        return {"in_sync": None, "problems": None}
    return {"in_sync": not problems, "problems": len(problems)}


USAGE_LOCK = threading.Lock()


def increment_usage(prompt_id: str, mode: str = "", runtime: str = "", profile: str = "") -> dict[str, int]:
    # Read-modify-write on one file. The ASGI host answers POSTs from a
    # threadpool, so two clicks arriving together used to read the same count
    # and both write it back as one increment.
    with USAGE_LOCK:
        usage = load_json(USAGE_PATH, {})
        usage[prompt_id] = int(usage.get(prompt_id, 0)) + 1
        save_json(USAGE_PATH, usage)
    entry = {
        "ts": int(time.time()),
        "prompt_id": prompt_id,
        "mode": mode or "launcher",
        "runtime": runtime,
        "profile": profile,
    }
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return usage


def recent_usage_entries(limit: int = 10) -> list[dict[str, Any]]:
    if not USAGE_LOG_PATH.is_file():
        return []
    try:
        lines = USAGE_LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in reversed(lines[-500:]):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("prompt_id"):
            entries.append(item)
        if len(entries) >= limit:
            break
    return entries


def catalog_summary() -> dict[str, Any]:
    home = codex_asset_home()
    path = home / "catalog/assets.json"
    runner = home / "bin" / CATALOG_RUNNER_NAME
    data = load_json(path, {})
    staged = data.get("staged_sources") or {}
    sources = staged.values() if isinstance(staged, dict) else staged if isinstance(staged, list) else []
    staged_sources = [source for source in sources if isinstance(source, dict)]
    # An empty catalog and a missing catalog look identical in the counts, so
    # say which one it is instead of showing six zeros and no reason.
    errors = []
    if not path.exists():
        errors.append(f"catalog missing: {path}")
    if not runner.exists():
        errors.append(f"catalog sync runner missing: {runner}")
    return {
        "path": str(path),
        "home": str(home),
        "runtime_home": str(codex_home()),
        "runner": str(runner),
        "runner_exists": runner.exists(),
        "errors": errors,
        "generated_at": data.get("generated_at"),
        "installed_skills": len(data.get("installed_skills") or []),
        "custom_agents": len(data.get("custom_agents") or []),
        "staged_sources": len(staged_sources),
        "staged_skills": sum(len(source.get("skills", [])) for source in staged_sources),
        "staged_agents": sum(len(source.get("agents", [])) for source in staged_sources),
    }


def aitmpl_agent_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in AITMPL_BASELINE_AGENTS:
        name = item["name"]
        category = item["category"]
        agent_ref = f"{category}/{name}"
        dry_run_args = ["npx", AITMPL_NPM_PACKAGE, "--agent", agent_ref, "--dry-run"]
        candidates.append(
            {
                "name": name,
                "category": category,
                "agent_ref": agent_ref,
                "purpose": item["purpose"],
                "runtime": "claude",
                "component_type": "agent",
                "source": "aitmpl",
                "source_url": AITMPL_AGENTS_URL,
                "component_url": f"https://www.aitmpl.com/component/agents/{agent_ref}",
                "docs_url": AITMPL_DOCS_URL,
                "install_target": str(claude_home() / "agents" / f"{name}.md"),
                "install_scope": "manual-vetted",
                "last_verified": "2026-06-13",
                "auto_install": False,
                "live_package": True,
                "package": AITMPL_NPM_PACKAGE,
                "promotion_requires_resolved_version": True,
                "promotion_requires_content_hash": True,
                "external_execution_approval_required": True,
                "copy_install_approval_required": True,
                "vetting_required": True,
                "vetting_checklist": AITMPL_VETTING_CHECKLIST,
                "dry_run_args": dry_run_args,
                "dry_run_command": shlex.join(dry_run_args),
            }
        )
    return candidates


def valid_claude_agent_library_name(name: str) -> str:
    value = name.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,80}", value):
        raise ValueError(f"invalid Claude agent name: {name}")
    return value


def aitmpl_candidate_by_name(name: str) -> dict[str, Any]:
    safe_name = valid_claude_agent_library_name(name)
    for candidate in aitmpl_agent_candidates():
        if candidate["name"] == safe_name:
            return candidate
    raise ValueError(f"unknown Claude agent library item: {safe_name}")


def claude_agent_library_template_paths(name: str) -> list[Path]:
    safe_name = valid_claude_agent_library_name(name)
    return [
        path
        for root in [CLAUDE_AGENT_LIBRARY_DIR, CLAUDE_AGENT_CACHE_DIR]
        for path in root.rglob(f"{safe_name}.md")
        if path.is_file() and claude_is_agent_file(path)
    ]


def claude_agent_library_template_path(name: str) -> Path | None:
    paths = claude_agent_library_template_paths(name)
    return paths[0] if paths else None


def claude_agent_library_file_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for root, source in [(CLAUDE_AGENT_LIBRARY_DIR, "local-agent-library"), (CLAUDE_AGENT_CACHE_DIR, "local-agent-cache")]:
        if not root.exists():
            continue
        for path in claude_valid_agent_paths(root):
            metadata = claude_agent_frontmatter(path)
            rel = path.relative_to(root)
            category = rel.parts[0] if len(rel.parts) > 1 else "local"
            records.append(
                {
                    "name": metadata.get("name") or path.stem,
                    "category": category,
                    "agent_ref": str(rel.with_suffix("")),
                    "purpose": metadata.get("description") or "Local Claude Code subagent.",
                    "template_path": str(path),
                    "source": source,
                }
            )
    return records


def generated_claude_agent_markdown(candidate: dict[str, Any]) -> str:
    name = valid_claude_agent_library_name(candidate["name"])
    purpose = str(candidate.get("purpose") or "Claude Code subagent.")
    agent_ref = str(candidate.get("agent_ref") or name)
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {purpose}\n"
        "tools: Read, Grep, Glob, Bash\n"
        "---\n\n"
        f"# {name}\n\n"
        f"You are a Claude Code subagent for: {purpose}\n\n"
        "Use this local wrapper as a vetted, agents-only baseline inspired by the aitmpl "
        f"candidate `{agent_ref}`. Do not install or suggest hooks, MCP servers, settings, "
        "slash commands, or broad permissions from external template packs.\n\n"
        "## Operating Rules\n\n"
        "- Stay within the assigned task and write zone. Verification is root-owned unless this is an explicitly assigned final verification stream.\n"
        "- Prefer project-local conventions and reusable code before new dependencies.\n"
        "- Use Docs L1/L2 for version-sensitive library, framework, CLI, or platform behavior.\n"
        "- Report severity, evidence, file/line when possible, suggested fix, tradeoff, confidence, and residual risk.\n"
    )


def claude_agent_library_source(name: str) -> tuple[str, Path | None, str]:
    template = claude_agent_library_template_path(name)
    if template:
        return template.read_text(encoding="utf-8"), template, "local-template"
    candidate = aitmpl_candidate_by_name(name)
    return generated_claude_agent_markdown(candidate), None, "generated-fallback"


def claude_agent_library_payload(workspace: Path | None = None) -> dict[str, Any]:
    project_root = workspace or workspace_root()
    project_agents_dir = project_root / ".claude" / "agents"
    user_agents_dir = claude_home() / "agents"
    installed_records = installed_claude_agent_records()
    records_by_name: dict[str, list[dict[str, Any]]] = {}
    for record in installed_records:
        records_by_name.setdefault(record["name"], []).append(record)

    candidate_map = {candidate["name"]: candidate for candidate in aitmpl_agent_candidates()}
    for record in claude_agent_library_file_records():
        if record["name"] not in candidate_map:
            candidate_map[record["name"]] = {
                "name": record["name"],
                "category": record["category"],
                "agent_ref": record["agent_ref"],
                "purpose": record["purpose"],
                "runtime": "claude",
                "component_type": "agent",
                "source": record["source"],
                "source_url": "",
                "component_url": "",
                "docs_url": "",
                "install_target": str(claude_home() / "agents" / f"{record['name']}.md"),
                "install_scope": "local-vetted",
                "last_verified": "",
                "auto_install": False,
                "live_package": False,
                "package": "",
                "promotion_requires_resolved_version": False,
                "promotion_requires_content_hash": False,
                "external_execution_approval_required": False,
                "copy_install_approval_required": True,
                "vetting_required": True,
                "vetting_checklist": AITMPL_VETTING_CHECKLIST,
                "dry_run_args": [],
                "dry_run_command": "",
            }

    candidates: list[dict[str, Any]] = []
    for candidate in sorted(candidate_map.values(), key=lambda item: (item["category"], item["name"])):
        template = claude_agent_library_template_path(candidate["name"])
        copy_project_command = (
            f"mkdir -p .claude/agents && cp {shlex.quote(str(template)) if template else '<local-template>'} "
            f".claude/agents/{candidate['name']}.md"
        )
        install_project_args = ["orch-prompts", "claude-agent-install", "--agent", candidate["name"], "--scope", "project"]
        install_user_args = ["orch-prompts", "claude-agent-install", "--agent", candidate["name"], "--scope", "user"]
        candidates.append(
            {
                **candidate,
                "source": "aitmpl-local-library" if candidate.get("source") == "aitmpl" else candidate.get("source", "local-agent-library"),
                "local_template_available": bool(template),
                "local_template_path": str(template) if template else "",
                "local_cache_path": str(CLAUDE_AGENT_CACHE_DIR / candidate["category"] / f"{candidate['name']}.md"),
                "project_install_target": str(project_agents_dir / f"{candidate['name']}.md"),
                "user_install_target": str(user_agents_dir / f"{candidate['name']}.md"),
                "copy_project_command": copy_project_command,
                "install_project_command": shlex.join(install_project_args),
                "install_user_command": shlex.join(install_user_args),
                "matching_claude_agent": bool(records_by_name.get(candidate["name"])),
                "matching_sources": records_by_name.get(candidate["name"], []),
            }
        )

    return {
        "runtime": "claude",
        "source": "aitmpl-local-library",
        "source_url": AITMPL_AGENTS_URL,
        "docs_url": AITMPL_DOCS_URL,
        "policy": AITMPL_INSTALL_POLICY,
        "vetting_checklist": AITMPL_VETTING_CHECKLIST,
        "library_dir": str(CLAUDE_AGENT_LIBRARY_DIR),
        "cache_dir": str(CLAUDE_AGENT_CACHE_DIR),
        "project_agents_dir": str(project_agents_dir),
        "user_agents_dir": str(user_agents_dir),
        "candidate_count": len(candidates),
        "local_template_count": sum(1 for item in candidates if item["local_template_available"]),
        "matching_agent_count": sum(1 for item in candidates if item["matching_claude_agent"]),
        "installed_agents": installed_records,
        "candidates": candidates,
    }


def install_claude_agent_from_library(
    name: str,
    scope: str = "project",
    workspace: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    safe_name = valid_claude_agent_library_name(name)
    text, source_path, source_kind = claude_agent_library_source(safe_name)
    if scope == "project":
        root = workspace or workspace_root()
        target_dir = root / ".claude" / "agents"
    elif scope == "user":
        target_dir = claude_home() / "agents"
    else:
        raise ValueError(f"unsupported Claude agent install scope: {scope}")
    target = target_dir / f"{safe_name}.md"
    restart_recommended = not target_dir.exists()
    if target.exists() and not overwrite:
        raise FileExistsError(f"Claude agent already exists: {target}")
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {
        "ok": True,
        "name": safe_name,
        "scope": scope,
        "target": str(target),
        "source_path": str(source_path) if source_path else "",
        "source_kind": source_kind,
        "restart_recommended": restart_recommended,
        "note": "Claude detects new files within seconds; restart the Claude Code session if the agents directory did not exist when the session started.",
    }


def claude_user_agent_paths() -> list[Path]:
    root = claude_home() / "agents"
    return claude_valid_agent_paths(root) if root.exists() else []


def claude_agent_frontmatter(path: Path) -> dict[str, str]:
    text = read_text(path, limit=8000).replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    frontmatter = text[4:end]
    metadata: dict[str, str] = {}
    for key in ["name", "description", "model", "tools"]:
        match = re.search(rf"(?m)^{re.escape(key)}:\s*['\"]?([^'\"\n]+)['\"]?\s*$", frontmatter)
        if match:
            metadata[key] = match.group(1).strip()
    return metadata


def claude_is_agent_file(path: Path) -> bool:
    if path.name.lower() == "readme.md":
        return False
    metadata = claude_agent_frontmatter(path)
    return bool(metadata.get("name") or metadata.get("description"))


def claude_valid_agent_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.md") if claude_is_agent_file(path))


def public_release_mode() -> bool:
    return (CONSOLE_DIR / "release-manifest.json").is_file()


def claude_wrapper_plugin_inventory() -> dict[str, Any]:
    """Describe public-release plugins without claiming a Claude registry load."""
    harness_root = env_path("HARNESS_HOME", Path.home() / ".agent-harness")
    plugins_root = (harness_root or Path.home() / ".agent-harness") / "plugins"
    items: list[dict[str, Any]] = []
    for expected_name in ("orchestration-bridge", "superpowers"):
        root = plugins_root / expected_name
        manifest_path = root / ".claude-plugin" / "plugin.json"
        manifest = load_json(manifest_path, {})
        manifest_name = str(manifest.get("name") or "") if isinstance(manifest, dict) else ""
        installed = root.is_dir() and manifest_path.is_file() and manifest_name == expected_name
        skill_paths = sorted(root.glob("skills/*/SKILL.md")) if installed else []
        agent_paths = claude_valid_agent_paths(root / "agents") if installed else []
        items.append(
            {
                "name": expected_name,
                "version": str(manifest.get("version") or "unknown") if installed else "unknown",
                "path": str(root),
                "installed_for_wrapper": installed,
                "skills": len(skill_paths),
                "agents": len(agent_paths),
                "load_status": "not-observed",
            }
        )
    return {
        "mode": "harness-claude-session",
        "command": "harness claude",
        "plugins_root": str(plugins_root),
        "installed_count": sum(1 for item in items if item["installed_for_wrapper"]),
        "skills": sum(int(item["skills"]) for item in items),
        "agents": sum(int(item["agents"]) for item in items),
        "items": items,
        "runtime_load_verified": False,
        "plain_claude_registration": "not-claimed",
        "note": "These plugin files are passed with repeated --plugin-dir only by `harness claude`; filesystem inventory does not prove Claude loaded them.",
    }


def claude_plugin_agent_roots_from_plugin(plugin: dict[str, Any]) -> list[tuple[Path, str]]:
    if not plugin.get("enabled"):
        return []
    install_path = plugin.get("install_path")
    if not install_path:
        return []
    root = Path(str(install_path)).expanduser()
    if not root.exists():
        return []
    plugin_id = str(plugin.get("name") or "")
    roots: list[tuple[Path, str]] = []
    direct = root / "agents"
    if direct.exists():
        roots.append((direct, plugin_id))
    for nested in root.glob("skills/*/agents"):
        if nested.exists():
            roots.append((nested, plugin_id))
    return roots


def claude_plugin_agent_roots_from_settings() -> list[tuple[Path, str]]:
    skills_root = claude_home() / "skills"
    if not skills_root.exists():
        return []
    settings = claude_settings_summary()
    enabled_plugin_names = {name.split("@", 1)[0] for name in settings.get("enabled_plugins", [])}
    has_plugin_settings = bool(settings.get("exists"))
    roots: list[tuple[Path, str]] = []
    for agents_root in skills_root.glob("*/agents"):
        if has_plugin_settings and agents_root.parent.name not in enabled_plugin_names:
            continue
        if agents_root.exists():
            roots.append((agents_root, agents_root.parent.name))
    return roots


def claude_plugin_agent_roots() -> list[tuple[Path, str]]:
    roots: list[tuple[Path, str]] = []
    for plugin in claude_plugins_summary().get("items", []):
        roots.extend(claude_plugin_agent_roots_from_plugin(plugin))
    if not roots:
        roots.extend(claude_plugin_agent_roots_from_settings())
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[Path, str]] = []
    for root, plugin_id in roots:
        key = (str(root), plugin_id)
        if key not in seen:
            seen.add(key)
            unique.append((root, plugin_id))
    return unique


def claude_plugin_agent_paths() -> list[Path]:
    paths: list[Path] = []
    for root, _plugin_id in claude_plugin_agent_roots():
        paths.extend(claude_valid_agent_paths(root))
    return sorted(set(paths))


def claude_project_agent_paths() -> list[Path]:
    roots = [workspace_root() / ".claude" / "agents", CONSOLE_DIR / ".claude" / "agents"]
    paths: list[Path] = []
    for root in roots:
        if root.exists():
            paths.extend(claude_valid_agent_paths(root))
    return sorted(set(paths))


def claude_agent_name(path: Path) -> str:
    return claude_agent_frontmatter(path).get("name") or path.stem


def claude_agent_record(path: Path, source_scope: str, plugin_id: str | None = None, project_root: Path | None = None) -> dict[str, Any]:
    metadata = claude_agent_frontmatter(path)
    return {
        "name": metadata.get("name") or path.stem,
        "description": metadata.get("description", ""),
        "path": str(path),
        "source_scope": source_scope,
        "plugin_id": plugin_id,
        "project_root": str(project_root) if project_root else None,
    }


def installed_claude_agent_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in claude_user_agent_paths():
        records.append(claude_agent_record(path, "user"))
    for root in [workspace_root() / ".claude" / "agents", CONSOLE_DIR / ".claude" / "agents"]:
        for path in claude_valid_agent_paths(root):
            records.append(claude_agent_record(path, "project", project_root=root.parent.parent))
    for root, plugin_id in claude_plugin_agent_roots():
        for path in claude_valid_agent_paths(root):
            records.append(claude_agent_record(path, "plugin", plugin_id=plugin_id))
    return records


def installed_claude_agent_names() -> set[str]:
    return {record["name"] for record in installed_claude_agent_records()}


def claude_aitmpl_summary() -> dict[str, Any]:
    installed_records = installed_claude_agent_records()
    records_by_name: dict[str, list[dict[str, Any]]] = {}
    for record in installed_records:
        records_by_name.setdefault(record["name"], []).append(record)
    candidates = []
    for candidate in aitmpl_agent_candidates():
        matching_sources = records_by_name.get(candidate["name"], [])
        candidates.append(
            {
                **candidate,
                "matching_claude_agent": bool(matching_sources),
                "matching_sources": matching_sources,
            }
        )
    return {
        "source": "aitmpl",
        "source_url": AITMPL_AGENTS_URL,
        "docs_url": AITMPL_DOCS_URL,
        "policy": AITMPL_INSTALL_POLICY,
        "vetting_checklist": AITMPL_VETTING_CHECKLIST,
        "candidate_count": len(candidates),
        "matching_agent_count": sum(1 for item in candidates if item["matching_claude_agent"]),
        "candidates": candidates,
    }


def claude_catalog_summary() -> dict[str, Any]:
    skills_root = claude_home() / "skills"
    skill_packs = [path for path in skills_root.iterdir() if path.is_dir()] if skills_root.exists() else []
    plugin_skills = len(list(skills_root.glob("*/skills/*/SKILL.md"))) + len(list(skills_root.glob("*/SKILL.md")))
    user_agents = len(claude_user_agent_paths())
    project_agents = len(claude_project_agent_paths())
    plugin_agents = len(claude_plugin_agent_paths())
    settings = claude_settings_summary()
    aitmpl = claude_aitmpl_summary()
    summary = {
        "path": str(skills_root),
        "enabled_plugins": len(settings["enabled_plugins"]),
        "disabled_plugins": len(settings["disabled_plugins"]),
        "skill_packs": len(skill_packs),
        "plugin_skills": plugin_skills,
        "agents": plugin_agents + user_agents + project_agents,
        "user_agents": user_agents,
        "project_agents": project_agents,
        "plugin_agents": plugin_agents,
        "aitmpl_candidates": aitmpl["candidate_count"],
        "aitmpl_matching_agents": aitmpl["matching_agent_count"],
        "aitmpl_policy": aitmpl["policy"],
        "orchestration_bridge": bool(settings["orchestration_bridge_enabled"]),
    }
    if public_release_mode():
        wrapper = claude_wrapper_plugin_inventory()
        summary.update(
            {
                "wrapper_plugins": wrapper["installed_count"],
                "wrapper_plugin_skills": wrapper["skills"],
                "wrapper_plugin_agents": wrapper["agents"],
                "wrapper_scope": wrapper["mode"],
                "wrapper_runtime_load_verified": wrapper["runtime_load_verified"],
            }
        )
    return summary


def asset_roots(*names: str) -> list[Path]:
    """Every distinct place an asset of these kinds can live, runtime home first.

    The runtime and asset homes are usually different directories but may be
    the same one, and a dedicated runtime home often symlinks `agents` back to
    the populated home. Resolving before de-duplicating stops both cases from
    listing the same skill or agent twice.
    """

    seen: set[Path] = set()
    roots: list[Path] = []
    for home in (codex_home(), codex_asset_home(), agents_home()):
        for name in names:
            root = home / name
            if not root.exists():
                continue
            key = root.resolve()
            if key in seen:
                continue
            seen.add(key)
            roots.append(root)
    return roots


def list_skill_paths() -> list[Path]:
    paths: list[Path] = []
    for root in asset_roots("skills", "superpowers/skills"):
        paths.extend(root.glob("*/SKILL.md"))
    return sorted(paths)


def list_agent_paths() -> list[Path]:
    paths: list[Path] = []
    for root in asset_roots("agents"):
        paths.extend(root.glob("*.toml"))
    return sorted(paths)


def beads_summary() -> dict[str, Any]:
    bd_path = shutil.which("bd")
    beads_path = shutil.which("beads")
    dolt_path = shutil.which("dolt")
    embeddeddolt = list(workspace_root().glob("*/.beads/embeddeddolt"))
    dolt_dirs = list(workspace_root().glob("*/.beads/dolt"))
    summary = "bd present" if bd_path else "bd missing"
    if embeddeddolt:
        summary += f", embedded Dolt in {len(embeddeddolt)} repos"
    return {
        "bd_present": bool(bd_path),
        "bd_path": bd_path,
        "beads_present": bool(beads_path),
        "beads_path": beads_path,
        "dolt_present": bool(dolt_path),
        "dolt_path": dolt_path,
        "embedded_dolt_repos": len(embeddeddolt),
        "legacy_dolt_repos": len(dolt_dirs),
        "summary": summary,
    }




def mask_secret_text(text: str) -> str:
    return redact_sensitive_text(text)


def private_debug_enabled() -> bool:
    return os.environ.get("ORCH_PROMPTS_PRIVATE_DEBUG", "").lower() in {"1", "true", "yes", "on"}


RUNTIME_CACHE: dict[str, tuple[float, Any]] = {}
RUNTIME_REFRESHING: set[str] = set()
RUNTIME_CACHE_LOCK = threading.Lock()
SERVER_MODE = False


def cached_runtime(key: str, ttl: int, builder: Any) -> Any:
    now = time.time()
    with RUNTIME_CACHE_LOCK:
        cached = RUNTIME_CACHE.get(key)
    if cached and now - cached[0] <= ttl:
        return cached[1]
    value = builder()
    with RUNTIME_CACHE_LOCK:
        RUNTIME_CACHE[key] = (time.time(), value)
    return value


def start_runtime_refresh(key: str, builder: Any) -> bool:
    if not SERVER_MODE:
        return False
    with RUNTIME_CACHE_LOCK:
        if key in RUNTIME_REFRESHING:
            return False
        RUNTIME_REFRESHING.add(key)

    def refresh() -> None:
        try:
            value = builder()
        except Exception as exc:  # pragma: no cover - defensive background guard
            value = {"available": False, "list_ok": False, "error": mask_secret_text(str(exc))}
        with RUNTIME_CACHE_LOCK:
            RUNTIME_CACHE[key] = (time.time(), value)
            RUNTIME_REFRESHING.discard(key)

    thread = threading.Thread(target=refresh, name=f"runtime-refresh-{key}", daemon=True)
    thread.start()
    return True


def runtime_cache_snapshot(key: str) -> tuple[float, Any] | None:
    with RUNTIME_CACHE_LOCK:
        return RUNTIME_CACHE.get(key)


def cached_payload(key: str, ttl: int, builder: Any, fresh: bool = False) -> Any:
    if fresh:
        value = builder()
        with RUNTIME_CACHE_LOCK:
            RUNTIME_CACHE[key] = (time.time(), value)
        return value
    return cached_runtime(key, ttl, builder)


def sensitive_key(key: str) -> bool:
    return bool(re.search(r"(token|secret|password|credential|api[_-]?key|access[_-]?token|refresh[_-]?token|auth)", key, re.IGNORECASE))


def redact_value(value: Any, key: str = "") -> Any:
    if sensitive_key(key):
        return "***"
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(item, key) for item in value[:100]]
    if isinstance(value, str):
        return mask_secret_text(value)
    return value


def claude_binary() -> str | None:
    candidates: list[str] = []
    found = shutil.which("claude")
    if found:
        candidates.append(found)
    nvm_root = Path.home() / ".nvm/versions/node"
    if nvm_root.exists():
        candidates.extend(str(path) for path in sorted(nvm_root.glob("*/bin/claude"), reverse=True))
    # Anthropic ships the WSL CLI inside the VS Code extension, where it may not
    # be available on PATH.
    extensions_root = Path.home() / ".vscode-server" / "extensions"
    if extensions_root.exists():
        candidates.extend(
            str(path)
            for path in sorted(
                extensions_root.glob("anthropic.claude-code-*/resources/native-binary/claude"),
                reverse=True,
            )
        )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return None


def parse_claude_version(output: str) -> str:
    return output.strip().splitlines()[0] if output.strip() else "unknown"


def claude_version_summary() -> dict[str, Any]:
    binary = claude_binary()
    if not binary:
        return {"available": False, "binary": None, "version": "", "status": "missing"}
    result = run([binary, "--version"], timeout=6)
    return {
        "available": result.returncode == 0,
        "binary": binary,
        "version": parse_claude_version(result.stdout or result.stderr),
        "status": "ok" if result.returncode == 0 else "warn",
        "error": mask_secret_text((result.stderr or "").strip()[:500]),
    }


def claude_settings_summary() -> dict[str, Any]:
    path = claude_home() / "settings.json"
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}
    enabled = data.get("enabledPlugins") if isinstance(data.get("enabledPlugins"), dict) else {}
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    permissions = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
    env = data.get("env") if isinstance(data.get("env"), dict) else {}
    deny = permissions.get("deny") if isinstance(permissions.get("deny"), list) else []
    return {
        "path": str(path),
        "exists": path.exists(),
        "language": data.get("language"),
        "effort_level": data.get("effortLevel"),
        "enabled_plugins": sorted([name for name, value in enabled.items() if value]),
        "disabled_plugins": sorted([name for name, value in enabled.items() if not value]),
        "template_bridge_enabled": bool(enabled.get("template-bridge@template-bridge-marketplace")),
        "claude_mem_enabled": bool(enabled.get("claude-mem@thedotmack")),
        "orchestration_bridge_enabled": bool(enabled.get("orchestration-bridge@skills-dir")),
        "skip_dangerous_mode_permission_prompt": bool(data.get("skipDangerousModePermissionPrompt")),
        "hooks": sorted(hooks.keys()),
        "env_keys": sorted(env.keys()),
        "permission_keys": sorted(permissions.keys()),
        "deny_count": len(deny),
    }


def claude_memory_summary() -> dict[str, Any]:
    path = claude_home() / "CLAUDE.md"
    text = read_text(path, limit=30000)
    lowered = text.lower()
    return {
        "path": str(path),
        "exists": path.exists(),
        "line_count": len(text.splitlines()) if text else 0,
        "routes_template_bridge": bool(re.search(r"template-bridge:[a-z]", lowered)),
        "mentions_unified_workflow": "unified-workflow" in lowered,
        "routes_context7_first": "context7 first" in lowered or "context7 mcp first" in lowered,
        "imports_agents": "@agents.md" in lowered,
    }


def parse_claude_plugin_list(output: str) -> list[dict[str, Any]]:
    plugins: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        marker = "❯ "
        if marker in line:
            if current:
                plugins.append(current)
            name = line.split(marker, 1)[1].strip()
            current = {"name": name, "version": "unknown", "scope": "unknown", "enabled": None}
            continue
        if current and line.startswith("Version:"):
            current["version"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("Scope:"):
            current["scope"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("Status:"):
            current["enabled"] = "✔" in line or "enabled" in line.lower()
    if current:
        plugins.append(current)
    return plugins


def parse_claude_plugin_json(output: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(output) if output.strip() else []
    except json.JSONDecodeError:
        return []
    source_items = parsed if isinstance(parsed, list) else parsed.get("plugins", []) if isinstance(parsed, dict) else []
    items: list[dict[str, Any]] = []
    for item in source_items:
        if not isinstance(item, dict):
            continue
        plugin_id = str(item.get("id") or item.get("name") or "")
        if not plugin_id:
            continue
        items.append(
            {
                "name": plugin_id,
                "version": str(item.get("version") or "unknown"),
                "scope": str(item.get("scope") or "unknown"),
                "enabled": bool(item.get("enabled")),
                "install_path": str(item.get("installPath") or item.get("install_path") or item.get("path") or ""),
            }
        )
    return items


def build_claude_plugins_summary() -> dict[str, Any]:
    binary = claude_binary()
    if not binary:
        summary = {"available": False, "items": [], "error": "claude command not found"}
        if public_release_mode():
            summary.update(
                {
                    "inventory_scope": "native-claude-plugin-registry",
                    "wrapper": claude_wrapper_plugin_inventory(),
                }
            )
        return summary
    result = run([binary, "plugin", "list", "--json"], timeout=10)
    raw_text = result.stdout or result.stderr
    text = mask_secret_text(raw_text)
    items = parse_claude_plugin_json(result.stdout) if result.returncode == 0 else []
    source = "json"
    if not items:
        fallback = run([binary, "plugin", "list"], timeout=10)
        raw_text = fallback.stdout or fallback.stderr
        text = mask_secret_text(raw_text)
        items = parse_claude_plugin_list(text)
        result = fallback
        source = "text"
    summary = {
        "available": result.returncode == 0 and bool(items),
        "items": items,
        "count": len(items),
        "enabled_count": sum(1 for item in items if item.get("enabled")),
        "template_bridge_enabled": any(item["name"].startswith("template-bridge@") and item.get("enabled") for item in items),
        "orchestration_bridge_enabled": any(item["name"].startswith("orchestration-bridge@") and item.get("enabled") for item in items),
        "source": source,
        "error": "" if result.returncode == 0 else text[:500],
    }
    if private_debug_enabled():
        summary["raw"] = text.splitlines()[:120]
    if public_release_mode():
        summary.update(
            {
                "inventory_scope": "native-claude-plugin-registry",
                "wrapper": claude_wrapper_plugin_inventory(),
            }
        )
    return summary


def claude_plugins_summary() -> dict[str, Any]:
    return cached_runtime("claude_plugins", 10, build_claude_plugins_summary)


def build_claude_agents_summary() -> dict[str, Any]:
    binary = claude_binary()
    if not binary:
        return {"available": False, "items": [], "error": "claude command not found"}
    result = run([binary, "agents", "--json"], timeout=10)
    text = mask_secret_text(result.stdout or result.stderr)
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        parsed = []
    items = parsed if isinstance(parsed, list) else parsed.get("agents", []) if isinstance(parsed, dict) else []
    summary = {
        "available": result.returncode == 0,
        "count": len(items) if isinstance(items, list) else 0,
        "error": "" if result.returncode == 0 else text[:500],
    }
    if private_debug_enabled():
        summary["items"] = redact_value(items)
    return summary


def claude_agents_summary() -> dict[str, Any]:
    return cached_runtime("claude_agents", 10, build_claude_agents_summary)


def build_claude_mcp_summary() -> dict[str, Any]:
    binary = claude_binary()
    claude_json = claude_mcp_state_path()
    user_mcp = claude_configured_mcp_servers(claude_json)
    result_text = ""
    ok = False
    returncode = None
    if binary:
        result = run([binary, "mcp", "list"], timeout=30)
        ok = result.returncode == 0
        returncode = result.returncode
        result_text = mask_secret_text(result.stdout or result.stderr)
    summary = {
        "available": bool(binary),
        "state_path": str(claude_json),
        "list_ok": ok,
        "list_returncode": returncode,
        "list_timed_out": returncode == 124,
        "configured_servers": user_mcp,
        "error": "" if ok else result_text[:500],
    }
    if private_debug_enabled():
        summary["list_output"] = result_text.splitlines()[:80]
    return summary


def claude_mcp_summary() -> dict[str, Any]:
    return cached_runtime("claude_mcp", 60, build_claude_mcp_summary)


def claude_mcp_state_path() -> Path:
    return first_existing([Path.home() / ".claude.json", claude_home() / ".claude.json"], Path.home() / ".claude.json")


def claude_configured_mcp_servers(path: Path | None = None) -> list[str]:
    data = load_json(path or claude_mcp_state_path(), {})
    if not isinstance(data, dict):
        return []
    servers = data.get("mcpServers")
    return sorted(servers.keys()) if isinstance(servers, dict) else []


def codex_configured_mcp_servers(path: Path | None = None) -> list[str]:
    config_path = path or (codex_home() / "config.toml")
    if tomllib is None or not config_path.exists():
        return []
    try:
        data = tomllib.loads(read_text(config_path))
    except Exception:
        return []
    servers = data.get("mcp_servers") if isinstance(data, dict) else None
    return sorted(servers.keys()) if isinstance(servers, dict) else []


def docs_server_names(names: list[str]) -> list[str]:
    markers = ("context", "neuledge", "docs")
    return sorted(name for name in names if any(marker in name.lower() for marker in markers))


def with_refresh_state(summary: dict[str, Any], refresh_state: str, timestamp: float | None = None) -> dict[str, Any]:
    payload = dict(summary)
    payload["refresh_state"] = refresh_state
    if timestamp is not None:
        payload["last_refreshed"] = int(timestamp)
    return payload


def pending_claude_mcp_summary(refresh_state: str = "pending") -> dict[str, Any]:
    binary = claude_binary()
    return {
        "available": bool(binary),
        "state_path": str(claude_mcp_state_path()),
        "list_ok": False,
        "list_returncode": None,
        "list_timed_out": False,
        "configured_servers": claude_configured_mcp_servers(),
        "error": "refresh pending" if binary else "claude command not found",
        "refresh_state": refresh_state,
    }


def claude_mcp_runtime_snapshot() -> dict[str, Any]:
    key = "claude_mcp"
    ttl = 60
    now = time.time()
    cached = runtime_cache_snapshot(key)
    if cached and now - cached[0] <= ttl:
        return with_refresh_state(cached[1], "fresh", cached[0])

    start_runtime_refresh(key, build_claude_mcp_summary)
    if cached:
        return with_refresh_state(cached[1], "stale", cached[0])
    return pending_claude_mcp_summary()


def vscode_user_settings_path() -> Path | None:
    users_root = Path("/mnt/c/Users")
    candidates = [Path.home() / ".config/Code/User/settings.json"]
    if users_root.exists():
        candidates.extend(sorted(users_root.glob("*/AppData/Roaming/Code/User/settings.json")))
    for path in candidates:
        if path.exists():
            return path
    return None


def vscode_claude_extensions() -> list[str]:
    users_root = Path("/mnt/c/Users")
    roots = [Path.home() / ".vscode/extensions"]
    if users_root.exists():
        roots.extend(sorted(users_root.glob("*/.vscode/extensions")))
    found: list[str] = []
    for extensions_root in roots:
        if not extensions_root.exists():
            continue
        found.extend(path.name for path in extensions_root.iterdir() if path.is_dir() and re.search(r"(anthropic|claude)", path.name, re.IGNORECASE))
    return sorted(set(found))


def vscode_wsl_summary() -> dict[str, Any]:
    settings_path = vscode_user_settings_path()
    settings = load_json(settings_path, {}) if settings_path else {}
    if not isinstance(settings, dict):
        settings = {}
    cwd = workspace_root()
    cli_mode_note = "Run `claude` from the VS Code integrated terminal. Use `/ide` only when attaching from an external terminal."
    if public_release_mode():
        cli_mode_note = "Run `harness claude`: it loads the journaled bridge and Superpowers plugins for that session only. Plain `claude` is not reported as globally configured by this release."
    return {
        "target": "Claude Code CLI in VS Code integrated terminal on WSL",
        "wsl": bool(os.environ.get("WSL_DISTRO_NAME") or Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists()),
        "workspace_on_linux_fs": str(cwd).startswith("/home/"),
        "workspace": str(cwd),
        "ripgrep": shutil.which("rg"),
        "vscode_settings_path": str(settings_path) if settings_path else "",
        "vscode_settings_exists": bool(settings_path),
        "terminal_gpu_setting": settings.get("terminal.integrated.gpuAcceleration", "not-set"),
        "claude_extensions": vscode_claude_extensions(),
        "cli_mode_note": cli_mode_note,
    }


def codex_runtime_payload() -> dict[str, Any]:
    skills = list_skill_paths()
    agents = list_agent_paths()
    return {
        "id": "codex",
        "label": "Codex",
        "status": "ok",
        "paths": {
            "home": str(codex_home()),
            "asset_home": str(codex_asset_home()),
            "agents_home": str(agents_home()),
            "workspace": str(workspace_root()),
        },
        "catalog": catalog_summary(),
        "skills": {"count": len(skills), "items": [{"name": path.parent.name, "path": str(path)} for path in skills]},
        "agents": {"count": len(agents), "items": [{"name": path.stem, "path": str(path)} for path in agents]},
        "mcp": mcp_status(),
    }


def claude_base_warnings(version: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    warnings = []
    if not version.get("available"):
        warnings.append("claude CLI missing")
    if settings.get("template_bridge_enabled"):
        warnings.append("template-bridge still enabled")
    if settings.get("claude_mem_enabled"):
        warnings.append("claude-mem enabled")
    return warnings


def claude_runtime_payload() -> dict[str, Any]:
    version = claude_version_summary()
    plugins = claude_plugins_summary()
    settings = claude_settings_summary()
    mcp = claude_mcp_runtime_snapshot()
    vscode_wsl = vscode_wsl_summary()
    aitmpl = claude_aitmpl_summary()
    warnings = claude_base_warnings(version, settings)
    if plugins.get("template_bridge_enabled") and "template-bridge still enabled" not in warnings:
        warnings.append("template-bridge still enabled")
    if mcp.get("available") and mcp.get("refresh_state") == "pending":
        warnings.append("claude mcp list pending")
    elif mcp.get("available") and not mcp.get("list_ok"):
        if mcp.get("refresh_state") == "stale":
            warnings.append("claude mcp list stale")
        else:
            warnings.append("claude mcp list timed out" if mcp.get("list_timed_out") else "claude mcp list failed")
    if not vscode_wsl.get("workspace_on_linux_fs"):
        warnings.append("workspace is not on Linux filesystem")
    agent_inventory = {
        "user_agents": len(claude_user_agent_paths()),
        "project_agents": len(claude_project_agent_paths()),
        "plugin_agents": len(claude_plugin_agent_paths()),
    }
    if public_release_mode():
        wrapper = plugins.get("wrapper") or claude_wrapper_plugin_inventory()
        agent_inventory.update(
            {
                "wrapper_plugin_agents": wrapper["agents"],
                "wrapper_scope": wrapper["mode"],
                "wrapper_runtime_load_verified": wrapper["runtime_load_verified"],
            }
        )
    return {
        "id": "claude",
        "label": "Claude Code CLI",
        "status": "warn" if warnings else "ok",
        "warnings": warnings,
        "home": str(claude_home()),
        "version": version,
        "plugins": plugins,
        "agents": claude_agents_summary(),
        "agent_inventory": agent_inventory,
        "aitmpl": aitmpl,
        "settings": settings,
        "memory": claude_memory_summary(),
        "mcp": mcp,
        "vscode_wsl": vscode_wsl,
    }


def runtime_payload(runtime: str) -> dict[str, Any]:
    if runtime == "claude":
        return claude_runtime_payload()
    return codex_runtime_payload()


def context7_status() -> dict[str, Any]:
    config_path = codex_home() / "config.toml"
    config_text = read_text(config_path)
    inline_key = bool(re.search(r"ctx7sk-[A-Za-z0-9-]+", config_text))
    env_present = bool(os.environ.get("CONTEXT7_API_KEY"))
    env_file_present = any(
        path.exists()
        for path in [
            codex_home() / "context7.env",
            Path.home() / ".context7.env",
            Path.home() / ".config/codex/context7.env",
        ]
    )
    return {
        "env_present": env_present,
        "env_file_present": env_file_present,
        "inline_key_in_codex_config": inline_key,
        "config_path": str(config_path),
        "status": "ok" if (env_present or env_file_present) and not inline_key else "warn",
    }


def mcp_status() -> dict[str, Any]:
    codex_bin = shutil.which("codex")
    status: dict[str, Any] = {"codex_available": bool(codex_bin), "servers": [], "context7_get": "", "processes": {}}
    if codex_bin:
        listed = run([codex_bin, "mcp", "list"], timeout=10)
        status["servers"] = mask_secret_text(listed.stdout).splitlines()[:80]
        context7 = run([codex_bin, "mcp", "get", "context7"], timeout=8)
        status["context7_get"] = mask_secret_text((context7.stdout or context7.stderr).strip())
    ps = run(["ps", "-eo", "args"], timeout=5)
    if ps.returncode == 0:
        text = ps.stdout.lower()
        for name, needle in {
            "neuledge_context": "context serve",
            "context7": "@upstash/context7-mcp",
            "supabase": "@supabase/mcp-server-supabase",
        }.items():
            status["processes"][name] = text.count(needle)
    return status


def claude_aitmpl_text(payload: dict[str, Any]) -> str:
    lines = [
        "Claude aitmpl agent candidates",
        f"source: {payload['source_url']}",
        f"policy: {payload['policy']}",
        f"candidates: {payload['candidate_count']}",
        f"matching Claude agents: {payload['matching_agent_count']}",
        "vetting checklist:",
        *[f"- {item}" for item in payload.get("vetting_checklist", [])],
        "",
    ]
    for item in payload["candidates"]:
        marker = "matching-agent" if item["matching_claude_agent"] else "candidate"
        lines.append(f"- [{marker}] {item['agent_ref']} - {item['purpose']}")
        lines.append(f"  dry-run approval required: {item['dry_run_command']}")
        lines.append(f"  target: {item['install_target']}")
        for source in item.get("matching_sources", [])[:3]:
            plugin = f" plugin={source['plugin_id']}" if source.get("plugin_id") else ""
            lines.append(f"  match: {source['source_scope']}{plugin} {source['path']}")
    return "\n".join(lines)


def claude_agent_library_text(payload: dict[str, Any]) -> str:
    lines = [
        "Claude local agent library",
        f"source: {payload['source_url']}",
        f"policy: {payload['policy']}",
        f"library: {payload['library_dir']}",
        f"cache: {payload['cache_dir']}",
        f"project target: {payload['project_agents_dir']}",
        f"candidates: {payload['candidate_count']}",
        f"local templates: {payload['local_template_count']}",
        f"matching Claude agents: {payload['matching_agent_count']}",
        "",
    ]
    for item in payload["candidates"]:
        marker = "installed" if item["matching_claude_agent"] else "available"
        template = "local" if item["local_template_available"] else "generated"
        lines.append(f"- [{marker}/{template}] {item['agent_ref']} - {item['purpose']}")
        lines.append(f"  install project: {item['install_project_command']}")
        lines.append(f"  copy project: {item['copy_project_command']}")
    return "\n".join(lines)


def claude_agent_install_text(result: dict[str, Any]) -> str:
    lines = [
        f"Installed Claude agent: {result['name']}",
        f"scope: {result['scope']}",
        f"target: {result['target']}",
        f"source: {result['source_kind']} {result.get('source_path') or ''}".rstrip(),
    ]
    if result.get("restart_recommended"):
        lines.append("restart recommended: agents directory was created during this install")
    lines.append(result.get("note", ""))
    return "\n".join(line for line in lines if line)


def overview_payload() -> dict[str, Any]:
    from orch_panel import docs_context

    docs_context.bind(globals())
    skills = list_skill_paths()
    agents = list_agent_paths()
    codex_runtime = {
        "id": "codex",
        "label": "Codex",
        "status": "ok",
        "summary": f"{len(skills)} skills, {len(agents)} agents",
    }
    claude_version = claude_version_summary()
    claude_settings = claude_settings_summary()
    claude_warnings = claude_base_warnings(claude_version, claude_settings)
    claude_runtime = {
        "id": "claude",
        "label": "Claude Code CLI",
        "status": "warn" if claude_warnings else "ok",
        "summary": claude_version.get("version") or "not found",
        "warnings": claude_warnings,
    }
    return {
        "health": {"online": True, "timestamp": int(time.time())},
        "paths": {
            "console_dir": str(CONSOLE_DIR),
            "codex_home": str(codex_home()),
            "codex_asset_home": str(codex_asset_home()),
            "claude_home": str(claude_home()),
            "agents_home": str(agents_home()),
            "workspace": str(workspace_root()),
            "prompts_dir": str(PROMPTS_DIR),
            "prompt_manifest": str(PROMPT_MANIFEST_PATH),
            "state_dir": str(STATE_DIR),
        },
        "runtimes": {
            "active": "codex",
            "items": [codex_runtime, claude_runtime],
        },
        "prompts": {
            "source": "manifest" if manifest_prompts() else "missing",
            "manifest_exists": PROMPT_MANIFEST_PATH.exists(),
        },
        "tools": cached_runtime("tool-health", 300, tool_health),
        "catalog": catalog_summary(),
        "catalog_claude": claude_catalog_summary(),
        "docs_context": {
            "stack_path": str(docs_context.docs_stack_path()),
            "policy_path": str(docs_context.docs_policy_path()),
        },
        "skills": {
            "count": len(skills),
            "items": [{"name": path.parent.name, "path": str(path)} for path in skills],
        },
        "agents": {
            "count": len(agents),
            "items": [{"name": path.stem, "path": str(path)} for path in agents],
        },
        "beads": beads_summary(),
        "notes": {"path": str(NOTES_PATH), "preview": read_text(NOTES_PATH, 5000)},
    }


def panel_throughput_payload() -> dict[str, Any]:
    """Combine observed repository signals with an explicitly labelled estimate."""
    payload = throughput_payload(discover_repos())
    payload["simulation"] = simulate_proportional_orchestration(REPRESENTATIVE_WORKLOAD)
    return payload


REPO_DISCOVERY_CACHE: tuple[Path, float, list[Path], list[Path]] | None = None
REPO_DISCOVERY_LOCK = threading.Lock()
REPO_DISCOVERY_TTL_SECONDS = 30


def git_common_dir(path: Path) -> Path | None:
    result = run(["git", "rev-parse", "--git-common-dir"], cwd=path, timeout=3)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = path / common
    return common.resolve()


def prefer_repo_path(current: Path, candidate: Path) -> Path:
    def rank(path: Path) -> tuple[int, int, str]:
        return (0 if (path / ".git").is_dir() else 1, len(path.parts), str(path))

    return min((current, candidate), key=rank)


def scan_repo_workspace(root: Path) -> tuple[list[Path], list[Path]]:
    candidates: dict[Path, Path] = {}
    checkouts: set[Path] = set()
    ignored = {".git", ".codex", ".claude", ".worktrees", "worktrees", "node_modules", "vendor", "dist", "build"}
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in ignored:
            continue
        possible = [child]
        possible.extend(
            nested
            for nested in child.iterdir()
            if nested.is_dir() and nested.name not in ignored
        )
        for repo in possible:
            if not (repo / ".git").exists():
                continue
            common_dir = git_common_dir(repo)
            if common_dir is None:
                continue
            resolved = repo.resolve()
            checkouts.add(resolved)
            current = candidates.get(common_dir)
            candidates[common_dir] = resolved if current is None else prefer_repo_path(current, resolved)

    for repo in list(candidates.values()):
        result = run(["git", "worktree", "list", "--porcelain"], cwd=repo, timeout=5)
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            if not line.startswith("worktree "):
                continue
            worktree = Path(line.removeprefix("worktree ")).resolve()
            if worktree.is_dir():
                checkouts.add(worktree)
    return sorted(candidates.values()), sorted(checkouts)


def repo_discovery_snapshot() -> tuple[list[Path], list[Path]]:
    root = workspace_root()
    if not root.exists():
        return [], []
    resolved_root = root.resolve()
    now = time.monotonic()
    global REPO_DISCOVERY_CACHE
    with REPO_DISCOVERY_LOCK:
        cached = REPO_DISCOVERY_CACHE
        if cached and cached[0] == resolved_root and now - cached[1] <= REPO_DISCOVERY_TTL_SECONDS:
            return list(cached[2]), list(cached[3])
        repos, checkouts = scan_repo_workspace(resolved_root)
        REPO_DISCOVERY_CACHE = (resolved_root, time.monotonic(), repos, checkouts)
        return list(repos), list(checkouts)


def discover_repos() -> list[Path]:
    repos, _ = repo_discovery_snapshot()
    return repos


def discover_checkouts() -> list[Path]:
    _, checkouts = repo_discovery_snapshot()
    return checkouts


def default_branch(repo: Path) -> str | None:
    result = run(["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd=repo, timeout=3)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("/", 1)[-1]
    for name in ["main", "master", "dev", "develop"]:
        result = run(["git", "rev-parse", "--verify", "--quiet", name], cwd=repo, timeout=3)
        if result.returncode == 0:
            return name
        result = run(["git", "rev-parse", "--verify", "--quiet", f"origin/{name}"], cwd=repo, timeout=3)
        if result.returncode == 0:
            return name
    return None


def branch_ref(repo: Path, branch: str) -> str | None:
    for ref in [f"origin/{branch}", branch]:
        result = run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo, timeout=3)
        if result.returncode == 0:
            return ref
    return None


def repo_tails(repo: Path, threshold_days: int, now: int, base: str | None = None) -> list[dict[str, Any]]:
    base = base or default_branch(repo)
    if not base:
        return []
    base_ref = branch_ref(repo, base)
    if not base_ref:
        return []

    result = run(
        [
            "git",
            "for-each-ref",
            f"--no-merged={base_ref}",
            "--format=%(refname:short)%09%(committerdate:unix)%09%(objectname:short)%09%(subject)",
            "refs/heads",
            "refs/remotes",
        ],
        cwd=repo,
        timeout=10,
    )
    if result.returncode != 0:
        return []

    tails: list[dict[str, Any]] = []
    protected = {"main", "master", "dev", "develop", base, f"origin/{base}", "origin/HEAD"}
    for line in result.stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        ref, timestamp, commit, subject = parts
        if ref in protected or ref.endswith("/HEAD"):
            continue
        short_ref = ref.split("/", 1)[-1] if ref.startswith("origin/") else ref
        if short_ref in {"main", "master", "dev", "develop"}:
            continue
        try:
            ts = int(timestamp)
        except ValueError:
            continue
        age_days = int((now - ts) / 86400)
        if age_days < threshold_days:
            continue
        date = time.strftime("%Y-%m-%d", time.localtime(ts))
        tails.append(
            {
                "project": repo.name,
                "repo_path": str(repo),
                "branch": ref,
                "kind": "remote" if ref.startswith("origin/") else "local",
                "age_days": age_days,
                "commit": commit,
                "date": date,
                "subject": subject,
                "base": base_ref,
            }
        )
    return tails


def tails_payload(threshold_days: int = 5) -> dict[str, Any]:
    now = int(time.time())
    repos = discover_repos()
    tails: list[dict[str, Any]] = []
    radar: list[dict[str, Any]] = []

    def inspect_repo(repo: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        base = default_branch(repo)
        repo_tail_items = repo_tails(repo, threshold_days, now, base=base)
        return repo_tail_items, radar_row(repo, now, len(repo_tail_items), base)

    workers = min(8, len(repos))
    rows = list(ThreadPoolExecutor(max_workers=workers).map(inspect_repo, repos)) if workers else []
    for repo_tail_items, radar_item in rows:
        tails.extend(repo_tail_items)
        radar.append(radar_item)
    tails.sort(key=lambda item: (-int(item["age_days"]), item["project"], item["branch"]))
    radar.sort(
        key=lambda item: (
            -int(item["dirty"]),
            -(len(item["merged_branches"]) + len(item["worktrees"])),
            -int(item["tail_count"]),
            item["project"],
        )
    )
    return {
        "threshold_days": threshold_days,
        "repo_count": len(repos),
        "tails": tails,
        "radar": radar,
        "generated_at": now,
    }


def beads_candidates() -> list[Path]:
    return [CONSOLE_DIR, *discover_repos()]


def beads_payload(issue_limit: int | None = BEADS_ISSUE_LIMIT) -> dict[str, Any]:
    return beads_board_payload(beads_candidates(), issue_limit=issue_limit)


LATENCY_BUDGETS_MS = {
    "prompt_compose": 250,
    "overview": 2500,
    "repo_discovery": 1500,
    "tails": 5000,
    "throughput": 5000,
    "beads": 6500,
    "panel_server": 250,
}

# These checks spend most of their time in subprocesses and filesystem work,
# so host saturation can dominate the measurement. Above this load threshold,
# record the result as a host observation instead of gating the harness.
LATENCY_LOAD_PER_CPU_LIMIT = 1.0


def host_load_snapshot() -> dict[str, Any]:
    try:
        load_1m, load_5m, load_15m = os.getloadavg()
    except (AttributeError, OSError) as exc:  # pragma: no cover - platform guard
        return {"available": False, "error": str(exc)}
    cpu_count = os.cpu_count() or 1
    return {
        "available": True,
        "load_1m": round(load_1m, 2),
        "load_5m": round(load_5m, 2),
        "load_15m": round(load_15m, 2),
        "cpu_count": cpu_count,
        "per_cpu": round(load_1m / cpu_count, 2),
        "limit_per_cpu": LATENCY_LOAD_PER_CPU_LIMIT,
        "oversubscribed": load_1m / cpu_count >= LATENCY_LOAD_PER_CPU_LIMIT,
    }


def panel_server_snapshot(host: str, port: int) -> dict[str, Any]:
    try:
        with urlopen(f"http://{host}:{port}/api/health", timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"online": False, "build_id": None, "error": str(exc)}
    observed = payload.get("build_id")
    return {
        "online": bool(payload.get("online")),
        "build_id": observed,
        "current": observed == PANEL_BUILD_ID,
    }


def over_budget_checks(checks: list[dict[str, Any]], *, load_bound: bool = False) -> list[str]:
    """Checks that can fail a benchmark run.

    A check status of `warn` also covers environment conditions such as an
    offline panel server. Only an error or a genuine budget overrun is a
    failure, otherwise the gate would fire whenever the panel is not running.

    `load_bound` says the host was oversubscribed while the run was taken. An
    overrun measured there is not evidence about this code, so it stays out of
    the gate; an error still fails, because a check that raised did not measure
    anything either way.
    """

    return [
        item["name"]
        for item in checks
        if item["status"] == "error"
        or (not load_bound and item["elapsed_ms"] > item["budget_ms"])
    ]


def latency_benchmark_payload(quick: bool, host: str, port: int) -> dict[str, Any]:
    load_before = host_load_snapshot()
    started = time.perf_counter()
    checks: list[dict[str, Any]] = []

    def measure(name: str, builder: Any) -> None:
        check_started = time.perf_counter()
        try:
            detail = builder()
            error = None
        except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
            detail = None
            error = mask_secret_text(str(exc))
        elapsed_ms = round((time.perf_counter() - check_started) * 1000, 1)
        budget_ms = LATENCY_BUDGETS_MS[name]
        status = "error" if error else ("pass" if elapsed_ms <= budget_ms else "warn")
        checks.append(
            {
                "name": name,
                "status": status,
                "elapsed_ms": elapsed_ms,
                "budget_ms": budget_ms,
                "detail": detail,
                "error": error,
            }
        )

    def prompt_detail() -> dict[str, Any]:
        payload = prompt_payload(runtime="codex", profile_id="gpt-6-astra")
        return {"prompt_count": len(payload.get("prompts") or []), "profile": (payload.get("active_profile") or {}).get("id")}

    def overview_detail() -> dict[str, Any]:
        payload = overview_payload()
        return {"skills": payload["skills"]["count"], "agents": payload["agents"]["count"]}

    def repo_detail() -> dict[str, Any]:
        repos = discover_repos()
        return {"unique_git_repositories": len(repos)}

    measure("prompt_compose", prompt_detail)
    measure("overview", overview_detail)
    measure("repo_discovery", repo_detail)
    if not quick:
        measure("tails", lambda: {"repo_count": tails_payload(5)["repo_count"]})
        measure("throughput", lambda: {"repo_count": panel_throughput_payload()["totals"]["repo_count"]})
        measure("beads", lambda: {"repo_count": len(beads_payload().get("repos") or [])})
    measure("panel_server", lambda: panel_server_snapshot(host, port))

    server_check = next(item for item in checks if item["name"] == "panel_server")
    snapshot = server_check.get("detail") or {}
    if server_check["status"] == "pass" and (not snapshot.get("online") or not snapshot.get("current")):
        server_check["status"] = "warn"
        server_check["error"] = "panel server is offline or runs a stale build"

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    total_budget_ms = 3500 if quick else 12000
    load_after = host_load_snapshot()
    # Load climbing during the run counts: the arms of the accepted c1a series
    # were compared across different load windows, which is what made its
    # speedup unreproducible.
    load_bound = bool(load_before.get("oversubscribed") or load_after.get("oversubscribed"))
    status = "pass" if elapsed_ms <= total_budget_ms and all(item["status"] == "pass" for item in checks) else "warn"
    over_budget = over_budget_checks(checks, load_bound=load_bound)
    within_total = elapsed_ms <= total_budget_ms or load_bound
    return {
        "schema_version": "orchestration-latency/v1",
        "build_id": PANEL_BUILD_ID,
        "status": status,
        "budget_status": "pass" if not over_budget and within_total else "warn",
        "over_budget": over_budget,
        "load_bound": load_bound,
        "load_bound_checks": sorted(
            item["name"]
            for item in checks
            if load_bound and item["status"] != "error" and item["elapsed_ms"] > item["budget_ms"]
        ),
        "load": {"before": load_before, "after": load_after},
        "quick": quick,
        "elapsed_ms": elapsed_ms,
        "budget_ms": total_budget_ms,
        "checks": checks,
    }


def latency_benchmark_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Harness latency benchmark: {payload['status']}",
        f"budget: {payload['budget_status']}"
        + (f" (over: {', '.join(payload['over_budget'])})" if payload["over_budget"] else ""),
        f"build: {payload['build_id']}",
        f"total: {payload['elapsed_ms']} ms / budget {payload['budget_ms']} ms",
    ]
    load = (payload.get("load") or {}).get("before") or {}
    if load.get("available"):
        lines.append(
            f"host load: {load['load_1m']} over {load['cpu_count']} cpus "
            f"({load['per_cpu']} per cpu, limit {load['limit_per_cpu']})"
        )
    if payload.get("load_bound"):
        named = ", ".join(payload.get("load_bound_checks") or []) or "none"
        lines.append(
            f"load-bound: host was oversubscribed, budgets not gating (over: {named})"
        )
    for item in payload["checks"]:
        suffix = f" — {item['error']}" if item.get("error") else ""
        lines.append(f"- {item['name']}: {item['elapsed_ms']} ms / {item['budget_ms']} ms [{item['status']}]{suffix}")
    return "\n".join(lines)


PANEL_SERVER_NAME = "CodexOrchestrationPanel/1.0"
STATIC_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
    ".png": "image/png",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


# The coordination HTTP glue moved to `orch_panel.coordination.panel_api`.
# `__getattr__` re-exports it lazily so importing either module first is safe
# and every caller and test keeps naming `orchestration_panel.<name>`.
_EXTRACTED_MODULES = (
    "orch_panel.coordination.panel_api",
    "orch_panel.docs_context",
)


def __getattr__(name: str) -> Any:
    import importlib as _importlib

    for module_name in _EXTRACTED_MODULES:
        module = _importlib.import_module(module_name)
        if not hasattr(module, name):
            continue
        # Bind on every lookup rather than caching in `globals()`: a test that
        # loads its own copy of this panel must get glue that reads that copy's
        # state directory and adapters, not the first one imported.
        module.bind(globals())
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")




def uuid_hex() -> str:
    """Panel-generated id for a record the caller does not name (epic, project).

    Deliberately not used for idempotency keys: those belong to the caller.
    """
    return hashlib.sha256(f"{time.time_ns()}:{os.getpid()}".encode()).hexdigest()[:16]


@dataclass(frozen=True)
class PanelResponse:
    """One transport-neutral HTTP result; the ASGI layer only serialises it."""

    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


def json_response(payload: Any, status: int = 200) -> PanelResponse:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return PanelResponse(
        status,
        (
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(data))),
        ),
        data,
    )


DEFAULT_ERROR_MESSAGES = {
    400: "bad request",
    403: "forbidden",
    404: "not found",
    405: "method not allowed",
    500: "internal panel error",
}


def error_response(status: int, message: str | None = None) -> PanelResponse:
    """One JSON error shape for every panel reply.

    The panel used to reproduce `http.server`'s HTML error page byte for byte,
    including `Connection: close`, long after it stopped being an http.server.
    A client of a JSON API gets JSON.
    """
    return json_response(
        {"error": message or DEFAULT_ERROR_MESSAGES.get(status, "request failed")},
        status=status,
    )


def method_not_allowed_response(method: str) -> PanelResponse:
    """Any verb the panel does not implement. GET, HEAD and POST are the set."""
    response = error_response(405, message=f"method not allowed: {method}")
    return PanelResponse(
        response.status,
        (*response.headers, ("Allow", "GET, HEAD, POST")),
        response.body,
    )


class QueryParamError(ValueError):
    """A query parameter the caller has to fix, not a panel failure."""


def query_int(
    query: dict[str, list[str]],
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Read one numeric query parameter, clamped, or refuse it as a 400.

    `int(query[...])` used to run unguarded, so `?days=soon` reached the
    catch-all and came back as a 500 carrying the raw `ValueError` text.
    """
    raw = (query.get(name, [""])[0] or "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise QueryParamError(f"{name} must be a whole number") from exc
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def file_response(path: Path) -> PanelResponse:
    if not path.exists() or not path.is_file():
        return error_response(404)
    data = path.read_bytes()
    return PanelResponse(
        200,
        (
            ("Content-Type", STATIC_CONTENT_TYPES.get(path.suffix, "application/octet-stream")),
            ("Content-Length", str(len(data))),
            ("Cache-Control", "no-store"),
        ),
        data,
    )


def allowed_repo_paths() -> set[Path]:
    """Every repository a request may name. Rebuilt once, not four times."""
    return {CONSOLE_DIR.resolve(), *(item.resolve() for item in discover_repos())}


def requested_repo(query: dict[str, list[str]], allowed: set[Path]) -> Path | None:
    raw = (query.get("repo", [""])[0] or "").strip()
    if not raw:
        return None
    repo = Path(raw).resolve()
    return repo if repo in allowed else None


def panel_get(path: str, query: dict[str, list[str]]) -> PanelResponse:
    """Blocking GET dispatch; the ASGI layer runs this off the event loop."""
    from orch_panel import docs_context
    from orch_panel.coordination import panel_api

    panel_api.bind(globals())
    docs_context.bind(globals())
    try:
        if path == "/api/health":
            return json_response({"online": True, "timestamp": int(time.time()), "build_id": PANEL_BUILD_ID})
        if path == "/api/settings":
            return json_response(panel_settings_payload())
        if path == "/api/prompts":
            runtime = query.get("runtime", [None])[0]
            if runtime not in {None, "codex", "claude"}:
                return json_response({"error": "unknown runtime"}, status=400)
            profile = query.get("profile", [None])[0]
            try:
                payload = prompt_payload(runtime=runtime, profile_id=profile)
            except ValueError as exc:
                return json_response({"error": str(exc)}, status=400)
            return json_response(payload)
        if path == "/api/overview":
            return json_response(overview_payload())
        if path.startswith("/api/runtime/"):
            runtime = path.rsplit("/", 1)[-1]
            if runtime not in {"codex", "claude"}:
                return json_response({"error": "unknown runtime"}, status=404)
            return json_response(runtime_payload(runtime))
        if path == "/api/docs-context":
            fresh = query.get("fresh", ["0"])[0] == "1"
            return json_response(
                cached_payload(
                    "docs-context", 60, docs_context.docs_context_payload, fresh=fresh
                )
            )
        if path == "/api/claude-agents":
            return json_response(claude_agent_library_payload())
        if path == "/api/coordination":
            return json_response(panel_api.coordination_overview_payload())
        if path == "/api/coordination/events":
            epic_id = query.get("epic_id", [""])[0]
            if not epic_id:
                return json_response({"error": "missing epic_id"}, status=400)
            return json_response(
                panel_api.coordination_events_payload(
                    epic_id,
                    beads_issue_id=query.get("beads_issue_id", [""])[0] or None,
                    after_seq=query_int(query, "after_seq", 0, minimum=0),
                    limit=query_int(query, "limit", 500, minimum=1, maximum=2000),
                )
            )
        if path == "/api/coordination/dispatches":
            epic_id = query.get("epic_id", [""])[0]
            if not epic_id:
                return json_response({"error": "missing epic_id"}, status=400)
            return json_response(panel_api.coordination_dispatches_payload(epic_id))
        if path == "/api/coordination/board":
            epic_id = query.get("epic_id", [""])[0]
            if not epic_id:
                return json_response({"error": "missing epic_id"}, status=400)
            return json_response(panel_api.coordination_board_payload(epic_id))
        if path == "/api/coordination/planning-artifacts":
            epic_id = query.get("epic_id", [""])[0]
            if not epic_id:
                return json_response({"error": "missing epic_id"}, status=400)
            return json_response(panel_api.coordination_planning_payload(epic_id))
        if path == "/api/coordination/reviews":
            epic_id = query.get("epic_id", [""])[0]
            if not epic_id:
                return json_response({"error": "missing epic_id"}, status=400)
            return json_response(
                panel_api.coordination_reviews_payload(
                    epic_id, query.get("beads_issue_id", [""])[0] or None
                )
            )
        if path == "/api/beads":
            raw_limit = query.get("limit", [str(BEADS_ISSUE_LIMIT)])[0]
            if raw_limit == "all":
                issue_limit = None
            else:
                issue_limit = query_int(query, "limit", BEADS_ISSUE_LIMIT)
                if issue_limit < 1:
                    raise QueryParamError("limit must be 'all' or a positive number")
            fresh = query.get("fresh", ["0"])[0] == "1"
            cache_limit = "all" if issue_limit is None else str(issue_limit)
            return json_response(
                cached_payload(
                    f"beads:{cache_limit}",
                    120,
                    lambda: beads_payload(issue_limit),
                    fresh=fresh,
                )
            )
        if path == "/api/telemetry":
            fresh = query.get("fresh", ["0"])[0] == "1"
            return json_response(cached_payload("telemetry", 30, lambda: stage_telemetry_payload(discover_checkouts()), fresh=fresh))
        if path == "/api/throughput":
            fresh = query.get("fresh", ["0"])[0] == "1"
            return json_response(cached_payload("throughput", 30, panel_throughput_payload, fresh=fresh))
        if path in {"/api/github/sync-status", "/api/github/issues", "/api/tails/prs"}:
            repo = requested_repo(query, allowed_repo_paths())
            if repo is None:
                return json_response({"error": "unknown repo"}, status=400)
            fresh = query.get("fresh", ["0"])[0] == "1"
            if path == "/api/github/sync-status":
                return json_response(github_sync_status(repo))
            if path == "/api/github/issues":
                return json_response(
                    cached_payload(
                        f"github-issues:{repo}", 120, lambda: github_issues_payload(repo), fresh=fresh
                    )
                )
            return json_response(
                cached_payload(f"tails-prs:{repo}", 300, lambda: tails_pr_payload(repo), fresh=fresh)
            )
        if path == "/api/tails":
            days = query_int(query, "days", 5, minimum=1, maximum=365)
            fresh = query.get("fresh", ["0"])[0] == "1"
            return json_response(cached_payload(f"tails-{days}", 60, lambda: tails_payload(days), fresh=fresh))
        if path == "/api" or path.startswith("/api/"):
            return error_response(404)
        if path == "/legacy" or path.startswith("/legacy/"):
            return error_response(404)
        if path in {"/", "/index.html"}:
            return file_response(WEB_DIR / "index.html")
        safe = Path(path.lstrip("/"))
        if ".." in safe.parts or safe.is_absolute():
            return error_response(400)
        candidate = WEB_DIR / safe
        if candidate.is_file():
            return file_response(candidate)
        public_candidate = WEB_ROOT / "public" / safe
        if public_candidate.is_file():
            return file_response(public_candidate)
        if safe.suffix:
            return error_response(404)
        return file_response(WEB_DIR / "index.html")
    except QueryParamError as exc:
        return json_response({"error": str(exc)}, status=400)
    except Exception as exc:  # pragma: no cover - defensive endpoint guard
        return internal_error_response(exc)


def internal_error_response(exc: BaseException) -> PanelResponse:
    """One 500 shape that never hands a caller an unmasked exception string.

    The endpoint guards used to return `str(exc)` verbatim, so a path, a token
    in an environment variable, or a subprocess command line could leave the
    machine through an error body.
    """
    return json_response(
        {
            "error": DEFAULT_ERROR_MESSAGES[500],
            "detail": mask_secret_text(f"{type(exc).__name__}: {exc}")[:500],
        },
        status=500,
    )


def panel_post(path: str, raw_body: bytes) -> PanelResponse:
    """Blocking POST dispatch; the ASGI layer runs this off the event loop."""
    from orch_panel.coordination import panel_api

    panel_api.bind(globals())
    try:
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return json_response(
                {"error": f"request body is not valid JSON: {exc.__class__.__name__}"},
                status=400,
            )
        if not isinstance(payload, dict):
            return json_response({"error": "request body must be a JSON object"}, status=400)
        if path == "/api/settings":
            try:
                return json_response(update_panel_settings(payload))
            except ValueError as exc:
                return json_response({"error": str(exc)}, status=400)
        if path.startswith("/api/coordination"):
            return panel_api.coordination_post(path, payload)
        if path == "/api/claude-agents/install":
            agent_name = str(payload.get("name", "")).strip()
            scope = str(payload.get("scope", "project")).strip() or "project"
            overwrite = bool(payload.get("overwrite", False))
            if not agent_name:
                return json_response({"error": "missing name"}, status=400)
            return json_response(
                install_claude_agent_from_library(agent_name, scope=scope, overwrite=overwrite)
            )
        if path != "/api/prompts/usage":
            return error_response(404)
        prompt_id = str(payload.get("id", "")).strip()
        if not prompt_id:
            return json_response({"error": "missing id"}, status=400)
        usage = increment_usage(
            prompt_id,
            mode=str(payload.get("mode", "")).strip(),
            runtime=str(payload.get("runtime", "")).strip(),
            profile=str(payload.get("profile", "")).strip(),
        )
        return json_response({"id": prompt_id, "usage_count": usage[prompt_id]})
    except Exception as exc:  # pragma: no cover - defensive endpoint guard
        return internal_error_response(exc)


def serve(host: str, port: int) -> None:
    global SERVER_MODE
    SERVER_MODE = True
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import uvicorn

        from orch_panel.asgi_app import build_app
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        print(
            f"Панель требует ASGI-зависимости ({exc.name}). Установите их: uv sync",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    app = build_app(sys.modules[__name__], host=host, port=port)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
        server_header=False,
        headers=[("server", PANEL_SERVER_NAME)],
        timeout_graceful_shutdown=5,
    )
    print(f"Панель оркестрации: http://{host}:{port}/")
    uvicorn.Server(config).run()


def main() -> int:
    """Delegate to `orch_panel.cli`, imported here so the two never cycle."""
    from orch_panel.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
