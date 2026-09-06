"""Repo radar rows for the Tails panel.

Per-repository work-state overview: dirty worktree, last commit age,
tail count, plus read-only cleanup candidates (merged-but-not-deleted
local branches and extra worktrees) with exact copyable commands.
The panel never executes these commands.
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

GIT_TIMEOUT = 8
PROTECTED_BRANCHES = {"main", "master", "dev", "develop"}
MERGED_LIMIT = 10
WORKTREE_LIMIT = 10


def run_git(repo: Path, args: list[str], timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def resolve_base_ref(repo: Path, base: str | None) -> str | None:
    if not base:
        return None
    for ref in (f"origin/{base}", base):
        result = run_git(repo, ["rev-parse", "--verify", "--quiet", ref], timeout=3)
        if result is not None and result.returncode == 0:
            return ref
    return None


def merged_branches(repo: Path, base_ref: str) -> list[str]:
    result = run_git(repo, ["branch", "--merged", base_ref, "--format=%(refname:short)"])
    if result is None or result.returncode != 0:
        return []
    names: list[str] = []
    for line in result.stdout.splitlines():
        name = line.strip()
        if name and name not in PROTECTED_BRANCHES and not name.startswith("("):
            names.append(name)
    return names


def repo_worktrees(repo: Path) -> list[dict[str, str]]:
    result = run_git(repo, ["worktree", "list", "--porcelain"])
    if result is None or result.returncode != 0:
        return []
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines() + [""]:
        line = line.strip()
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            current["branch"] = line.split(" ", 1)[1].removeprefix("refs/heads/")
    main_path = str(repo.resolve())
    return [entry for entry in entries if entry.get("path") and Path(entry["path"]).resolve() != Path(main_path)]


def head_age_days(repo: Path, now: int) -> int | None:
    result = run_git(repo, ["log", "-1", "--format=%ct"], timeout=5)
    if result is None or result.returncode != 0:
        return None
    value = result.stdout.strip()
    if not value.isdigit():
        return None
    return max(0, int((now - int(value)) / 86400))


def is_dirty(repo: Path) -> bool:
    result = run_git(repo, ["status", "--porcelain"])
    return bool(result is not None and result.returncode == 0 and result.stdout.strip())


def radar_row(repo: Path, now: int, tail_count: int, base: str | None) -> dict[str, Any]:
    base_ref = resolve_base_ref(repo, base)
    merged = merged_branches(repo, base_ref)[:MERGED_LIMIT] if base_ref else []
    worktrees = repo_worktrees(repo)[:WORKTREE_LIMIT]
    repo_arg = shlex.quote(str(repo))
    cleanup_commands = [f"git -C {repo_arg} branch -d {shlex.quote(name)}" for name in merged]
    cleanup_commands.extend(
        f"git -C {repo_arg} worktree remove {shlex.quote(entry['path'])}" for entry in worktrees
    )
    return {
        "project": repo.name,
        "repo_path": str(repo),
        "dirty": is_dirty(repo),
        "head_age_days": head_age_days(repo, now),
        "tail_count": tail_count,
        "base": base_ref or base or "",
        "merged_branches": merged,
        "worktrees": worktrees,
        "cleanup_commands": cleanup_commands,
    }
