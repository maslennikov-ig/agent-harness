"""Docs L1/L2 resolution: inventory, sync plan, signatures, and debt.

Everything the panel knows about dependency documentation lives here — reading
lockfiles, choosing a `@neuledge/context` package, running the resolver,
persisting an L2 answer, and rendering all of it as text. `orchestration_panel`
keeps the routes and re-exports these names.

The panel is reached through a bound namespace rather than an import, so a test
that loads its own copy of the panel and repoints `STATE_DIR` is the copy this
module reads.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

try:  # pragma: no cover - Python 3.11+ ships tomllib
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - older interpreters
    tomllib = None
from collections.abc import Callable
from pathlib import Path
from typing import Any

_BOUND_NAMESPACE: dict[str, Any] | None = None


def bind(namespace: dict[str, Any]) -> None:
    """Name the panel namespace this module reads."""
    global _BOUND_NAMESPACE
    _BOUND_NAMESPACE = namespace


def panel_namespace() -> dict[str, Any]:
    global _BOUND_NAMESPACE
    if _BOUND_NAMESPACE is None:
        import orchestration_panel

        _BOUND_NAMESPACE = vars(orchestration_panel)
    return _BOUND_NAMESPACE


class _PanelProxy:
    """Forward every attribute to the panel namespace currently bound."""

    def __getattr__(self, name: str) -> Any:
        namespace = panel_namespace()
        if name in namespace:
            return namespace[name]
        try:
            return globals()[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


panel = _PanelProxy()


DEFAULT_CONTEXT_PACKAGES_DIR = Path.home() / ".context" / "packages"
DOCS_CONTEXT_DIRNAME = "docs-context"
DOCS_CONTEXT_STACK = "stack.json"
DOCS_CONTEXT_POLICY = "policy.md"
DOCS_CONTEXT_PACKAGE_LIMIT = 2000
DOCS_RESOLVE_RESULT_LIMIT = 5
DOCS_POLICY_TEXT = """# Docs Context L1/L2 Policy

Use the Docs Resolver as the required entrypoint for dependency documentation.
It routes by lockfile package/version, queries @neuledge/context L1 first, can
auto-download registry-backed L1 docs for uncovered tracks, and if an exact registry
version is unavailable it tries a newer patch in the same major.minor track
before falling back. It records evidence in `stack.json`. @neuledge/context
remains the local/global L1 package store backed by packages in
`~/.context/packages/`.

Fall back to Context7 MCP only as L2 when L1 is missing, stale for the
project's dependency version, or does not return relevant sections. Context7
must read its key from `CONTEXT7_API_KEY`; do not hardcode keys in tracked
files or command arguments.

Version rule: route documentation by ecosystem/name plus major.minor. The L1
documentation package for a track must be the same version as, or newer than,
the latest dependency version used in that track. Floating `latest`, another
major.minor track, or older docs are fallback conditions, never authoritative
L1 hits.

When a dependency is upgraded to a target/LTS version, inspect the lockfile
diff and update or verify the matching L1 documentation package before merge.

`context` and Context7 expose MCP tools; empty MCP resources/templates do not
prove either provider unavailable. Diagnose both Codex and Claude with
`orch-prompts docs-diagnose --json`. Direct MCP tool injection is optional for
this workflow because `docs-resolve` queries L1 through the Harness wrapper.
Open a fresh task after Harness skill changes; restart the Codex/Claude host
only after an actual MCP configuration change, then open a fresh task.
"""

DOCS_RELEVANT_PACKAGES = {
    "@ai-sdk/openai",
    "@anthropic-ai/sdk",
    "@hookform/resolvers",
    "@langchain/core",
    "@langchain/langgraph",
    "@modelcontextprotocol/sdk",
    "@nestjs/common",
    "@nestjs/core",
    "@playwright/test",
    "@prisma/client",
    "@supabase/ssr",
    "@supabase/supabase-js",
    "@tanstack/react-query",
    "@trpc/client",
    "@trpc/react-query",
    "@trpc/server",
    "ai",
    "astro",
    "better-auth",
    "bullmq",
    "django",
    "drizzle-orm",
    "express",
    "fastapi",
    "flask",
    "grammy",
    "hono",
    "jest",
    "langchain",
    "langfuse",
    "mongoose",
    "next",
    "next-auth",
    "next-intl",
    "openai",
    "playwright",
    "prisma",
    "pydantic",
    "pytest",
    "react",
    "react-dom",
    "react-hook-form",
    "react-router",
    "remix",
    "svelte",
    "tailwindcss",
    "telegraf",
    "trpc",
    "typescript",
    "vite",
    "vitest",
    "vue",
    "zod",
    "zustand",
}

DOCS_PACKAGE_ALIASES = {
    "@prisma/client": ["prisma", "client"],
    "@supabase/supabase-js": ["supabase", "supabase-js"],
    "@supabase/ssr": ["supabase", "ssr"],
    "@tanstack/react-query": ["tanstack-query", "react-query"],
    "@trpc/client": ["@trpc/server", "trpc"],
    "@trpc/react-query": ["@trpc/server", "trpc"],
    "@trpc/server": ["trpc"],
    "@nestjs/common": ["nestjs"],
    "@nestjs/core": ["nestjs"],
    "@playwright/test": ["playwright"],
    "@ai-sdk/openai": ["ai-sdk", "ai"],
    "ai": ["ai-sdk"],
    "next": ["nextjs", "next.js"],
    "react-dom": ["react"],
}

DOCS_REGISTRY_PACKAGES = {
    "@prisma/client": "prisma",
    "@supabase/ssr": "supabase",
    "@supabase/supabase-js": "supabase",
    "@trpc/client": "@trpc/server",
    "@trpc/react-query": "@trpc/server",
    "@trpc/server": "@trpc/server",
    "@nestjs/common": "nestjs",
    "@nestjs/core": "nestjs",
    "next-auth": "authjs",
    "react-dom": "react",
}

DOCS_PRIORITY_PACKAGES = {
    "@langchain/core",
    "@langchain/langgraph",
    "@modelcontextprotocol/sdk",
    "@nestjs/common",
    "@nestjs/core",
    "@prisma/client",
    "@supabase/ssr",
    "@supabase/supabase-js",
    "@trpc/client",
    "@trpc/react-query",
    "@trpc/server",
    "ai",
    "better-auth",
    "bullmq",
    "drizzle-orm",
    "next",
    "openai",
    "prisma",
    "react",
    "tailwindcss",
    "typescript",
    "vite",
    "vitest",
    "zod",
}


def docs_context_dir() -> Path:
    return panel.agents_home() / DOCS_CONTEXT_DIRNAME


def docs_stack_path() -> Path:
    return docs_context_dir() / DOCS_CONTEXT_STACK


def docs_policy_path() -> Path:
    return docs_context_dir() / DOCS_CONTEXT_POLICY


def ensure_docs_policy() -> None:
    path = docs_policy_path()
    current = panel.read_text(path)
    if current.strip() != DOCS_POLICY_TEXT.strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DOCS_POLICY_TEXT, encoding="utf-8")


def clean_version(value: Any) -> str:
    text = str(value or "").strip().strip('"').strip("'")
    text = text.split("(", 1)[0].strip()
    text = text.lstrip("^~>=< ")
    match = re.search(r"\d+(?:\.\d+){0,3}(?:[-+][0-9A-Za-z.-]+)?", text)
    return match.group(0) if match else text


def semver_tuple(value: Any) -> tuple[int, int, int] | None:
    cleaned = clean_version(value)
    match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", cleaned)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def semver_key(value: str) -> tuple[int, int, int, str]:
    parsed = semver_tuple(value)
    if not parsed:
        return (-1, -1, -1, value)
    return (*parsed, value)


def semver_track(value: str) -> str:
    parsed = semver_tuple(value)
    if not parsed:
        return "unknown"
    return f"{parsed[0]}.{parsed[1]}"


def version_at_least(candidate: str, target: str) -> bool:
    candidate_tuple = semver_tuple(candidate)
    target_tuple = semver_tuple(target)
    return bool(candidate_tuple and target_tuple and candidate_tuple >= target_tuple)


def same_major(candidate: str, target: str) -> bool:
    candidate_tuple = semver_tuple(candidate)
    target_tuple = semver_tuple(target)
    return bool(candidate_tuple and target_tuple and candidate_tuple[0] == target_tuple[0])


def normalize_package_name(name: str) -> str:
    return name.strip().lower()


def docs_package_candidates(name: str) -> list[str]:
    normalized = normalize_package_name(name)
    candidates = [normalized]
    if normalized.startswith("@") and "/" in normalized:
        candidates.append(normalized.split("/", 1)[1])
    candidates.extend(DOCS_PACKAGE_ALIASES.get(normalized, []))
    seen: set[str] = set()
    return [item for item in candidates if not (item in seen or seen.add(item))]


def context_package_file_name(name: str, version: str) -> str:
    safe_name = name.replace("/", "__")
    safe_version = version.replace("/", "__")
    return f"{safe_name}@{safe_version}.db"


def read_context_package_info(path: Path) -> dict[str, Any] | None:
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            meta = {key: value for key, value in con.execute("SELECT key, value FROM meta")}
            name = normalize_package_name(meta.get("name", ""))
            version = clean_version(meta.get("version", ""))
            if not name or not version:
                return None
            section_count = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
        finally:
            con.close()
        return {
            "name": name,
            "version": version,
            "description": meta.get("description", ""),
            "sourceUrl": meta.get("source_url", ""),
            "path": str(path),
            "sizeBytes": path.stat().st_size,
            "sectionCount": int(section_count),
        }
    except (OSError, sqlite3.Error, ValueError):
        return None


def context_package_file_inventory(packages_dir: Path | None = None) -> list[dict[str, Any]]:
    root = packages_dir or DEFAULT_CONTEXT_PACKAGES_DIR
    if not root.exists():
        return []
    packages: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.db")):
        info = read_context_package_info(path)
        if info:
            packages.append(info)
    return packages


def merge_context_packages(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for group in groups:
        for package in group:
            key = (normalize_package_name(package.get("name", "")), clean_version(package.get("version", "")))
            if not all(key):
                continue
            current = merged.get(key)
            if current is None or (not current.get("path") and package.get("path")):
                merged[key] = {**package, "name": key[0], "version": key[1]}
    return sorted(merged.values(), key=lambda item: (item["name"], semver_key(item["version"])))


def docs_fts_query(topic: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r'[^\w\s"]', " ", topic).strip()).strip()


def query_context_package(package: dict[str, Any], topic: str, limit: int = DOCS_RESOLVE_RESULT_LIMIT) -> list[dict[str, str]]:
    path_text = package.get("path")
    if not path_text:
        return []
    query = docs_fts_query(topic)
    if not query:
        return []
    try:
        con = sqlite3.connect(f"file:{Path(path_text)}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                """
                SELECT
                  c.doc_path AS source,
                  c.doc_title AS doc_title,
                  c.section_title AS section_title,
                  c.content AS content,
                  (bm25(chunks_fts, 5.0, 10.0, 1.0) * -1) AS score
                FROM chunks_fts
                JOIN chunks c ON chunks_fts.rowid = c.id
                WHERE chunks_fts MATCH ?
                ORDER BY score DESC
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    return [
        {
            "title": f"{row['doc_title']} > {row['section_title']}",
            "content": row["content"],
            "source": row["source"],
        }
        for row in rows
    ]


