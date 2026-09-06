#!/usr/bin/env python3
"""Emit bounded Beads runtime facts without static workflow policy.

Status: **not wired to any hook.** `hooks/hooks.json` is empty, so nothing
invokes this adapter automatically. It is a library plus manual CLI for a
`SessionStart` hook a user may choose to install; treat its output as
unavailable unless that hook exists.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def dependency_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict) and item.get("id"):
            result.append(str(item["id"]))
    return result[:8]


def build_context(
    context: dict[str, Any],
    tasks: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> dict[str, Any]:
    bounded = []
    for task in tasks[: max(0, limit)]:
        bounded.append(
            {
                "id": str(task.get("id") or ""),
                "status": str(task.get("status") or ""),
                "dependencies": dependency_ids(
                    task.get("dependencies") or task.get("deps")
                ),
            }
        )
    return {
        "schema": "beads-runtime-context/v1",
        "project": {
            "project_id": context.get("project_id"),
            "repo_root": context.get("repo_root") or context.get("cwd_repo_root"),
        },
        "active_tasks": bounded,
    }


def run_json(args: list[str]) -> Any:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=3,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed with {result.returncode}")
    return json.loads(result.stdout)


def main() -> int:
    try:
        context = run_json(["bd", "context", "--json"])
        tasks = run_json(["bd", "list", "--status", "in_progress", "--json"])
        if not isinstance(context, dict) or not isinstance(tasks, list):
            raise RuntimeError("unexpected Beads JSON shape")
        print(json.dumps(build_context(context, tasks), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(
            json.dumps(
                {
                    "schema": "beads-runtime-context/v1",
                    "available": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
