#!/usr/bin/env python3
"""Collect a local Codex stability report without mutating the system."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any


DEFAULT_USER_HOME = Path.home()


def resolve_codex_home() -> Path:
    """Prefer CODEX_HOME, then the newest Windows-side profile on WSL, then ~/.codex."""
    explicit = os.environ.get("CODEX_HOME")
    if explicit:
        return Path(explicit)
    candidates: list[Path] = []
    users_root = Path("/mnt/c/Users")
    if users_root.is_dir():
        try:
            for profile in users_root.iterdir():
                if profile.name.lower() in {"public", "default", "default user", "all users"}:
                    continue
                config = profile / ".codex/config.toml"
                if config.is_file():
                    candidates.append(config)
        except OSError:
            pass
    local = DEFAULT_USER_HOME / ".codex/config.toml"
    if local.is_file():
        candidates.append(local)
    if not candidates:
        return DEFAULT_USER_HOME / ".codex"

    def mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    return max(candidates, key=mtime).parent


DEFAULT_CODEX_HOME = resolve_codex_home()
DEFAULT_WORKSPACE = Path(
    os.environ.get("CODEX_WORKSPACE", str(DEFAULT_USER_HOME / "code"))
)
COLLECTION_BUDGET_SECONDS = 60.0
OPTIONAL_CACHE_TIMEOUT_SECONDS = 1.5
HARNESS_BENCHMARK_SCHEMA = "orchestration-latency/v1"
HARNESS_BENCHMARK_TIMEOUT_SECONDS = 20.0
CODE_MODE_BATCHING_GUIDANCE = (
    "In Code Mode, batch independent functions.exec calls per bounded stage in "
    "one call; keep dependent or conflicting work sequential."
)
DEFAULT_BOUNDED_RUNNER = (
    Path(__file__).resolve().parents[2]
    / "orchestration-setup/templates/scripts/run_bounded_node_tests.py"
)
HARNESS_BENCHMARK_CHECKS = frozenset(
    {
        "prompt_compose",
        "overview",
        "repo_discovery",
        "tails",
        "throughput",
        "beads",
        "panel_server",
    }
)


def run(cmd: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str] | SimpleNamespace:
    try:
        return subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return SimpleNamespace(returncode=127, stdout="", stderr=str(exc))
    except PermissionError as exc:
        return SimpleNamespace(returncode=126, stdout="", stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        return SimpleNamespace(returncode=124, stdout=stdout, stderr=str(exc))


def bytes_to_gib(value: int) -> float:
    return value / (1024**3)


def kib_to_mib(value: int) -> float:
    return value / 1024


def bounded_run(
    cmd: list[str], *, timeout: float, deadline: float | None = None
) -> subprocess.CompletedProcess[str] | SimpleNamespace:
    if deadline is None:
        return run(cmd, timeout=timeout)
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        return SimpleNamespace(
            returncode=124,
            stdout="",
            stderr="global collection budget exhausted",
        )
    return run(cmd, timeout=max(0.05, min(timeout, remaining)))


def classify_process(args: str) -> str | None:
    lower = args.lower()
    if re.search(r"\bcodex\b.*\bapp-server\b", lower):
        return "codex-app-server"
    if "claude --permission-mode" in lower or "claude --dangerously-skip-permissions" in lower:
        return "claude"
    if re.search(r"\bnode\b.*\s--test(?:\s|$)", lower):
        return "node-test"
    if re.search(r"(?:^|[/\s])vitest(?:[./\s]|$)", lower):
        return "vitest"
    if re.search(r"(?:^|[/\s])jest(?:[./\s]|$)", lower):
        return "jest"
    if "context7-mcp" in lower or "@upstash/context7-mcp" in lower:
        return "context7"
    if "mcp-shadcn" in lower or "shadcn mcp" in lower:
        return "shadcn"
    if "@21st-dev/magic" in lower or "21st-magic" in lower:
        return "21st-magic"
    if "playwright-mcp" in lower or "@playwright/mcp" in lower:
        return "playwright-mcp"
    if "sequential-thinking" in lower or "mcp-server-sequential" in lower:
        return "sequential-thinking"
    if "mcp-server-supabase" in lower or "@supabase/mcp" in lower:
        return "supabase"
    if "exa-mcp-server" in lower:
        return "exa"
    if "stitch" in lower and "mcp" in lower:
        return "stitch"
    if "lazyweb" in lower and "mcp" in lower:
        return "lazyweb"
    if re.search(
        r"(?:\bmcp-server(?:[-_/]|\b)|\bmcp_server(?:[-_/]|\b)|"
        r"[/@-]mcp(?:[-_/]|\b)|\bmcp\b)",
        lower,
    ):
        return "other-mcp"
    if "dolt sql-server" in lower:
        return "dolt-sql-server"
    if "next-server" in lower:
        return "next-server"
    if "chrome" in lower and ("playwright" in lower or "--headless" in lower):
        return "playwright-browser"
    return None


def redact(value: str) -> str:
    value = re.sub(
        r"((?:--)?(?:api[-_]?key|token)\s*(?:=|\s)\s*)[^\s,'\"}]+",
        r"\1***",
        value,
        flags=re.I,
    )
    value = re.sub(r"(ctx7sk-)[^\s]+", r"\1***", value)
    value = re.sub(
        r"((?:[\"']?[A-Z][A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|TOKEN|SECRET|PASSWORD)[\"']?)"
        r"\s*[:=]\s*[\"']?)[^\s,}\"']+",
        r"\1***",
        value,
    )
    value = re.sub(
        r"(\b(?:api[_-]?key|token|access[_-]?token|auth[_-]?token|password|secret)\s*=\s*)[^&\s,}\"']+",
        r"\1***",
        value,
        flags=re.I,
    )
    value = re.sub(r"(Authorization:\s*Bearer\s+)[^\s]+", r"\1***", value, flags=re.I)
    value = re.sub(r"(\bBearer\s+)[^\s]+", r"\1***", value, flags=re.I)
    return value


def process_report(
    errors: list[str] | None = None, *, deadline: float | None = None
) -> dict[str, Any]:
    proc = bounded_run(
        ["ps", "-eo", "pid=,ppid=,pgid=,sid=,rss=,etimes=,pcpu=,args="],
        timeout=5.0,
        deadline=deadline,
    )
    if proc.returncode != 0:
        if errors is not None:
            errors.append(f"process scan failed (rc={proc.returncode}): {redact(str(proc.stderr))}")
        return {}
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "rss_kib": 0,
            "max_etime_seconds": 0,
            "max_cpu_pct": 0.0,
            "parents": defaultdict(int),
            "process_groups": set(),
            "sessions": set(),
            "recent_process_groups": set(),
            "examples": [],
        }
    )
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 7)
        if len(parts) < 8:
            continue
        pid, ppid, pgid, sid, rss, etime_seconds, cpu_pct, args = parts
        if (
            "check_system_stability.py" in args
            or "ps -eo" in args
            or "rg -n" in args
            or "grep" in args
        ):
            continue
        name = classify_process(args)
        if not name:
            continue
        group = groups[name]
        group["count"] += 1
        group["rss_kib"] += int(rss)
        group["max_etime_seconds"] = max(group["max_etime_seconds"], int(etime_seconds))
        group["max_cpu_pct"] = max(group["max_cpu_pct"], float(cpu_pct))
        group["parents"][ppid] += 1
        group["process_groups"].add(pgid)
        group["sessions"].add(sid)
        if int(etime_seconds) <= 30 * 60:
            group["recent_process_groups"].add(pgid)
        if len(group["examples"]) < 3:
            group["examples"].append(
                {
                    "pid": int(pid),
                    "ppid": int(ppid),
                    "rss_mib": round(kib_to_mib(int(rss)), 1),
                    "etime_seconds": int(etime_seconds),
                    "cpu_pct": float(cpu_pct),
                    "args": redact(args[:220]),
                }
            )

    normalized = {}
    for name, group in groups.items():
        normalized[name] = {
            "count": group["count"],
            "rss_mib": round(kib_to_mib(group["rss_kib"]), 1),
            "max_etime_seconds": group["max_etime_seconds"],
            "max_cpu_pct": group["max_cpu_pct"],
            "parents": dict(sorted(group["parents"].items(), key=lambda item: -item[1])[:8]),
            "process_group_count": len(group["process_groups"]),
            "session_count": len(group["sessions"]),
            "recent_process_group_count": len(group["recent_process_groups"]),
            "examples": group["examples"],
        }
    return dict(sorted(normalized.items(), key=lambda item: item[1]["rss_mib"], reverse=True))


WSL_ACCEPT_TIMEOUT_MARKER = "UtilAcceptVsock"
WSL_ACCEPT_TIMEOUT_RECENT_SECONDS = 900.0
WSL_RELAY_LINE = re.compile(
    r"^\[\s*(?P<ts>\d+(?:\.\d+)?)\]\s+WSL \((?P<pid>\d+) - Relay\).*"
    + WSL_ACCEPT_TIMEOUT_MARKER
)


def parse_relay_accept_timeouts(text: str) -> dict[str, dict[str, Any]]:
    """Group `UtilAcceptVsock ... abnormally long accept` kernel lines by relay pid."""
    result: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        match = WSL_RELAY_LINE.match(line.strip())
        if not match:
            continue
        pid = match.group("pid")
        entry = result.setdefault(pid, {"count": 0, "last_uptime_seconds": 0.0})
        entry["count"] += 1
        entry["last_uptime_seconds"] = max(entry["last_uptime_seconds"], float(match.group("ts")))
    return result


def read_uptime_seconds() -> float | None:
    try:
        return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return None


def wsl_interop_report(
    notes: list[str] | None = None, *, deadline: float | None = None
) -> dict[str, Any]:
    """Detect WSL interop relays whose Windows peer never connects.

    Each stuck relay blocks the hvsocket accept path for 10 s per retry, and
    every Windows .exe launched from WSL then stalls for exactly 10 s. The
    relays run as root under /init with PPID 1 and survive SIGTERM; the fix is
    `kill -9` as root or `wsl --shutdown`.
    """
    if not Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists():
        return {"available": False, "reason": "not running under WSL"}
    relays: list[dict[str, Any]] = []
    proc = bounded_run(
        ["ps", "-eo", "pid=,ppid=,etimes=,comm="], timeout=5.0, deadline=deadline
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) == 4 and parts[3].strip() == "Relay":
                relays.append(
                    {
                        "pid": parts[0],
                        "ppid": parts[1],
                        "etime_seconds": int(parts[2]),
                        "orphan": parts[1] == "1",
                    }
                )
    dmesg = bounded_run(["dmesg"], timeout=5.0, deadline=deadline)
    if dmesg.returncode != 0:
        if notes is not None:
            notes.append("dmesg is not readable; WSL relay accept timeouts were not checked")
        timeouts: dict[str, dict[str, Any]] = {}
        dmesg_available = False
    else:
        timeouts = parse_relay_accept_timeouts(dmesg.stdout)
        dmesg_available = True
    uptime = read_uptime_seconds()
    alive = {relay["pid"] for relay in relays}
    recent_pids: list[str] = []
    last_seen_seconds_ago: float | None = None
    for pid, entry in timeouts.items():
        if uptime is None:
            continue
        age = uptime - entry["last_uptime_seconds"]
        entry["last_seen_seconds_ago"] = round(age, 1)
        entry["alive"] = pid in alive
        if last_seen_seconds_ago is None or age < last_seen_seconds_ago:
            last_seen_seconds_ago = round(age, 1)
        if age <= WSL_ACCEPT_TIMEOUT_RECENT_SECONDS:
            recent_pids.append(pid)
    return {
        "available": True,
        "dmesg_available": dmesg_available,
        "relays": relays,
        "orphan_relay_pids": [relay["pid"] for relay in relays if relay["orphan"]],
        "accept_timeouts": timeouts,
        "accept_timeout_total": sum(entry["count"] for entry in timeouts.values()),
        "recent_accept_timeout_pids": sorted(recent_pids, key=int),
        "last_accept_timeout_seconds_ago": last_seen_seconds_ago,
    }


def wsl_interop_warnings(report: dict[str, Any]) -> list[str]:
    interop = report.get("wsl_interop", {})
    if not interop.get("available"):
        return []
    warnings: list[str] = []
    recent = interop.get("recent_accept_timeout_pids", [])
    if recent:
        alive = [pid for pid in recent if interop["accept_timeouts"][pid].get("alive")]
        fix = (
            f"run as root: kill -9 {' '.join(alive)}; otherwise wsl --shutdown"
            if alive
            else "relays already gone; if launches still stall, wsl --shutdown"
        )
        warnings.append(
            "WSL interop relay accept timeouts in the last "
            f"{int(WSL_ACCEPT_TIMEOUT_RECENT_SECONDS // 60)} min from relay pids "
            f"{', '.join(recent)} (total {interop.get('accept_timeout_total', 0)}); "
            f"Windows .exe launches from WSL stall 10 s each; {fix}"
        )
    elif interop.get("orphan_relay_pids"):
        warnings.append(
            "orphan WSL interop relays (PPID 1) present: "
            f"{', '.join(interop['orphan_relay_pids'])}; no recent accept timeouts, "
            "watch dmesg for UtilAcceptVsock"
        )
    return warnings


def memory_report() -> dict[str, Any]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0])
    except (OSError, ValueError, IndexError):
        return {}
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    swap_used = max(0, swap_total - swap_free)
    return {
        "total_gib": round(total / 1024**2, 1),
        "available_gib": round(available / 1024**2, 1),
        "swap_total_gib": round(swap_total / 1024**2, 1),
        "swap_used_gib": round(swap_used / 1024**2, 1),
        "swap_used_pct": round((swap_used / swap_total) * 100, 1) if swap_total else 0.0,
    }


def disk_report(paths: list[Path]) -> dict[str, Any]:
    report = {}
    for path in paths:
        if not path.exists():
            continue
        usage = shutil.disk_usage(path)
        report[str(path)] = {
            "total_gib": round(bytes_to_gib(usage.total), 1),
            "used_gib": round(bytes_to_gib(usage.used), 1),
            "free_gib": round(bytes_to_gib(usage.free), 1),
            "used_pct": round((usage.used / usage.total) * 100, 1),
        }
    return report


def du_path(
    path: Path,
    timeout: float = OPTIONAL_CACHE_TIMEOUT_SECONDS,
    *,
    errors: list[str] | None = None,
    notes: list[str] | None = None,
    required: bool = False,
    deadline: float | None = None,
) -> str | None:
    if not path.exists():
        return None
    proc = bounded_run(["du", "-sh", str(path)], timeout=timeout, deadline=deadline)
    if proc.returncode != 0:
        if required and errors is not None:
            errors.append(f"cache size scan failed for {path} (rc={proc.returncode})")
        if notes is not None:
            notes.append(f"cache size scan unavailable for {path} (rc={proc.returncode})")
        return "unavailable"
    return proc.stdout.split()[0]


def latency_report(
    workspace: Path,
    errors: list[str] | None = None,
    *,
    deadline: float | None = None,
) -> list[dict[str, Any]]:
    git_workspace = choose_git_workspace(workspace, deadline=deadline)
    checks = [
        ["bash", "-lc", "true"],
        ["node", "-v"],
        ["npm", "--version"],
        ["git", "-C", str(git_workspace), "status", "--short"],
    ]
    results = []
    for cmd in checks:
        samples = []
        returncodes = []
        stderr_messages = []
        for _ in range(2):
            start = time.perf_counter()
            proc = bounded_run(cmd, timeout=3.0, deadline=deadline)
            samples.append((time.perf_counter() - start) * 1000)
            returncodes.append(proc.returncode)
            stderr_messages.append(getattr(proc, "stderr", "").strip())
        results.append(
            {
                "command": " ".join(cmd),
                "avg_ms": round(sum(samples) / len(samples), 1),
                "max_ms": round(max(samples), 1),
                "returncodes": returncodes,
                "error": next((e for e in stderr_messages if e), ""),
            }
        )
        if any(code == 124 for code in returncodes) and errors is not None:
            errors.append(f"latency check timed out: {' '.join(cmd)}")
    return results


def harness_latency_report(
    errors: list[str] | None = None,
    notes: list[str] | None = None,
    *,
    deadline: float | None = None,
) -> dict[str, Any]:
    runner = shutil.which("orch-prompts")
    if not runner:
        if notes is not None:
            notes.append("harness benchmark unavailable: orch-prompts was not found")
        return {
            "available": False,
            "status": "unavailable",
            "reason": "orch-prompts was not found",
        }

    started = time.perf_counter()
    proc = bounded_run(
        [runner, "benchmark", "--json"],
        timeout=HARNESS_BENCHMARK_TIMEOUT_SECONDS,
        deadline=deadline,
    )
    wall_elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    # `orch-prompts benchmark` exits 1 when a check is over budget but still
    # prints a valid report; only rc>1 or an empty payload is a failure.
    if proc.returncode not in (0, 1) or not str(proc.stdout).strip():
        message = f"harness latency benchmark failed (rc={proc.returncode})"
        if proc.returncode == 124:
            message += "; collection budget exhausted before the benchmark finished"
        if errors is not None:
            errors.append(message)
        return {
            "available": True,
            "status": "error",
            "returncode": proc.returncode,
            "wall_elapsed_ms": wall_elapsed_ms,
            "error": message,
        }

    try:
        payload = json.loads(proc.stdout)
    except (TypeError, json.JSONDecodeError):
        payload = None

    payload_checks = payload.get("checks") if isinstance(payload, dict) else None
    check_names = {
        str(item.get("name"))
        for item in payload_checks or []
        if isinstance(item, dict)
    }
    required_shape = (
        isinstance(payload, dict)
        and payload.get("schema_version") == HARNESS_BENCHMARK_SCHEMA
        and payload.get("status") in {"pass", "warn"}
        and payload.get("quick") is False
        and isinstance(payload.get("elapsed_ms"), (int, float))
        and isinstance(payload.get("budget_ms"), (int, float))
        and isinstance(payload_checks, list)
        and HARNESS_BENCHMARK_CHECKS.issubset(check_names)
    )
    if not required_shape:
        message = "harness latency benchmark returned an invalid orchestration-latency/v1 contract"
        if errors is not None:
            errors.append(message)
        return {
            "available": True,
            "status": "error",
            "returncode": proc.returncode,
            "wall_elapsed_ms": wall_elapsed_ms,
            "error": message,
        }

    checks = []
    for item in payload["checks"]:
        if not isinstance(item, dict):
            continue
        checks.append(
            {
                "name": str(item.get("name", "unknown")),
                "status": str(item.get("status", "error")),
                "elapsed_ms": item.get("elapsed_ms"),
                "budget_ms": item.get("budget_ms"),
                "detail": item.get("detail"),
                "error": redact(str(item["error"])) if item.get("error") else None,
            }
        )
    return {
        "available": True,
        "schema_version": HARNESS_BENCHMARK_SCHEMA,
        "build_id": str(payload.get("build_id", "unknown")),
        "status": payload["status"],
        "over_budget": [str(name) for name in payload.get("over_budget", []) or []],
        "quick": False,
        "elapsed_ms": payload["elapsed_ms"],
        "budget_ms": payload["budget_ms"],
        "wall_elapsed_ms": wall_elapsed_ms,
        "checks": checks,
    }


def bounded_test_runner_report(
    errors: list[str] | None = None,
    notes: list[str] | None = None,
    *,
    runner_path: Path = DEFAULT_BOUNDED_RUNNER,
    deadline: float | None = None,
) -> dict[str, Any]:
    if not runner_path.is_file():
        message = f"bounded Node test runner is missing: {runner_path}"
        if errors is not None:
            errors.append(message)
        return {"available": False, "status": "error", "error": message}

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="codex-bounded-runner-health-") as raw:
        fixture = Path(raw) / "health.test.mjs"
        fixture.write_text("// bounded runner health fixture\n", encoding="utf-8")
        proc = bounded_run(
            [
                sys.executable,
                str(runner_path),
                "--node-timeout-ms",
                "1000",
                "--wall-timeout-seconds",
                "3",
                "--",
                str(fixture),
            ],
            timeout=4.0,
            deadline=deadline,
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    if proc.returncode != 0:
        message = f"bounded Node test runner health check failed (rc={proc.returncode})"
        if errors is not None:
            errors.append(message)
        return {
            "available": True,
            "status": "error",
            "returncode": proc.returncode,
            "elapsed_ms": elapsed_ms,
            "error": redact(str(proc.stderr)),
        }
    return {
        "available": True,
        "status": "pass",
        "returncode": 0,
        "elapsed_ms": elapsed_ms,
    }


def is_git_repo(path: Path, *, deadline: float | None = None) -> bool:
    if not path.exists():
        return False
    proc = bounded_run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        timeout=2.0,
        deadline=deadline,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def choose_git_workspace(workspace: Path, *, deadline: float | None = None) -> Path:
    """Use only the workspace selected by the caller."""
    return workspace


def codex_config_report(
    codex_home: Path, errors: list[str] | None = None
) -> dict[str, Any]:
    path = codex_home / "config.toml"
    if not path.exists():
        return {"path": str(path), "exists": False}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        message = redact(str(exc))
        if errors is not None:
            errors.append(f"Codex config parse failed: {message}")
        return {
            "path": str(path),
            "exists": True,
            "parse_error": message,
            "features": {},
            "agents": {},
            "mcp_servers": [],
            "disabled_mcp_servers": [],
            "plugins": {},
            "duplicate_mcp_plugin_sources": [],
        }
    plugins = {}
    for name, cfg in data.get("plugins", {}).items():
        if isinstance(cfg, dict):
            plugins[name] = cfg.get("enabled")
    mcp_config = data.get("mcp_servers", {})
    mcp_servers = sorted(
        name
        for name, cfg in mcp_config.items()
        if not isinstance(cfg, dict) or cfg.get("enabled") is not False
    )
    disabled_mcp_servers = sorted(
        name
        for name, cfg in mcp_config.items()
        if isinstance(cfg, dict) and cfg.get("enabled") is False
    )
    enabled_plugin_roots = {
        name.split("@", 1)[0]
        for name, enabled in plugins.items()
        if enabled is True
    }
    return {
        "path": str(path),
        "exists": True,
        "features": data.get("features", {}),
        "agents": data.get("agents", {}),
        "mcp_servers": mcp_servers,
        "disabled_mcp_servers": disabled_mcp_servers,
        "plugins": plugins,
        "duplicate_mcp_plugin_sources": sorted(set(mcp_servers) & enabled_plugin_roots),
    }


CONFIG_SEARCH_TARGETS = (
    "sequential-thinking",
    "google-calendar",
    "google-drive",
    "@supabase/mcp",
    "mcp-server-supabase",
)
CONFIG_SEARCH_SKIP_DIRS = frozenset({"node_modules", ".git", ".next", ".mypy_cache"})
CONFIG_SEARCH_FILE_PATTERNS = ("config.toml", ".mcp*.json", "mcp.json")


def config_search_files(roots: list[Path], *, deadline: float | None) -> list[Path]:
    """Enumerate candidate config files without ripgrep, bounded by the deadline."""
    import fnmatch

    found: list[Path] = []
    for root in roots:
        if root.is_file():
            found.append(root)
            continue
        for current, dirs, files in os.walk(root):
            if deadline is not None and time.perf_counter() >= deadline:
                return found
            dirs[:] = [name for name in dirs if name not in CONFIG_SEARCH_SKIP_DIRS]
            for name in files:
                if any(fnmatch.fnmatch(name, pattern) for pattern in CONFIG_SEARCH_FILE_PATTERNS):
                    found.append(Path(current) / name)
    return found


def config_search_python(
    roots: list[Path], targets: tuple[str, ...], *, deadline: float | None
) -> str:
    """Return rg-style `path:line:text` matches using only the standard library."""
    lines: list[str] = []
    for path in config_search_files(roots, deadline=deadline):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            lower = line.lower()
            if any(target.lower() in lower for target in targets):
                lines.append(f"{path}:{number}:{line}")
    return "\n".join(lines)


def config_search(
    workspace: Path,
    codex_home: Path,
    errors: list[str] | None = None,
    *,
    deadline: float | None = None,
) -> dict[str, list[str]]:
    targets = list(CONFIG_SEARCH_TARGETS)
    roots = [root for root in (codex_home / "config.toml", workspace) if root.exists()]
    result: dict[str, list[str]] = {target: [] for target in targets}
    rg_binary = shutil.which("rg")
    if rg_binary:
        cmd = [rg_binary, "-n"]
        for target in targets:
            cmd.extend(["-e", target])
        cmd.extend(str(root) for root in roots)
        for pattern in CONFIG_SEARCH_FILE_PATTERNS:
            cmd.extend(["--glob", pattern])
        for name in sorted(CONFIG_SEARCH_SKIP_DIRS):
            cmd.extend(["--glob", f"!**/{name}/**"])
        proc = bounded_run(cmd, timeout=10.0, deadline=deadline)
        if proc.returncode not in (0, 1):
            if errors is not None:
                errors.append(f"config search failed (rc={proc.returncode}): {redact(str(proc.stderr))}")
            return result
        stdout = proc.stdout
    else:
        # Claude Code ships ripgrep only through a shell function; a subprocess
        # cannot exec it, so search with the standard library instead.
        stdout = config_search_python(roots, CONFIG_SEARCH_TARGETS, deadline=deadline)
    for raw_line in stdout.splitlines():
        lower_line = raw_line.lower()
        for target in targets:
            if target.lower() in lower_line and len(result[target]) < 40:
                location_match = re.match(r"^(.*?):(\d+):", raw_line)
                if location_match:
                    location = f"{redact(location_match.group(1))}:{location_match.group(2)}"
                else:
                    location = "<location unavailable>"
                result[target].append(f"{location}: <matched {target}>")
    return result


def code_mode_batching_guidance_count(text: str) -> int:
    normalized = re.sub(r"\s+", " ", text.replace("`", "")).strip()
    managed_patterns = (
        r"\bIn Code Mode, batch independent functions\.exec calls per bounded "
        r"stage in one call\s*[:;]\s*keep dependent or conflicting work "
        r"sequential(?:\.|$)",
        r"\bIn Code Mode, batch independent functions\.exec calls in one bounded "
        r"stage with Promise\.allSettled or Promise\.all\s*;\s*keep dependencies "
        r"sequential(?:\.|$)",
    )
    return sum(
        len(re.findall(pattern, normalized, re.IGNORECASE))
        for pattern in managed_patterns
    )


def code_mode_batching_guidance_report(codex_home: Path) -> dict[str, Any]:
    global_agents = codex_home / "AGENTS.md"
    try:
        global_text = (
            global_agents.read_text(encoding="utf-8")
            if global_agents.is_file()
            else ""
        )
    except OSError as exc:
        return {
            "status": "warn",
            "global_path": str(global_agents),
            "global_occurrences": 0,
            "custom_agent_duplicates": [],
            "error": redact(str(exc)),
        }

    duplicates: list[str] = []
    agents_dir = codex_home / "agents"
    for path in sorted(agents_dir.glob("*.toml")):
        try:
            if code_mode_batching_guidance_count(path.read_text(encoding="utf-8")):
                duplicates.append(path.name)
        except OSError:
            continue

    global_occurrences = code_mode_batching_guidance_count(global_text)
    return {
        "status": (
            "pass"
            if global_occurrences == 1 and not duplicates
            else "warn"
        ),
        "global_path": str(global_agents),
        "global_occurrences": global_occurrences,
        "custom_agent_duplicates": duplicates,
        "error": None,
    }


def build_warnings(report: dict[str, Any]) -> list[str]:
    warnings = []
    processes = report["processes"]
    mcp_names = (
        "context7",
        "21st-magic",
        "shadcn",
        "playwright-mcp",
        "supabase",
        "exa",
        "lazyweb",
        "stitch",
        "other-mcp",
    )
    for name in mcp_names:
        count = processes.get(name, {}).get("count", 0)
        rss = processes.get(name, {}).get("rss_mib", 0)
        if count >= 12 or rss >= 1024:
            warnings.append(f"{name}: high process count ({count}, {rss} MiB RSS)")
        group_count = processes.get(name, {}).get("process_group_count", 0)
        session_count = processes.get(name, {}).get("session_count", 0)
        recent_groups = processes.get(name, {}).get("recent_process_group_count", 0)
        if group_count >= 8 and session_count == 1:
            warnings.append(
                f"{name}: same session owns {group_count} MCP process groups "
                f"({recent_groups} recent); possible lifecycle leak"
            )
    mcp_count = sum(processes.get(name, {}).get("count", 0) for name in mcp_names)
    mcp_rss = sum(processes.get(name, {}).get("rss_mib", 0) for name in mcp_names)
    if mcp_count >= 48 or mcp_rss >= 3072:
        warnings.append(f"MCP process pressure is high ({mcp_count} processes, {round(mcp_rss, 1)} MiB RSS)")
    for test_name in ("node-test", "vitest", "jest"):
        test_process = processes.get(test_name, {})
        if test_process.get("max_etime_seconds", 0) >= 6 * 60 * 60:
            label = "node test" if test_name == "node-test" else test_name
            warnings.append(
                f"stale {label} detected "
                f"(max age {test_process['max_etime_seconds']} seconds, "
                f"max CPU {test_process.get('max_cpu_pct', 0)}%)"
            )
    for name, count_limit, rss_limit in (
        ("next-server", 8, 4096),
        ("playwright-browser", 16, 4096),
    ):
        info = processes.get(name, {})
        if info.get("count", 0) >= count_limit or info.get("rss_mib", 0) >= rss_limit:
            warnings.append(
                f"{name}: high process pressure ({info.get('count', 0)} processes, "
                f"{info.get('rss_mib', 0)} MiB RSS)"
            )
    app_server = processes.get("codex-app-server", {})
    available_gib = report.get("memory", {}).get("available_gib", 99)
    if app_server.get("rss_mib", 0) >= 4096 or (
        app_server.get("rss_mib", 0) >= 2500
        and app_server.get("max_etime_seconds", 0) >= 7 * 24 * 60 * 60
        and available_gib < 8
    ):
        warnings.append(
            "Codex app-server is old or memory-heavy "
            f"({app_server.get('rss_mib', 0)} MiB RSS, "
            f"max age {app_server.get('max_etime_seconds', 0)} seconds); restart after active work"
        )
    for name in report.get("config", {}).get("duplicate_mcp_plugin_sources", []):
        warnings.append(f"{name}: duplicate MCP/plugin source is enabled")
    batching = report.get("code_mode_batching", {})
    if batching.get("status") == "warn":
        warnings.append(
            "Code Mode batching guidance is missing or duplicated "
            f"(global={batching.get('global_occurrences', 0)}, "
            f"custom_agents={len(batching.get('custom_agent_duplicates', []))})"
        )
    if processes.get("sequential-thinking", {}).get("count", 0):
        warnings.append("sequential-thinking is running even though it is expected to be disabled")
    warnings.extend(wsl_interop_warnings(report))
    harness = report.get("harness_latency", {})
    if harness.get("available") and harness.get("status") in {"warn", "error"}:
        slow_checks = [
            str(item.get("name", "unknown"))
            for item in harness.get("checks", [])
            if item.get("status") != "pass"
        ]
        suffix = f"; slow checks: {', '.join(slow_checks)}" if slow_checks else ""
        warnings.append(
            "Harness latency benchmark "
            f"{harness.get('status')} "
            f"({harness.get('elapsed_ms', 'unknown')}/{harness.get('budget_ms', 'unknown')} ms{suffix})"
        )
    for error in report.get("collector_errors", []):
        warnings.append(f"stability evidence is incomplete: {error}")
    for path, info in report["disk"].items():
        if info["used_pct"] >= 95:
            warnings.append(f"{path}: disk is {info['used_pct']}% full")
    memory = report.get("memory", {})
    if memory.get("available_gib", 99) < 2:
        warnings.append(f"available memory is low ({memory['available_gib']} GiB)")
    if memory.get("swap_used_pct", 0) >= 80:
        warnings.append(f"swap use is high ({memory['swap_used_pct']}%)")
    caches = report["caches"]
    if caches.get("playwright") and caches["playwright"].endswith("G"):
        try:
            if float(caches["playwright"][:-1]) >= 5:
                warnings.append(f"Playwright cache is large ({caches['playwright']})")
        except ValueError:
            pass
    if caches.get("npm_npx") and caches["npm_npx"].endswith("G"):
        try:
            if float(caches["npm_npx"][:-1]) >= 3:
                warnings.append(f"npm _npx cache is large ({caches['npm_npx']})")
        except ValueError:
            pass
    for latency in report["latency"]:
        if any(code != 0 for code in latency["returncodes"]):
            warnings.append(f"{latency['command']} returned non-zero codes {latency['returncodes']}")
        if latency["command"].startswith("bash") and latency["avg_ms"] > 100:
            warnings.append(f"shell startup is slow ({latency['avg_ms']} ms)")
        if latency["command"].startswith("npm") and latency["avg_ms"] > 750:
            warnings.append(f"npm startup is slow ({latency['avg_ms']} ms)")
        if latency["command"].startswith("node") and latency["avg_ms"] > 1000:
            warnings.append(f"node startup is slow ({latency['avg_ms']} ms)")
        if latency["command"].startswith("git") and latency["avg_ms"] > 2000:
            warnings.append(f"git status is slow ({latency['avg_ms']} ms)")
    return warnings


def collect(codex_home: Path, workspace: Path) -> dict[str, Any]:
    started = time.perf_counter()
    deadline = started + COLLECTION_BUDGET_SECONDS
    collector_errors: list[str] = []
    collector_notes: list[str] = []
    config = codex_config_report(codex_home, collector_errors)
    if not config.get("exists"):
        collector_errors.append(f"Codex config is missing: {config.get('path')}")
    processes = process_report(collector_errors, deadline=deadline)
    wsl_interop = wsl_interop_report(collector_notes, deadline=deadline)
    harness_latency = harness_latency_report(collector_errors, collector_notes, deadline=deadline)
    report: dict[str, Any] = {
        "host": platform.node(),
        "codex_home": str(codex_home),
        "workspace": str(workspace),
        "processes": processes,
        "wsl_interop": wsl_interop,
        "config": config,
        "memory": memory_report(),
        "disk": disk_report([Path("/"), DEFAULT_USER_HOME, Path("/mnt/c")]),
        "caches": {
            "playwright": du_path(DEFAULT_USER_HOME / ".cache/ms-playwright", notes=collector_notes, deadline=deadline),
            "npm_npx": du_path(DEFAULT_USER_HOME / ".npm/_npx", notes=collector_notes, deadline=deadline),
            "codex_tmp_plugins": du_path(codex_home / ".tmp/plugins", notes=collector_notes, deadline=deadline),
            "codex_plugin_cache": du_path(codex_home / "plugins/cache", notes=collector_notes, deadline=deadline),
        },
        "harness_latency": harness_latency,
        "latency": latency_report(workspace if workspace.exists() else DEFAULT_WORKSPACE, collector_errors, deadline=deadline),
        "bounded_test_runner": bounded_test_runner_report(collector_errors, collector_notes, deadline=deadline),
        "code_mode_batching": code_mode_batching_guidance_report(codex_home),
        "config_search": config_search(workspace, codex_home, collector_errors, deadline=deadline),
        "collector_errors": collector_errors,
        "collector_notes": collector_notes,
        "collection_elapsed_seconds": round(time.perf_counter() - started, 2),
    }
    report["warnings"] = build_warnings(report)
    return report


def print_human(report: dict[str, Any]) -> None:
    status = "stable" if not report["warnings"] else "attention-needed"
    print(f"Summary: {status}; warnings={len(report['warnings'])}")
    if report["warnings"]:
        print("\nWarnings:")
        for item in report["warnings"]:
            print(f"- {item}")
    print("\nProcess groups:")
    for name, info in report["processes"].items():
        print(f"- {name}: count={info['count']} rss={info['rss_mib']} MiB parents={info['parents']}")
    interop = report.get("wsl_interop", {})
    if interop.get("available"):
        print("\nWSL interop:")
        relays = interop.get("relays", [])
        orphan = interop.get("orphan_relay_pids", [])
        print(f"- relay processes: {len(relays)} (orphans: {', '.join(orphan) or 'none'})")
        if not interop.get("dmesg_available"):
            print("- accept timeouts: dmesg not readable")
        else:
            last = interop.get("last_accept_timeout_seconds_ago")
            last_text = f", last {last} s ago" if last is not None else ""
            print(
                f"- accept timeouts (UtilAcceptVsock): {interop.get('accept_timeout_total', 0)}{last_text}"
            )
            for pid, entry in sorted(interop.get("accept_timeouts", {}).items(), key=lambda item: int(item[0])):
                state = "alive" if entry.get("alive") else "gone"
                print(f"  - relay {pid}: {entry['count']} timeouts, {state}")
    print("\nLatency checks:")
    for item in report["latency"]:
        print(f"- {item['command']}: avg={item['avg_ms']} ms max={item['max_ms']} ms rc={item['returncodes']}")
    print("\nHarness latency:")
    harness = report.get("harness_latency", {})
    if not harness.get("available"):
        print(f"- unavailable: {harness.get('reason', 'orch-prompts was not found')}")
    else:
        print(
            f"- total={harness.get('elapsed_ms', 'unknown')} ms / "
            f"{harness.get('budget_ms', 'unknown')} ms "
            f"status={harness.get('status')} build={harness.get('build_id', 'unknown')}"
        )
        for item in harness.get("checks", []):
            suffix = f" error={item['error']}" if item.get("error") else ""
            print(
                f"  - {item.get('name')}: {item.get('elapsed_ms')} ms / "
                f"{item.get('budget_ms')} ms status={item.get('status')}{suffix}"
            )
    batching = report.get("code_mode_batching", {})
    print("\nCode Mode batching guidance:")
    print(
        f"- status={batching.get('status', 'unavailable')} "
        f"global_occurrences={batching.get('global_occurrences', 0)} "
        f"custom_agent_duplicates="
        f"{len(batching.get('custom_agent_duplicates', []))}"
    )
    bounded_runner = report.get("bounded_test_runner", {})
    print("\nBounded Node test runner:")
    print(
        f"- status={bounded_runner.get('status', 'unavailable')} "
        f"elapsed={bounded_runner.get('elapsed_ms', 'unknown')} ms"
    )
    print("\nMemory:")
    memory = report.get("memory", {})
    print(
        f"- available={memory.get('available_gib', 'unknown')} GiB "
        f"swap_used={memory.get('swap_used_gib', 'unknown')} GiB "
        f"({memory.get('swap_used_pct', 'unknown')}%)"
    )
    print("\nDisk:")
    for path, info in report["disk"].items():
        print(f"- {path}: used={info['used_pct']}% free={info['free_gib']} GiB")
    print("\nCaches:")
    for name, value in report["caches"].items():
        print(f"- {name}: {value or 'missing'}")
    for note in report.get("collector_notes", []):
        print(f"- note: {note}")
    print("\nCodex config:")
    config = report["config"]
    print(f"- path: {config.get('path')}")
    print(f"- features: {config.get('features')}")
    print(f"- mcp_servers: {', '.join(config.get('mcp_servers', []))}")
    print(f"- disabled_mcp_servers: {', '.join(config.get('disabled_mcp_servers', [])) or 'none'}")
    print(f"- duplicate_mcp_plugin_sources: {', '.join(config.get('duplicate_mcp_plugin_sources', [])) or 'none'}")
    print("- plugins:")
    for name, enabled in config.get("plugins", {}).items():
        print(f"  - {name}: enabled={enabled}")
    print("\nConfig search highlights:")
    for target, lines in report["config_search"].items():
        print(f"- {target}: {len(lines)} hits shown")
        for line in lines[:5]:
            print(f"  {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local Codex environment stability.")
    parser.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human text.")
    args = parser.parse_args()

    report = collect(args.codex_home, args.workspace)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 2 if report.get("collector_errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