def npm_prod_dependencies(package_json: Path) -> set[str]:
    data = panel.load_json(package_json, {})
    deps: set[str] = set()
    if isinstance(data, dict):
        deps.update((data.get("dependencies") or {}).keys())
        deps.update((data.get("optionalDependencies") or {}).keys())
    return deps


def package_lock_dependencies(lock_path: Path) -> list[dict[str, str]]:
    data = panel.load_json(lock_path, {})
    if not isinstance(data, dict):
        return []
    root = data.get("packages", {}).get("", {}) if isinstance(data.get("packages"), dict) else {}
    direct = set((root.get("dependencies") or {}).keys())
    direct.update((root.get("optionalDependencies") or {}).keys())
    direct.update((root.get("devDependencies") or {}).keys())
    if not direct and (lock_path.parent / "package.json").exists():
        direct = npm_prod_dependencies(lock_path.parent / "package.json")

    packages = data.get("packages") if isinstance(data.get("packages"), dict) else {}
    legacy = data.get("dependencies") if isinstance(data.get("dependencies"), dict) else {}
    result: list[dict[str, str]] = []
    for name in sorted(direct):
        version = ""
        record = packages.get(f"node_modules/{name}") if isinstance(packages, dict) else None
        if isinstance(record, dict):
            version = clean_version(record.get("version"))
        if not version and isinstance(legacy.get(name), dict):
            version = clean_version(legacy[name].get("version"))
        if version:
            result.append({"ecosystem": "npm", "name": name, "version": version, "source": str(lock_path)})
    return result


def pnpm_lock_dependencies(lock_path: Path) -> list[dict[str, str]]:
    text = panel.read_text(lock_path)
    package_json_paths = [lock_path.parent / "package.json", *lock_path.parent.glob("*/package.json"), *lock_path.parent.glob("*/*/package.json")]
    direct_names: set[str] = set()
    for package_json in package_json_paths:
        if "node_modules" in package_json.parts:
            continue
        direct_names.update(npm_prod_dependencies(package_json))

    result: list[dict[str, str]] = []
    for name in sorted(direct_names):
        escaped = re.escape(name)
        pattern = re.compile(
            rf"^[ \t]*['\"]?{escaped}['\"]?:\n(?:[ \t]+[A-Za-z0-9_-]+:[^\n]*\n)*?[ \t]+version:[ \t]*['\"]?([^'\"\n]+)",
            re.MULTILINE,
        )
        match = pattern.search(text)
        if match:
            result.append({"ecosystem": "npm", "name": name, "version": clean_version(match.group(1)), "source": str(lock_path)})
    return result


def requirements_dependencies(path: Path) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for line in panel.read_text(path).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)==([^;\s]+)", line)
        if match:
            result.append(
                {
                    "ecosystem": "pip",
                    "name": match.group(1).replace("_", "-").lower(),
                    "version": clean_version(match.group(2)),
                    "source": str(path),
                }
            )
    return result


def dependency_name_from_spec(spec: str) -> str:
    text = spec.split(";", 1)[0].strip()
    match = re.match(r"([A-Za-z0-9_.-]+)", text)
    return match.group(1).replace("_", "-").lower() if match else ""


def dependency_version_from_spec(spec: str) -> str:
    text = spec.split(";", 1)[0].strip()
    match = re.search(r"(?:==|>=|~=|>|<=|<)\s*([0-9][^,\s]+)", text)
    return clean_version(match.group(1)) if match else ""


def pyproject_direct_specs(path: Path) -> dict[str, str]:
    if tomllib is None or not path.exists():
        return {}
    try:
        data = tomllib.loads(panel.read_text(path))
    except Exception:
        return {}
    specs: dict[str, str] = {}
    project_deps = data.get("project", {}).get("dependencies", [])
    if isinstance(project_deps, list):
        for spec in project_deps:
            if isinstance(spec, str):
                name = dependency_name_from_spec(spec)
                if name:
                    specs[name] = spec
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if isinstance(poetry_deps, dict):
        for raw_name, raw_spec in poetry_deps.items():
            name = normalize_package_name(str(raw_name).replace("_", "-"))
            if name == "python":
                continue
            if isinstance(raw_spec, str):
                specs[name] = f"{name}{raw_spec}"
            elif isinstance(raw_spec, dict) and isinstance(raw_spec.get("version"), str):
                specs[name] = f"{name}{raw_spec['version']}"
    return specs


def pyproject_dependencies(path: Path) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for name, spec in sorted(pyproject_direct_specs(path).items()):
        version = dependency_version_from_spec(spec)
        if version:
            result.append({"ecosystem": "pip", "name": name, "version": version, "source": str(path)})
    return result


def toml_lock_dependencies(lock_path: Path, direct_specs: dict[str, str]) -> list[dict[str, str]]:
    if tomllib is None:
        return []
    try:
        data = tomllib.loads(panel.read_text(lock_path))
    except Exception:
        return []
    packages = data.get("package", [])
    if not isinstance(packages, list):
        return []
    direct_names = set(direct_specs)
    result: list[dict[str, str]] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = normalize_package_name(str(package.get("name", "")).replace("_", "-"))
        version = clean_version(package.get("version", ""))
        if name and version and name in direct_names:
            result.append({"ecosystem": "pip", "name": name, "version": version, "source": str(lock_path)})
    return result


def uv_lock_dependencies(lock_path: Path) -> list[dict[str, str]]:
    return toml_lock_dependencies(lock_path, pyproject_direct_specs(lock_path.parent / "pyproject.toml"))


def poetry_lock_dependencies(lock_path: Path) -> list[dict[str, str]]:
    return toml_lock_dependencies(lock_path, pyproject_direct_specs(lock_path.parent / "pyproject.toml"))


def project_name_for(path: Path, root: Path | None = None) -> str:
    root = (root or panel.workspace_root()).resolve()
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return path.parent.name
    return relative.parts[0] if relative.parts else path.parent.name


