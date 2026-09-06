"""Doctor rows for local orchestration tooling.

Presence and version/status checks for the CLI tools the orchestration
workflow depends on. Read-only: no installs, no mutations.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import shutil
import subprocess
from typing import Any

TOOL_TIMEOUT = 10
TOOL_CHECKS: tuple[tuple[str, str, list[str]], ...] = (
    ("bd", "Beads", ["bd", "--version"]),
    ("gh", "GitHub CLI (auth)", ["gh", "auth", "status"]),
    ("tmux", "tmux", ["tmux", "-V"]),
    ("context", "Docs L1 (context)", ["context", "--version"]),
    ("graphify", "Graphify", ["graphify", "--version"]),
    ("playwright", "Playwright CLI", ["playwright", "--version"]),
)


def check_tool(key: str, label: str, args: list[str]) -> dict[str, Any]:
    row: dict[str, Any] = {"id": key, "label": label, "present": False, "ok": False, "detail": "not found"}
    if shutil.which(args[0]) is None:
        return row
    row["present"] = True
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=TOOL_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        row["detail"] = exc.__class__.__name__
        return row
    output = (result.stdout or result.stderr or "").strip()
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    row["detail"] = (lines[0] if lines else "")[:100]
    row["ok"] = result.returncode == 0
    if not row["ok"] and not row["detail"]:
        row["detail"] = f"exit {result.returncode}"
    return row


def tool_health() -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=len(TOOL_CHECKS)) as executor:
        return list(
            executor.map(
                lambda check: check_tool(*check),
                TOOL_CHECKS,
            )
        )