def discover_lock_dependencies(root: Path | None = None, relevant_only: bool = True) -> list[dict[str, str]]:
    root = root or panel.workspace_root()
    if not root.exists():
        return []
    ignored = {
        ".claude",
        ".git",
        ".next",
        ".tmp",
        ".turbo",
        ".worktrees",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "graphify-out",
        "node_modules",
        "venv",
        ".venv",
    }
    dependencies: list[dict[str, str]] = []
    lock_paths: list[Path] = []
    lock_names = {
        "package-lock.json",
        "pnpm-lock.yaml",
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "poetry.lock",
        "uv.lock",
    }
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in ignored]
        for filename in filenames:
            if filename in lock_names:
                lock_paths.append(Path(dirpath) / filename)
    for path in lock_paths:
        if any(part in ignored for part in path.parts):
            continue
        if path.name == "package-lock.json":
            found = package_lock_dependencies(path)
        elif path.name == "pnpm-lock.yaml":
            found = pnpm_lock_dependencies(path)
        elif path.name == "uv.lock":
            found = uv_lock_dependencies(path)
        elif path.name == "poetry.lock":
            found = poetry_lock_dependencies(path)
        elif path.name == "pyproject.toml" and not ((path.parent / "uv.lock").exists() or (path.parent / "poetry.lock").exists()):
            found = pyproject_dependencies(path)
        else:
            found = requirements_dependencies(path)
        for item in found:
            name = normalize_package_name(item["name"])
            if relevant_only and name not in DOCS_RELEVANT_PACKAGES:
                continue
            item["name"] = name
            item["project"] = project_name_for(path, root)
            item["track"] = semver_track(item["version"])
            item["id"] = f"{item['ecosystem']}/{name}@{item['track']}"
            dependencies.append(item)
    dependencies.sort(key=lambda item: (item["project"], item["ecosystem"], item["name"], semver_key(item["version"])))
    return dependencies[:DOCS_CONTEXT_PACKAGE_LIMIT]


def parse_context_packages(output: str) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for line in output.splitlines():
        match = re.search(r"^\s*([A-Za-z0-9_.@/+:-]+)@(\d+(?:\.\d+){0,3}(?:[-+][0-9A-Za-z.-]+)?|latest)\b", line)
        if not match:
            continue
        packages.append({"name": normalize_package_name(match.group(1)), "version": clean_version(match.group(2))})
    return packages


def context_package_inventory(packages_dir: Path | None = None, include_cli: bool = True) -> dict[str, Any]:
    context_bin = shutil.which("context")
    cli_packages: list[dict[str, Any]] = []
    cli_error = ""
    cli_available = False
    if include_cli and context_bin:
        result = panel.run([context_bin, "list"], timeout=10)
        cli_available = result.returncode == 0
        cli_packages = parse_context_packages(result.stdout) if cli_available else []
        cli_error = "" if cli_available else (result.stderr or result.stdout).strip()[:500]
    elif include_cli:
        cli_error = "context command not found"
    file_packages = context_package_file_inventory(packages_dir)
    packages = merge_context_packages(cli_packages, file_packages)
    return {
        "available": cli_available or bool(file_packages),
        "command": context_bin,
        "packages": packages,
        "error": cli_error,
        "file_package_count": len(file_packages),
        "cli_package_count": len(cli_packages),
    }


def aggregate_docs_tracks(dependencies: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    tracks: dict[str, dict[str, Any]] = {}
    for dep in dependencies:
        key = dep["id"]
        track = tracks.setdefault(
            key,
            {
                "id": key,
                "ecosystem": dep["ecosystem"],
                "name": dep["name"],
                "track": dep["track"],
                "versions": [],
                "projects": [],
                "max_used_version": dep["version"],
            },
        )
        if dep["version"] not in track["versions"]:
            track["versions"].append(dep["version"])
        if dep["project"] not in track["projects"]:
            track["projects"].append(dep["project"])
        if semver_key(dep["version"]) > semver_key(track["max_used_version"]):
            track["max_used_version"] = dep["version"]
    for track in tracks.values():
        track["versions"].sort(key=semver_key)
        track["projects"].sort()
    return tracks


def choose_docs_package(dep_name: str, target_version: str, packages: list[dict[str, str]]) -> tuple[str, str, str]:
    candidate_names = set(docs_package_candidates(dep_name))
    matching = [pkg for pkg in packages if pkg["name"] in candidate_names]
    if not matching:
        return ("missing", "", "")
    exact_or_newer = [pkg for pkg in matching if semver_track(pkg["version"]) == semver_track(target_version) and version_at_least(pkg["version"], target_version)]
    if exact_or_newer:
        selected = sorted(exact_or_newer, key=lambda pkg: semver_key(pkg["version"]))[0]
        return ("ok", selected["name"], selected["version"])
    future = [pkg for pkg in matching if same_major(pkg["version"], target_version) and version_at_least(pkg["version"], target_version)]
    if future:
        selected = sorted(future, key=lambda pkg: semver_key(pkg["version"]))[0]
        return ("future", selected["name"], selected["version"])
    same_major_stale = [pkg for pkg in matching if same_major(pkg["version"], target_version)]
    if same_major_stale:
        stale = sorted(same_major_stale, key=lambda pkg: semver_key(pkg["version"]), reverse=True)[0]
        return ("stale", stale["name"], stale["version"])
    latest = [pkg for pkg in matching if pkg["version"] == "latest"]
    if latest:
        selected = sorted(latest, key=lambda pkg: pkg["name"])[0]
        return ("floating", selected["name"], selected["version"])
    return ("missing", "", "")


def safe_docs_commands(row: dict[str, Any]) -> dict[str, str]:
    registry_name = registry_package_ref(row["ecosystem"], row["dependency"])
    version = row["docs_target_version"] or row["used_version"]
    return {
        "install": f"context install {registry_name} {version}",
        "add_template": f"context add <docs-source-url-or-path> --name {row['dependency']} --pkg-version {version}",
        "resolve": f"orch-prompts docs-resolve --package {row['dependency']} --version {version} --topic '<domain API keyword query>'",
    }


def registry_package_ref(ecosystem: str, name: str) -> str:
    package = DOCS_REGISTRY_PACKAGES.get(name, name)
    return f"{ecosystem}/{package}"


def docs_priority(status: str, dependency: str, projects: list[str]) -> str:
    if status == "stale":
        return "high"
    if dependency in DOCS_PRIORITY_PACKAGES:
        return "high"
    if len(projects) >= 3:
        return "high"
    if len(projects) == 2:
        return "medium"
    return "low"


def build_docs_sync_plan(dependencies: list[dict[str, str]], packages: list[dict[str, str]]) -> dict[str, Any]:
    tracks = aggregate_docs_tracks(dependencies)
    entries: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    actionable_counts: dict[str, int] = {}
    for track in sorted(tracks.values(), key=lambda item: (item["name"], item["track"], item["ecosystem"])):
        status, docs_name, docs_version = choose_docs_package(track["name"], track["max_used_version"], packages)
        status_counts[status] = status_counts.get(status, 0) + 1
        registry_ref = registry_package_ref(track["ecosystem"], track["name"])
        target_version = track["max_used_version"]
        install_args = ["context", "install", registry_ref, target_version]
        add_args = [
            "context",
            "add",
            "<docs-source-url-or-path>",
            "--name",
            track["name"],
            "--pkg-version",
            target_version,
        ]
        action = "none"
        can_write = False
        reason = "L1 package covers this track."
        if status in {"missing", "stale", "future", "floating"}:
            action = "install"
            can_write = True
            reason = {
                "missing": "L1 is missing for this track.",
                "stale": "Installed L1 docs are older than the target track.",
                "future": "Installed L1 docs belong to a different major.minor track.",
                "floating": "Installed L1 docs have no verifiable package version.",
            }[status]
            actionable_counts[status] = actionable_counts.get(status, 0) + 1

        entries.append(
            {
                "id": track["id"],
                "ecosystem": track["ecosystem"],
                "dependency": track["name"],
                "track": track["track"],
                "used_versions": track["versions"],
                "docs_target_version": target_version,
                "docs_package": docs_name,
                "docs_version": docs_version,
                "status": status,
                "fallback": status != "ok",
                "priority": docs_priority(status, track["name"], track["projects"]),
                "action": action,
                "can_write": can_write,
                "projects": track["projects"],
                "command": shlex.join(install_args),
                "command_args": install_args,
                "add_template": shlex.join(add_args),
                "reason": reason,
            }
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    status_order = {"stale": 0, "missing": 1, "future": 2, "floating": 3, "ok": 4}
    entries.sort(
        key=lambda item: (
            priority_order.get(item["priority"], 9),
            status_order.get(item["status"], 9),
            item["dependency"],
            item["track"],
        )
    )
    return {
        "summary": {
            "tracks": len(tracks),
            "status_counts": status_counts,
            "actionable_counts": actionable_counts,
            "write_default": "dry-panel.run",
        },
        "entries": entries,
    }


def find_dependency_version(
    dependencies: list[dict[str, str]],
    package_name: str,
    ecosystem: str | None = None,
) -> dict[str, str] | None:
    normalized = normalize_package_name(package_name)
    matches = [
        dep
        for dep in dependencies
        if dep["name"] == normalized and (ecosystem is None or dep["ecosystem"] == ecosystem)
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda dep: semver_key(dep["version"]), reverse=True)[0]


def find_context_package_record(packages: list[dict[str, Any]], name: str, version: str) -> dict[str, Any] | None:
    normalized = normalize_package_name(name)
    for package in packages:
        if normalize_package_name(package.get("name", "")) == normalized and clean_version(package.get("version", "")) == version:
            return package
    return None


def docs_coverage_label(status: str, docs_version: str, target_version: str) -> str:
    if status == "missing":
        return "missing-addable"
    if status == "floating" or docs_version == "latest":
        return "floating"
    if status == "ok" and docs_version == target_version:
        return "exact"
    if status == "ok":
        return "compatible"
    if status == "future":
        return "cross-track"
    return status


def context_command_result(command: list[str], result: subprocess.CompletedProcess[str], strategy: str, selected_version: str = "") -> dict[str, Any]:
    return {
        "ok": result.returncode == 0,
        "command": shlex.join(command),
        "strategy": strategy,
        "selected_version": selected_version,
        "stdout": result.stdout.strip()[:1000],
        "stderr": result.stderr.strip()[:1000],
        "error": "" if result.returncode == 0 else (result.stderr or result.stdout).strip()[:1000],
    }


def parse_context_browse_packages(output: str) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for line in output.splitlines():
        match = re.search(r"^\s*([^\s]+)@([^\s]+)\s+", line)
        if not match:
            continue
        packages.append({"ref": match.group(1), "version": clean_version(match.group(2))})
    return packages


def choose_registry_install_version(target_version: str, packages: list[dict[str, str]]) -> tuple[str | None, str]:
    versions = [pkg["version"] for pkg in packages if pkg.get("version")]
    compatible = [
        version
        for version in versions
        if version != "latest" and semver_track(version) == semver_track(target_version) and version_at_least(version, target_version)
    ]
    if compatible:
        return (sorted(compatible, key=semver_key)[0], "compatible")
    return (None, "unavailable")


def browse_context_registry(context_bin: str, ecosystem: str, package_name: str) -> dict[str, Any]:
    registry_ref = registry_package_ref(ecosystem, package_name)
    command = [context_bin, "browse", registry_ref]
    result = panel.run(command, timeout=30)
    packages = parse_context_browse_packages(result.stdout) if result.returncode == 0 else []
    return {
        "ok": result.returncode == 0,
        "command": shlex.join(command),
        "packages": packages,
        "stdout": result.stdout.strip()[:1000],
        "stderr": result.stderr.strip()[:1000],
        "error": "" if result.returncode == 0 else (result.stderr or result.stdout).strip()[:1000],
    }


def install_context_package(ecosystem: str, package_name: str, version: str) -> dict[str, Any]:
    context_bin = shutil.which("context")
    if not context_bin:
        return {"ok": False, "error": "context command not found", "command": "", "strategy": "missing-binary"}
    registry_ref = registry_package_ref(ecosystem, package_name)
    exact_command = [context_bin, "install", registry_ref, version]
    exact = context_command_result(exact_command, panel.run(exact_command, timeout=240), "exact", version)
    if exact["ok"]:
        return exact

    browse = browse_context_registry(context_bin, ecosystem, package_name)
    selected_version, strategy = choose_registry_install_version(version, browse.get("packages", []))
    if selected_version is None:
        exact["browse"] = browse
        exact["strategy"] = "exact-failed-no-compatible"
        return exact

    fallback_command = [context_bin, "install", registry_ref]
    if selected_version:
        fallback_command.append(selected_version)
    fallback = context_command_result(fallback_command, panel.run(fallback_command, timeout=240), strategy, selected_version or "latest")
    fallback["exact_attempt"] = exact
    fallback["browse"] = browse
    return fallback


# A persisted page is read back as authoritative local docs, so keep one section
# bounded rather than storing whatever a provider returned.
L2_PERSIST_SECTION_LIMIT = 200_000
L2_PERSIST_PROVIDERS = ("context7", "first-party")
# Only a real release number can pin a package. `clean_version` passes through
# anything without digits, so `*`, `next`, `workspace:*` would otherwise create
# exactly the floating L1 entry that keeps a package in permanent fallback.
PINNED_VERSION_RE = re.compile(r"^\d+(\.\d+)*([-+].+)?$")
# `docs-persist` is a manual step, so a forgotten call is invisible: the L2
# answer dies with the context and the next task repeats the network round.
# A hook is out (removed 2026-07-30) and the panel must not reach the network,
# so the remaining honest option is to let the skipped calls accumulate as debt
# an operator can see. Append-only, capped, and never blocking.
DOCS_DEBT_FILENAME = "docs-persist-debt.jsonl"
DOCS_DEBT_MAX_EVENTS = 2000
DOCS_DEBT_ROW_LIMIT = 5


def docs_debt_path() -> Path:
    return panel.STATE_DIR / DOCS_DEBT_FILENAME


def append_docs_debt_event(event: dict[str, Any], journal_path: Path | None = None) -> bool:
    """Append one debt event. Never raises: the journal must not break resolving."""

    path = journal_path or docs_debt_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > DOCS_DEBT_MAX_EVENTS:
            # Keeping the tail drops paired fallback/persist events together, so
            # the surviving balance stays representative.
            path.write_text(
                "\n".join(lines[-DOCS_DEBT_MAX_EVENTS:]) + "\n", encoding="utf-8"
            )
    except OSError:
        return False
    return True


def docs_debt_event(kind: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": kind,
        "package": str(result.get("package", "")),
        "ecosystem": str(result.get("ecosystem", "")),
        "target_version": str(result.get("target_version", "")),
        "topic": str(result.get("topic", "")),
        "lockfile": str(result.get("lockfile_source", "")),
    }


def record_docs_resolution(result: dict[str, Any], journal_path: Path | None = None) -> bool:
    """Record that a resolution had to leave L1.

    Eligibility, not the final status, is the signal: `fallback-needed`,
    `l2-hit`, and `provider-error` all mean L1 could not answer and the version
    is pinned enough to persist. A `blocked` result has no version to store.
    """

    if not result.get("l2", {}).get("eligible"):
        return False
    if not PINNED_VERSION_RE.match(str(result.get("target_version", ""))):
        return False
    return append_docs_debt_event(docs_debt_event("fallback", result), journal_path)


def record_docs_persist(
    outcome: dict[str, Any],
    topic: str = "",
    ecosystem: str = "",
    journal_path: Path | None = None,
) -> bool:
    if not outcome.get("ok"):
        return False
    event = docs_debt_event(
        "persist",
        {
            "package": outcome.get("package", ""),
            "ecosystem": ecosystem,
            "target_version": outcome.get("version", ""),
            "topic": topic,
        },
    )
    return append_docs_debt_event(event, journal_path)


def docs_debt_rows(
    journal_path: Path | None = None,
    packages: list[dict[str, Any]] | None = None,
    limit: int = DOCS_DEBT_ROW_LIMIT,
) -> list[dict[str, Any]]:
    """Packages that went to L2 more often than they were persisted.

    `packages` is the current L1 inventory: a package that L1 now covers is no
    longer debt, whatever the journal remembers.
    """

    path = journal_path or docs_debt_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []

    tally: dict[tuple[str, str, str], dict[str, Any]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        # Keyed on package and version only: `docs-persist` need not be told the
        # ecosystem, and a default that disagreed with the lockfile would leave
        # the debt standing after it was actually paid.
        key = (
            normalize_package_name(str(event.get("package", ""))),
            str(event.get("target_version", "")),
        )
        if not key[0] or not key[1]:
            continue
        row = tally.setdefault(
            key,
            {
                "ecosystem": "",
                "package": key[0],
                "target_version": key[1],
                "fallbacks": 0,
                "persisted": 0,
                "topics": [],
            },
        )
        if not row["ecosystem"]:
            row["ecosystem"] = str(event.get("ecosystem", ""))
        if event.get("event") == "persist":
            row["persisted"] += 1
        elif event.get("event") == "fallback":
            row["fallbacks"] += 1
            topic = str(event.get("topic", "")).strip()
            if topic and topic not in row["topics"]:
                row["topics"].append(topic)

    rows = []
    for row in tally.values():
        debt = row["fallbacks"] - row["persisted"]
        if debt <= 0:
            continue
        if packages is not None:
            status, name, _ = choose_docs_package(
                row["package"], row["target_version"], packages
            )
            if status == "ok" and normalize_package_name(name) == row["package"]:
                continue
        rows.append({**row, "debt": debt})
    rows.sort(key=lambda row: (-row["debt"], row["package"], row["target_version"]))
    return rows[:limit] if limit else rows


def l2_docs_markdown(
    package_name: str,
    version: str,
    provider: str,
    topic: str,
    results: list[dict[str, Any]],
) -> str:
    """Render an L2 answer as a docs page that keeps its provenance inline.

    Provider content is untrusted and becomes locally authoritative once stored,
    so headings and provenance lines must stay attributable: titles are flattened
    to a single line and bodies are fenced so they cannot forge either.
    """

    def one_line(value: str, limit: int = 200) -> str:
        collapsed = re.sub(r"\s+", " ", str(value)).strip()
        return collapsed[:limit] or "section"

    lines = [
        f"# {one_line(package_name)}@{one_line(version)}",
        "",
        "Persisted from an L2 fallback answer; not a registry package.",
        f"Provider: {one_line(provider)}",
        f"Topic: {one_line(topic)}",
        "",
    ]
    for item in results:
        body = str(item["content"]).strip()[:L2_PERSIST_SECTION_LIMIT]
        fence = "`" * max([3] + [len(panel.run) + 1 for panel.run in re.findall(r"`+", body)])
        lines.append(f"## {one_line(item.get('title') or 'section')}")
        lines.append("")
        lines.append(f"Source: {one_line(item['source'])}")
        lines.append("")
        lines.append(fence)
        lines.append(body)
        lines.append(fence)
        lines.append("")
    return "\n".join(lines)


def persist_l2_docs(
    package_name: str,
    version: str,
    provider: str,
    topic: str,
    results: list[Any],
    packages_dir: Path | None = None,
) -> dict[str, Any]:
    """Store an L2 answer in local L1.

    Without this, every task that needs a package L1 cannot cover pays the same
    network round trip and loses the answer when its context ends. Refuses
    anything it cannot pin or attribute, and never overwrites an L1 entry that
    already covers the version.
    """

    normalized = normalize_package_name(package_name)
    target_version = clean_version(version)
    outcome: dict[str, Any] = {
        "ok": False,
        "package": normalized,
        "version": target_version,
        "provider": provider,
        "skipped": "",
        "command": "",
        "sources": [],
    }
    if not normalized:
        outcome["skipped"] = "no package name"
        return outcome
    if not PINNED_VERSION_RE.match(target_version):
        # A floating or non-numeric label is exactly the state that keeps a
        # package in permanent fallback; storing one reproduces the defect.
        outcome["skipped"] = "unpinned version; pass the exact lockfile version"
        return outcome
    if provider.strip() not in L2_PERSIST_PROVIDERS:
        # Provenance is the only reason to keep this page, so an unnamed or
        # guessed provider must not be recorded as fact.
        outcome["skipped"] = (
            f"provider must be one of {', '.join(L2_PERSIST_PROVIDERS)}"
        )
        return outcome

    usable = [
        item
        for item in results
        if isinstance(item, dict)
        and isinstance(item.get("content"), str)
        and item["content"].strip()
        and isinstance(item.get("source"), str)
        and item["source"].strip()
    ]
    if not usable:
        outcome["skipped"] = "no result carried both content and a source URL"
        return outcome
    outcome["sources"] = [item["source"].strip() for item in usable]

    inventory = context_package_inventory(
        packages_dir=packages_dir, include_cli=packages_dir is None
    )
    status, existing_name, existing_version = choose_docs_package(
        normalized, target_version, inventory["packages"]
    )
    # `choose_docs_package` also matches aliases: `@types/node` resolves against
    # `node`. Treating that as coverage would drop the answer for a different
    # package on every attempt, so only an exact name counts as already covered.
    if status == "ok" and normalize_package_name(existing_name) == normalized:
        outcome["skipped"] = f"L1 already covers {existing_name}@{existing_version}"
        return outcome

    context_bin = shutil.which("context")
    if not context_bin:
        outcome["skipped"] = "context command not found"
        return outcome

    with tempfile.TemporaryDirectory(prefix="orch-l2-docs-") as staging:
        page = Path(staging) / f"{normalized.replace('/', '-')}.md"
        page.write_text(
            l2_docs_markdown(normalized, target_version, provider, topic, usable),
            encoding="utf-8",
        )
        command = [
            context_bin,
            "add",
            staging,
            "--name",
            normalized,
            "--pkg-version",
            target_version,
        ]
        result = context_command_result(
            command, panel.run(command, timeout=240), "l2-persist", target_version
        )

    outcome.update(
        {
            "ok": result["ok"],
            "command": result["command"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "error": result["error"],
        }
    )
    if not result["ok"]:
        outcome["skipped"] = "context add failed"
        return outcome

    # A killed or partial `context add` can still leave a package file behind,
    # which would then read back as covered. Confirm the entry exists before
    # reporting success.
    stored = context_package_inventory(
        packages_dir=packages_dir, include_cli=packages_dir is None
    )
    if choose_docs_package(normalized, target_version, stored["packages"])[0] != "ok":
        outcome["ok"] = False
        outcome["skipped"] = (
            "context add reported success but no L1 entry covers the version; "
            "inspect ~/.context/packages"
        )
    return outcome


def resolve_docs(
    cwd: Path,
    package_name: str,
    topic: str,
    ecosystem: str | None = None,
    version: str | None = None,
    packages_dir: Path | None = None,
    allow_download: bool = True,
    l2_lookup: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = cwd.resolve()
    normalized = normalize_package_name(package_name)
    dependencies = discover_lock_dependencies(root=root, relevant_only=False)
    dependency = find_dependency_version(dependencies, normalized, ecosystem)
    explicit_version = clean_version(version or "")
    target_version = explicit_version or clean_version((dependency or {}).get("version", ""))
    version_source = "explicit" if explicit_version else "lockfile"
    resolved_ecosystem = ecosystem or (dependency or {}).get("ecosystem", "npm")
    result: dict[str, Any] = {
        "package": normalized,
        "ecosystem": resolved_ecosystem,
        "topic": topic,
        "cwd": str(root),
        "target_version": target_version,
        "version_source": version_source,
        "lockfile_source": "" if explicit_version else (dependency or {}).get("source", ""),
        "allow_download": allow_download,
        "source": "",
        "status": "",
        "coverage": "",
        "docs_package": "",
        "docs_version": "",
        "results": [],
        "fallback": False,
        "fallback_reason": "",
        "download": None,
        "interface": "harness-wrapper",
        "l1": {
            "provider": "@neuledge/context",
            "attempted": False,
            "status": "not-attempted",
        },
        "l2": {
            "providers": ["context7", "first-party"],
            "eligible": False,
            "status": "not-needed",
            "provider": "",
        },
        "provenance": {},
        "diagnostic": "",
    }
    if not target_version:
        result.update(
            {
                "status": "blocked",
                "coverage": "blocked",
                "fallback": True,
                "fallback_reason": "No package version was found in lockfiles; pass --version or update supported lockfile parsing.",
                "diagnostic": "Lockfile routing failed before L1 lookup; pass --version only when the exact version cannot be resolved from the repository.",
            }
        )
        return result

    result["l1"]["attempted"] = True
    inventory = context_package_inventory(packages_dir=packages_dir, include_cli=packages_dir is None)
    status, docs_name, docs_version = choose_docs_package(normalized, target_version, inventory["packages"])
    result.update(
        {
            "coverage": docs_coverage_label(status, docs_version, target_version),
            "docs_package": docs_name,
            "docs_version": docs_version,
        }
    )

    def try_l1() -> list[dict[str, str]]:
        if not docs_name or not docs_version:
            return []
        package = find_context_package_record(inventory["packages"], docs_name, docs_version)
        return query_context_package(package or {}, topic)

    uncovered_statuses = {"missing", "stale", "future", "floating"}
    if status in uncovered_statuses and allow_download:
        download = panel.install_context_package(resolved_ecosystem, normalized, target_version)
        result["download"] = download
        if download.get("ok"):
            inventory = context_package_inventory(packages_dir=packages_dir, include_cli=packages_dir is None)
            status, docs_name, docs_version = choose_docs_package(normalized, target_version, inventory["packages"])
            result.update(
                {
                    "coverage": docs_coverage_label(status, docs_version, target_version),
                    "docs_package": docs_name,
                    "docs_version": docs_version,
                }
            )
            results = try_l1() if status == "ok" else []
            if status == "ok" and results:
                package = find_context_package_record(inventory["packages"], docs_name, docs_version) or {}
                result.update(
                    {
                        "status": "l1-hit-after-download",
                        "source": "l1-local",
                        "results": results,
                        "provenance": {
                            "provider": "@neuledge/context",
                            "package": docs_name,
                            "package_version": docs_version,
                            "source_url": package.get("sourceUrl", ""),
                            "lockfile": result["lockfile_source"],
                        },
                    }
                )
                result["l1"]["status"] = "hit"
                return result

    if status == "ok":
        results = try_l1()
        if results:
            package = find_context_package_record(inventory["packages"], docs_name, docs_version) or {}
            result.update(
                {
                    "status": "l1-hit",
                    "source": "l1-local",
                    "results": results,
                    "provenance": {
                        "provider": "@neuledge/context",
                        "package": docs_name,
                        "package_version": docs_version,
                        "source_url": package.get("sourceUrl", ""),
                        "lockfile": result["lockfile_source"],
                    },
                }
            )
            result["l1"]["status"] = "hit"
            return result

    l1_status = status if status in uncovered_statuses else "insufficient"
    fallback_reason = {
        "missing": "L1 package is missing for the lockfile version.",
        "stale": "L1 package is older than the lockfile version.",
        "future": "L1 package belongs to a different major.minor track.",
        "floating": "L1 package uses an unversioned latest label.",
    }.get(status, "L1 package exists but did not return relevant sections for the topic.")
    result.update(
        {
            "status": "fallback-needed",
            "source": "context7-or-first-party",
            "fallback": True,
            "fallback_reason": fallback_reason,
        }
    )
    result["l1"]["status"] = l1_status
    result["l2"].update({"eligible": True, "status": "required"})
    if l2_lookup is None:
        return result

    request = {
        "package": normalized,
        "ecosystem": resolved_ecosystem,
        "target_version": target_version,
        "topic": topic,
        "cwd": str(root),
        "lockfile_source": result["lockfile_source"],
        "l1_status": l1_status,
        "l1_reason": fallback_reason,
    }
    try:
        l2_response = l2_lookup(request)
    except Exception as exc:
        l2_response = {"provider": "unknown", "results": [], "error": f"{type(exc).__name__}: {exc}"}
    provider = str(l2_response.get("provider") or "unknown") if isinstance(l2_response, dict) else "unknown"
    raw_results = l2_response.get("results", []) if isinstance(l2_response, dict) else []
    usable_results = [
        item
        for item in raw_results
        if isinstance(item, dict)
        and str(item.get("content", "")).strip()
        and str(item.get("source", "")).strip()
    ] if isinstance(raw_results, list) else []
    if not usable_results:
        provider_error = str(l2_response.get("error", "")).strip() if isinstance(l2_response, dict) else "invalid provider response"
        detail = f" ({provider_error})" if provider_error else ""
        result.update(
            {
                "status": "provider-error",
                "source": provider,
                "diagnostic": (
                    f"L2 provider {provider} returned no usable documentation{detail}. "
                    "Run `orch-prompts docs-diagnose` and inspect session ALL_TOOLS; "
                    "empty MCP resources/templates are not an availability check."
                ),
            }
        )
        result["l2"].update({"status": "error", "provider": provider, "error": provider_error})
        return result

    result.update(
        {
            "status": "l2-hit",
            "source": provider,
            "results": usable_results,
            "provenance": {
                "provider": provider,
                "package": normalized,
                "package_version": target_version,
                "sources": [str(item["source"]) for item in usable_results],
                "lockfile": result["lockfile_source"],
            },
        }
    )
    result["l2"].update({"status": "hit", "provider": provider})
    return result


# Half of the packages that matter exist in the L1 registry only as `latest`,
# so no retrieval can give their exact version. The exact answer is already on
# disk: what is installed *is* the version that runs. This gives signatures, not
# semantics, which is precisely the half of the failure surface retrieval is
# worst at — wrong parameters and invented functions.
SIGNATURE_OUTPUT_LIMIT = 4_000
SIGNATURE_MATCH_LIMIT = 8
SIGNATURE_SCAN_FILE_LIMIT = 4_000
# Declaration forms worth reporting. A bare mention inside a parameter list or a
# comment is not a declaration, so the symbol has to be the thing being named.
TS_DECLARATION_TEMPLATES = (
    r"^\s*(?:export\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var|interface|type|enum|namespace)\s+{symbol}\b",
    r"^\s*(?:readonly\s+)?{symbol}\s*[<(]",
    r"^\s*(?:get|set)\s+{symbol}\s*\(",
)


def project_python_interpreter(root: Path) -> str:
    """The interpreter that actually runs this project, not the panel's own."""

    for relative in (".venv/bin/python", "venv/bin/python", ".venv/Scripts/python.exe"):
        candidate = root / relative
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def npm_package_root(root: Path, package: str) -> Path | None:
    candidate = root / "node_modules" / package
    if (candidate / "package.json").is_file():
        return candidate
    # Monorepos hoist to the workspace root; walk up rather than give up.
    for parent in root.parents:
        candidate = parent / "node_modules" / package
        if (candidate / "package.json").is_file():
            return candidate
    return None


def npm_types_package(package: str) -> str:
    """DefinitelyTyped name for an untyped package.

    `react` ships no `.d.ts` at all — its declarations live in `@types/react`,
    and a scoped name is flattened with a double underscore.
    """

    if package.startswith("@"):
        scope, _, name = package[1:].partition("/")
        return f"@types/{scope}__{name}"
    return f"@types/{package}"


def npm_installed_signature(root: Path, package: str, symbol: str) -> dict[str, Any]:
    outcome: dict[str, Any] = {
        "ecosystem": "npm",
        "package": package,
        "symbol": symbol,
        "version": "",
        "source": "",
        "matches": [],
        "error": "",
    }
    package_root = npm_package_root(root, package)
    if package_root is None:
        outcome["error"] = f"{package} is not installed under node_modules"
        return outcome
    outcome["source"] = str(package_root)
    outcome["version"] = str(panel.load_json(package_root / "package.json", {}).get("version", ""))

    types_root = npm_package_root(root, npm_types_package(package))
    if types_root is not None:
        # Report both: the runtime version is what executes, the @types version
        # is what the declaration came from, and they drift independently.
        outcome["types_package"] = npm_types_package(package)
        outcome["types_version"] = str(
            panel.load_json(types_root / "package.json", {}).get("version", "")
        )

    patterns = [
        re.compile(template.format(symbol=re.escape(symbol)))
        for template in TS_DECLARATION_TEMPLATES
    ]
    search_roots = [(package, package_root)]
    if types_root is not None:
        search_roots.append((outcome["types_package"], types_root))
    declaration_files = [
        (label, base, path)
        for label, base in search_roots
        for path in sorted(base.rglob("*.d.ts"), key=lambda item: len(item.parts))
    ]
    matches: list[dict[str, Any]] = []
    scanned = 0
    for label, base, path in declaration_files:
        if scanned >= SIGNATURE_SCAN_FILE_LIMIT or len(matches) >= SIGNATURE_MATCH_LIMIT:
            break
        scanned += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines):
            if not any(pattern.search(line) for pattern in patterns):
                continue
            # A declaration can wrap; take following lines until it terminates.
            block = [line.rstrip()]
            cursor = index
            while (
                not block[-1].rstrip().endswith((";", "{", "}"))
                and cursor + 1 < len(lines)
                and len(block) < 6
            ):
                cursor += 1
                block.append(lines[cursor].rstrip())
            matches.append(
                {
                    "file": f"{label}/{path.relative_to(base)}",
                    "line": index + 1,
                    "declaration": "\n".join(block).strip(),
                }
            )
            if len(matches) >= SIGNATURE_MATCH_LIMIT:
                break
    outcome["matches"] = matches
    outcome["files_scanned"] = scanned
    if not matches:
        outcome["error"] = f"no declaration of {symbol} found in {package} type definitions"
    return outcome


PYTHON_INTROSPECT = r"""
import importlib, inspect, json, sys
package, symbol = sys.argv[1], sys.argv[2]
out = {"version": "", "source": "", "declaration": "", "doc": "", "error": ""}
try:
    module = importlib.import_module(package)
except Exception as exc:
    out["error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(out)); raise SystemExit(0)
out["version"] = str(getattr(module, "__version__", "") or "")
out["source"] = str(getattr(module, "__file__", "") or "")
target = module
for part in symbol.split(".") if symbol else []:
    target = getattr(target, part, None)
    if target is None:
        out["error"] = f"{package} has no attribute {symbol}"
        print(json.dumps(out)); raise SystemExit(0)
try:
    out["declaration"] = f"{symbol}{inspect.signature(target)}"
except (TypeError, ValueError):
    out["declaration"] = f"{symbol}: {type(target).__name__}"
out["doc"] = inspect.getdoc(target) or ""
print(json.dumps(out))
"""


def python_installed_signature(root: Path, package: str, symbol: str) -> dict[str, Any]:
    """Introspect in the project's own interpreter, never in this process.

    Importing a third-party module executes its top-level code. Doing that
    inside the panel would panel.run arbitrary project code in a long-lived process,
    and would read the wrong environment besides.
    """

    outcome: dict[str, Any] = {
        "ecosystem": "python",
        "package": package,
        "symbol": symbol,
        "version": "",
        "source": "",
        "matches": [],
        "error": "",
    }
    interpreter = project_python_interpreter(root)
    outcome["interpreter"] = interpreter
    try:
        completed = panel.run(
            [interpreter, "-c", PYTHON_INTROSPECT, package, symbol],
            cwd=root,
            timeout=30,
        )
    except Exception as exc:  # pragma: no cover - defensive
        outcome["error"] = f"{type(exc).__name__}: {exc}"
        return outcome
    if completed.returncode != 0:
        outcome["error"] = (completed.stderr or "introspection failed").strip()[:500]
        return outcome
    try:
        data = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        outcome["error"] = "introspection returned no usable result"
        return outcome
    outcome["version"] = str(data.get("version", ""))
    outcome["source"] = str(data.get("source", ""))
    if data.get("error"):
        outcome["error"] = str(data["error"])
        return outcome
    outcome["matches"] = [
        {
            "file": outcome["source"],
            "line": 0,
            "declaration": str(data.get("declaration", "")),
            "doc": str(data.get("doc", ""))[:SIGNATURE_OUTPUT_LIMIT],
        }
    ]
    return outcome


def resolve_installed_signature(
    cwd: Path, package: str, symbol: str, ecosystem: str | None = None
) -> dict[str, Any]:
    root = cwd.resolve()
    resolved = ecosystem
    if not resolved:
        resolved = "npm" if npm_package_root(root, package) is not None else "python"
    if resolved == "npm":
        outcome = npm_installed_signature(root, package, symbol)
    else:
        outcome = python_installed_signature(root, package, symbol)
    outcome["cwd"] = str(root)
    outcome["ok"] = bool(outcome["matches"]) and not outcome["error"]
    return outcome


def signature_text(payload: dict[str, Any]) -> str:
    version = payload.get("version") or "unknown version"
    lines = [
        "Installed signature",
        f"package: {payload.get('ecosystem')}/{payload.get('package')}@{version}",
        f"symbol: {payload.get('symbol')}",
        f"source: {payload.get('source', '')}",
    ]
    if payload.get("types_package"):
        # The runtime version is what executes; the declarations may come from a
        # separately versioned @types package. Saying so is the whole provenance.
        lines.append(
            f"types: {payload['types_package']}@{payload.get('types_version') or 'unknown'}"
        )
    if payload.get("error"):
        lines.append(f"error: {payload['error']}")
        return "\n".join(lines)
    budget = SIGNATURE_OUTPUT_LIMIT
    for match in payload.get("matches", []):
        where = f"{match['file']}:{match['line']}" if match.get("line") else match["file"]
        block = str(match.get("declaration", ""))
        doc = str(match.get("doc", ""))
        chunk = f"\n{where}\n{block}" + (f"\n\n{doc}" if doc else "")
        if len(chunk) > budget:
            lines.append(chunk[:budget] + "\n… truncated")
            break
        budget -= len(chunk)
        lines.append(chunk)
    return "\n".join(lines)


def docs_resolve_text(payload: dict[str, Any]) -> str:
    lines = [
        "Docs Resolver",
        f"package: {payload.get('ecosystem')}/{payload.get('package')}@{payload.get('target_version')}",
        f"status: {payload.get('status')}",
        f"coverage: {payload.get('coverage')}",
        f"source: {payload.get('source')}",
    ]
    if payload.get("version_source"):
        lines.append(f"version_source: {payload.get('version_source')}")
    if payload.get("docs_package"):
        lines.append(f"l1: {payload.get('docs_package')}@{payload.get('docs_version')}")
    if payload.get("lockfile_source"):
        lines.append(f"lockfile: {payload.get('lockfile_source')}")
    download = payload.get("download")
    if isinstance(download, dict):
        lines.append(f"download: {'ok' if download.get('ok') else 'failed'} {download.get('command', '')}".rstrip())
        if download.get("error"):
            lines.append(f"download_error: {download['error']}")
    if payload.get("fallback"):
        lines.append(f"fallback: {payload.get('fallback_reason')}")
        lines.append(
            "persist after L2: orch-prompts docs-persist --package "
            f"{payload.get('package')} --version {payload.get('target_version')} "
            "--provider <context7|first-party> --source <url> --topic "
            f"{shlex.quote(str(payload.get('topic') or ''))} < answer.md"
        )
    l1 = payload.get("l1") or {}
    l2 = payload.get("l2") or {}
    if l1:
        lines.append(f"l1_attempt: {l1.get('status')}")
    if l2:
        lines.append(f"l2: {l2.get('status')} {l2.get('provider', '')}".rstrip())
    if payload.get("diagnostic"):
        lines.append(f"diagnostic: {payload.get('diagnostic')}")
    results = payload.get("results") or []
    if results:
        lines.append("")
        lines.append("results:")
        for item in results:
            lines.append(f"- {item.get('title')} ({item.get('source')})")
            content = re.sub(r"\s+", " ", item.get("content", "")).strip()
            lines.append(f"  {content[:500]}")
    return "\n".join(lines)


def docs_context_text(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    counts = json.dumps(summary.get("status_counts", {}), ensure_ascii=False, sort_keys=True)
    resolve_command = payload.get("commands", {}).get(
        "resolve",
        "orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<API keywords>'",
    )
    lines = [
        "Docs L1/L2 status",
        f"projects: {summary.get('projects', 0)}",
        f"dependencies: {summary.get('dependencies', 0)}",
        f"tracks: {summary.get('tracks', 0)}",
        f"status_counts: {counts}",
        f"stack: {summary.get('stack_path', '')}",
        f"agent entrypoint: {resolve_command}",
    ]
    debt = payload.get("persist_debt") or []
    if debt:
        lines.append("unpersisted L2 answers (panel.run `orch-prompts docs-persist`):")
        for row in debt:
            topic = (row.get("topics") or [""])[0]
            suffix = f" — {topic}" if topic else ""
            lines.append(
                f"  {row.get('package')}@{row.get('target_version')}: "
                f"went to L2 {row.get('fallbacks')}x, persisted "
                f"{row.get('persisted')}x{suffix}"
            )
    lines.append("full state: orch-prompts docs-context --json")
    return "\n".join(lines)

def docs_diagnostic_payload(
    codex_config_path: Path | None = None,
    claude_config_path: Path | None = None,
    packages_dir: Path | None = None,
    include_processes: bool = True,
    codex_host_started_at: float | None = None,
) -> dict[str, Any]:
    codex_config = codex_config_path or (panel.codex_home() / "config.toml")
    claude_config = claude_config_path or panel.claude_mcp_state_path()
    codex_servers = panel.docs_server_names(panel.codex_configured_mcp_servers(codex_config))
    claude_servers = panel.docs_server_names(panel.claude_configured_mcp_servers(claude_config))
    context_bin = shutil.which("context")
    wrapper_bin = shutil.which("orch-prompts")
    inventory = context_package_inventory(packages_dir=packages_dir, include_cli=packages_dir is None)
    process_counts = {"context": 0, "context7": 0}
    if include_processes:
        processes = panel.run(["ps", "-eo", "args"], timeout=5)
        if processes.returncode == 0:
            process_text = processes.stdout.lower()
            process_counts = {
                "context": process_text.count("context serve"),
                "context7": process_text.count("@upstash/context7-mcp"),
            }

    issues: list[str] = []
    if not wrapper_bin:
        issues.append("orch-prompts wrapper is not on PATH")
    if not context_bin:
        issues.append("context CLI is not on PATH")
    # The whole config is routinely rewritten for unrelated settings, so its
    # mtime cannot prove that MCP configuration changed after host startup.
    codex_restart_required = False
    for runtime, servers in (("codex", codex_servers), ("claude", claude_servers)):
        if "context" not in servers:
            issues.append(f"{runtime} does not configure the context MCP server")
        if "context7" not in servers:
            issues.append(f"{runtime} does not configure the optional Context7 L2 server")

    return {
        "status": "ok" if not issues else "warn",
        "interface": {
            "agent_entrypoint": "orch-prompts docs-resolve",
            "native_tool_injection_required": False,
            "l1": "@neuledge/context via the Harness wrapper and local context package store",
            "l2": "Context7 MCP or first-party documentation, only after an explicit resolver fallback state",
            "mcp_capability": "tools",
            "expected_tools": {
                "context": ["get_docs", "search_packages", "download_package"],
                "context7": ["resolve-library-id", "query-docs"],
            },
            "resources_are_authoritative": False,
        },
        "runtimes": {
            "codex": {
                "configured_docs_servers": codex_servers,
                "config_present": codex_config.exists(),
                "injected_tools": "session-scoped; inspect ALL_TOOLS in the active Codex task",
            },
            "claude": {
                "configured_docs_servers": claude_servers,
                "config_present": claude_config.exists(),
                "injected_tools": "session-scoped; inspect the active Claude tool catalog or /mcp",
            },
        },
        "commands": {
            "diagnose": "orch-prompts docs-diagnose --json",
            "resolve": "orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<API keywords>'",
        },
        "local": {
            "wrapper_available": bool(wrapper_bin),
            "context_cli_available": bool(context_bin),
            "l1_package_count": len(inventory.get("packages", [])),
            "started_provider_processes": process_counts,
        },
        "discovery": {
            "session_tool_check": "Codex: filter ALL_TOOLS for context/neuledge/docs; Claude: inspect /mcp and the active tool catalog.",
            "resources_check": "list_mcp_resources/list_mcp_resource_templates may validly be empty because these providers expose tools; do not infer provider availability from them.",
            "provider_failure": "A provider must return usable content plus source provenance or an explicit error; an empty successful discovery result is not accepted.",
            "native_tool_injection": "Direct MCP tools require a successful server launch and session injection but are optional for this workflow; use docs-resolve when the active task does not expose them.",
        },
        "restart": {
            "requirement": "Open a fresh task after Harness skill changes. Restart the relevant host only after an actual MCP server configuration change, not from config.toml mtime alone.",
            "global_restart": "A fresh task that lacks direct MCP tools does not by itself require another restart; verify docs-resolve first, then inspect MCP launcher errors and session injection separately.",
            "codex_required": codex_restart_required,
        },
        "issues": issues,
    }


def docs_diagnostic_text(payload: dict[str, Any]) -> str:
    lines = [
        "Docs L1/L2 Diagnostic",
        f"status: {payload.get('status')}",
        "entrypoint: orch-prompts docs-resolve",
        "interface: MCP tools behind the Harness wrapper; resources/templates are not authoritative",
    ]
    for runtime in ("codex", "claude"):
        servers = payload.get("runtimes", {}).get(runtime, {}).get("configured_docs_servers", [])
        lines.append(f"{runtime}_configured: {', '.join(servers) or 'none'}")
    local = payload.get("local", {})
    lines.extend(
        [
            f"wrapper_available: {local.get('wrapper_available')}",
            f"context_cli_available: {local.get('context_cli_available')}",
            f"l1_packages: {local.get('l1_package_count')}",
            "session_discovery: inspect ALL_TOOLS (Codex) or /mcp (Claude)",
            f"codex_restart_required: {payload.get('restart', {}).get('codex_required')}",
            "restart: only after an actual MCP server config change; direct tool absence alone is not a restart signal",
        ]
    )
    for issue in payload.get("issues", []):
        lines.append(f"warning: {issue}")
    return "\n".join(lines)


def docs_context_payload() -> dict[str, Any]:
    ensure_docs_policy()
    dependencies = discover_lock_dependencies()
    inventory = context_package_inventory()
    tracks = aggregate_docs_tracks(dependencies)
    rows: list[dict[str, Any]] = []
    for dep in dependencies:
        track = tracks[dep["id"]]
        status, docs_name, docs_version = choose_docs_package(dep["name"], track["max_used_version"], inventory["packages"])
        row = {
            "project": dep["project"],
            "ecosystem": dep["ecosystem"],
            "dependency": dep["name"],
            "track": dep["track"],
            "used_version": dep["version"],
            "docs_target_version": track["max_used_version"],
            "docs_package": docs_name,
            "docs_version": docs_version,
            "status": status,
            "fallback": status != "ok",
            "source": dep["source"],
        }
        row["commands"] = safe_docs_commands(row)
        rows.append(row)

    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    sync_plan = build_docs_sync_plan(dependencies, inventory["packages"])
    persist_debt = docs_debt_rows(packages=inventory["packages"])
    payload = {
        "persist_debt": persist_debt,
        "summary": {
            "projects": len({row["project"] for row in rows}),
            "dependencies": len(rows),
            "tracks": len(tracks),
            "status_counts": status_counts,
            "generated_at": int(time.time()),
            "stack_path": str(docs_stack_path()),
            "policy_path": str(docs_policy_path()),
            "persist_debt_path": str(docs_debt_path()),
        },
        "dependencies": rows,
        "packages": inventory,
        "sync_plan": sync_plan,
        "commands": {
            "refresh": "orch-prompts docs-context",
            "resolve": "orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<API keywords>'",
            "plan": "orch-prompts docs-context-plan",
            "sync_dry_run": "orch-prompts docs-context-sync",
            "sync_write": "orch-prompts docs-context-sync --write --limit 20",
            "list": "context list",
            "serve": "context serve",
            "codex_add_l1": "codex mcp add context -- context serve",
            "claude_add_l1": "claude mcp add context -- context serve",
        },
        "context7": panel.context7_status(),
        "mcp": panel.mcp_status(),
    }
    panel.save_json(docs_stack_path(), payload)
    return payload


def filtered_sync_entries(payload: dict[str, Any], statuses: set[str] | None, limit: int | None) -> list[dict[str, Any]]:
    entries = list(payload.get("sync_plan", {}).get("entries") or [])
    if statuses:
        entries = [entry for entry in entries if entry.get("status") in statuses]
    else:
        entries = [entry for entry in entries if entry.get("status") in {"missing", "stale", "future", "floating"}]
    if limit is not None and limit >= 0:
        entries = entries[:limit]
    return entries


def docs_sync_plan_text(payload: dict[str, Any], statuses: set[str] | None = None, limit: int | None = None) -> str:
    plan = payload.get("sync_plan", {})
    summary = plan.get("summary", {})
    entries = filtered_sync_entries(payload, statuses, limit)
    lines = [
        "Docs L1/L2 sync plan",
        f"tracks: {summary.get('tracks', 0)}",
        f"status_counts: {json.dumps(summary.get('status_counts', {}), ensure_ascii=False, sort_keys=True)}",
        f"actionable_counts: {json.dumps(summary.get('actionable_counts', {}), ensure_ascii=False, sort_keys=True)}",
        f"selected_entries: {len(entries)}",
        "write_default: dry-panel.run",
        "",
    ]
    for entry in entries:
        projects = ",".join(entry.get("projects", []))
        lines.append(
            f"- [{entry['priority']}] {entry['status']} {entry['ecosystem']}/{entry['dependency']}@{entry['track']} "
            f"target={entry['docs_target_version']} projects={projects}"
        )
        lines.append(f"  command: {entry['command']}")
        lines.append(f"  add-template: {entry['add_template']}")
        lines.append(f"  reason: {entry['reason']}")
    return "\n".join(lines)

def run_docs_sync(write: bool, statuses: set[str] | None, limit: int | None) -> int:
    payload = docs_context_payload()
    entries = filtered_sync_entries(payload, statuses, limit)
    print(docs_sync_plan_text(payload, statuses, limit))
    if not write:
        print("\nDry-panel.run only. Re-panel.run with --write to execute install commands.")
        return 0
    failures = 0
    for entry in entries:
        if not entry.get("can_write"):
            print(f"SKIP {entry['id']}: action={entry.get('action')}")
            continue
        args = entry.get("command_args") or []
        print(f"\nRUN {shlex.join(args)}")
        result = panel.install_context_package(entry["ecosystem"], entry["dependency"], entry["docs_target_version"])
        if result.get("exact_attempt"):
            print(f"EXACT_FAILED {result['exact_attempt'].get('command')}: {result['exact_attempt'].get('error')}")
        if result.get("command") and result.get("command") != shlex.join(args):
            print(f"RETRY {result['command']} strategy={result.get('strategy')}")
        if result.get("stdout"):
            print(result["stdout"].rstrip())
        if result.get("stderr"):
            print(result["stderr"].rstrip(), file=sys.stderr)
        if not result.get("ok"):
            failures += 1
            print(f"FAIL {entry['id']}: {result.get('error')}", file=sys.stderr)
        else:
            print(f"OK {entry['id']} strategy={result.get('strategy')}")
    docs_context_payload()
    return 1 if failures else 0
