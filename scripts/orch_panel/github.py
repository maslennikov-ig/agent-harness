"""GitHub PR/CI status for tail branches via the gh CLI.

One `gh pr list` call per repository, mapped by head branch, so the
Tails panel can show whether an old branch has an open PR and how its
checks look before anyone decides to delete or continue it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from github_sync import (
    BEGIN_MARKER,
    END_MARKER,
    STATE_SCHEMA as GITHUB_SYNC_STATE_SCHEMA,
    _hook_command,
    load_policy,
    resolve_hooks_path,
    resolve_repository_status,
    verify_pinned_executables,
)
from orch_panel.beads import github_sync_log_path

GH_TIMEOUT = 20
PR_LIST_LIMIT = 200
ISSUE_LIST_LIMIT = 50
STATE_ORDER = {"OPEN": 0, "MERGED": 1, "CLOSED": 2}
FAILED_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE", "ACTION_REQUIRED"}


def gh_available() -> bool:
    return shutil.which("gh") is not None


def repo_slug(repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    url = result.stdout.strip()
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", url)
    return match.group(1) if match else ""


def checks_summary(rollup: Any) -> str:
    if not isinstance(rollup, list) or not rollup:
        return "none"
    states = set()
    for check in rollup:
        if not isinstance(check, dict):
            continue
        conclusion = str(check.get("conclusion") or "").upper()
        status = str(check.get("status") or check.get("state") or "").upper()
        if conclusion in FAILED_CONCLUSIONS or status == "FAILURE":
            return "failing"
        if not conclusion and status not in {"COMPLETED", "SUCCESS"}:
            states.add("pending")
    return "pending" if "pending" in states else "passing"


def pr_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": item.get("number"),
        "state": str(item.get("state") or "").upper(),
        "is_draft": bool(item.get("isDraft")),
        "url": str(item.get("url") or ""),
        "title": str(item.get("title") or ""),
        "checks": checks_summary(item.get("statusCheckRollup")),
    }


def tails_pr_payload(repo: Path) -> dict[str, Any]:
    generated_at = int(time.time())
    if not gh_available():
        return {"available": False, "error": "gh CLI not found", "generated_at": generated_at}
    slug = repo_slug(repo)
    if not slug:
        return {
            "available": False,
            "error": "origin remote not found",
            "repo_path": str(repo),
            "generated_at": generated_at,
        }
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "all",
                "--limit",
                str(PR_LIST_LIMIT),
                "--json",
                "number,state,isDraft,url,title,headRefName,statusCheckRollup",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "available": False,
            "error": f"gh pr list: {exc.__class__.__name__}",
            "repo_path": str(repo),
            "slug": slug,
            "generated_at": generated_at,
        }
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        return {
            "available": False,
            "error": f"gh pr list: {tail[-1] if tail else f'exit {result.returncode}'}",
            "repo_path": str(repo),
            "slug": slug,
            "generated_at": generated_at,
        }
    try:
        items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        items = []
    prs: dict[str, dict[str, Any]] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        head = str(item.get("headRefName") or "")
        if not head:
            continue
        summary = pr_summary(item)
        current = prs.get(head)
        if current is None or STATE_ORDER.get(summary["state"], 3) < STATE_ORDER.get(current["state"], 3):
            prs[head] = summary
    return {
        "available": True,
        "repo_path": str(repo),
        "slug": slug,
        "prs": prs,
        "generated_at": generated_at,
    }


def issue_summary(item: dict[str, Any]) -> dict[str, Any]:
    labels = item.get("labels")
    return {
        "number": item.get("number"),
        "title": str(item.get("title") or ""),
        "url": str(item.get("url") or ""),
        "state": str(item.get("state") or "").upper(),
        "updated_at": str(item.get("updatedAt") or ""),
        "labels": [
            str(label.get("name") or "")
            for label in (labels if isinstance(labels, list) else [])
            if isinstance(label, dict) and label.get("name")
        ],
    }


def issues_payload(repo: Path, limit: int = ISSUE_LIST_LIMIT) -> dict[str, Any]:
    """Open issues of one repository, read-only.

    Intake starts here, so an unavailable `gh`, a missing remote, or a failed
    call is reported as itself instead of an empty list that reads like a
    repository without work.
    """
    generated_at = int(time.time())
    if not gh_available():
        return {"available": False, "error": "gh CLI not found", "generated_at": generated_at}
    slug = repo_slug(repo)
    if not slug:
        return {
            "available": False,
            "error": "origin remote not found",
            "repo_path": str(repo),
            "generated_at": generated_at,
        }
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "open",
                "--limit",
                str(max(1, min(limit, ISSUE_LIST_LIMIT))),
                "--json",
                "number,title,url,state,updatedAt,labels",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "available": False,
            "error": f"gh issue list: {exc.__class__.__name__}",
            "repo_path": str(repo),
            "slug": slug,
            "generated_at": generated_at,
        }
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        return {
            "available": False,
            "error": f"gh issue list: {tail[-1] if tail else f'exit {result.returncode}'}",
            "repo_path": str(repo),
            "slug": slug,
            "generated_at": generated_at,
        }
    try:
        items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        items = []
    return {
        "available": True,
        "repo_path": str(repo),
        "slug": slug,
        "issues": [
            issue_summary(item)
            for item in (items if isinstance(items, list) else [])
            if isinstance(item, dict)
        ],
        "generated_at": generated_at,
    }


CURRENT_SYNC_LAUNCHER = Path(__file__).resolve().parents[1] / "github_sync.sh"
RETIRED_HOOK_FLAGS = ("--pull-only", "--push-only")
MAX_SYNC_LOG_TAIL_BYTES = 64 * 1024
SYNC_SWEEP_SECONDS = 5 * 60
# Three missed sweep opportunities means a held lease is no longer routine.
INFLIGHT_ATTENTION_SECONDS = 3 * SYNC_SWEEP_SECONDS


def _runtime_status_defaults() -> dict[str, Any]:
    return {
        "state_status": "not_enrolled",
        "state_error": "",
        "enrolled": False,
        "pending_count": 0,
        "oldest_pending_age": None,
        "inflight": False,
        "inflight_started_at": None,
        "inflight_age": None,
        "inflight_stale": False,
        "last_success": None,
        "last_error": "",
        "pin_valid": None,
        "pin_mismatch": "",
    }


def _parse_sync_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _wrapper_runtime_status(
    identity: Any,
    *,
    pin_verifier: Callable[..., Any],
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Read the coordinator's atomic state without creating locks or files."""
    status = _runtime_status_defaults()
    state_file = Path(identity.state_file)
    if not state_file.is_file():
        return status, None
    try:
        raw = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("root value is not an object")
        if raw.get("schema_version") != GITHUB_SYNC_STATE_SCHEMA:
            raise ValueError(f"unsupported schema {raw.get('schema_version')!r}")
        actual_identity = raw.get("identity")
        expected_identity = {
            "slug": identity.slug,
            "database_id": identity.database_id,
        }
        if not isinstance(actual_identity, dict) or any(
            actual_identity.get(key) != value for key, value in expected_identity.items()
        ):
            raise ValueError("state identity does not match repository")
        pending = raw.get("pending", [])
        pending_since = raw.get("pending_since", {})
        inflight = raw.get("inflight")
        if not isinstance(pending, list) or not isinstance(pending_since, dict):
            raise ValueError("pending queue is not a list/map pair")
        if inflight is not None and not isinstance(inflight, dict):
            raise ValueError("inflight value is not an object")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        status.update(
            state_status="error",
            state_error=f"invalid sync state {state_file}: {exc}",
        )
        return status, None

    enrolled = bool(raw.get("enrolled"))
    oldest_pending_age = None
    timestamps = [pending_since.get(str(item)) for item in pending]
    timestamps = [str(item) for item in timestamps if item]
    if timestamps:
        try:
            oldest = min(_parse_sync_time(item) for item in timestamps)
            oldest_pending_age = max(0, int((now - oldest).total_seconds()))
        except (TypeError, ValueError) as exc:
            status.update(
                state_status="error",
                state_error=f"invalid pending timestamp in {state_file}: {exc}",
            )

    inflight_started_at = (
        (str(inflight.get("started_at") or "") or None) if inflight else None
    )
    inflight_age = None
    if inflight:
        try:
            if not inflight_started_at:
                raise ValueError("missing started_at")
            started = _parse_sync_time(inflight_started_at)
            inflight_age = max(0, int((now - started).total_seconds()))
        except (TypeError, ValueError) as exc:
            status.update(
                state_status="error",
                state_error=f"invalid inflight timestamp in {state_file}: {exc}",
            )

    status.update(
        enrolled=enrolled,
        pending_count=len(pending),
        oldest_pending_age=oldest_pending_age,
        inflight=bool(inflight),
        inflight_started_at=inflight_started_at,
        inflight_age=inflight_age,
        inflight_stale=(
            inflight_age is not None and inflight_age >= INFLIGHT_ATTENTION_SECONDS
        ),
        last_success=(str(raw.get("last_success") or "") or None),
        last_error=str(raw.get("last_error") or ""),
    )
    if status["state_status"] != "error":
        status["state_status"] = "ready" if enrolled else "not_enrolled"
    if enrolled:
        try:
            # Status is read-only: verify path, executable mode, and digest, but
            # never start the pinned bd/gh binaries to ask for their versions.
            pin_verifier(raw, run_versions=False)
        except Exception as exc:  # Pin drift is an operator state, not an API failure.
            status.update(
                pin_valid=False,
                pin_mismatch=f"{exc.__class__.__name__}: {exc}",
            )
            if "reenrollment_required" in str(exc):
                status["state_status"] = "reenrollment_required"
        else:
            status["pin_valid"] = True
    return status, raw


def _managed_hooks_status(
    identity: Any,
    state: dict[str, Any] | None,
    *,
    hook_command_builder: Callable[[Path, Path], str],
) -> tuple[bool, str]:
    """Verify current common-dir hooks against their enrollment receipt."""
    if not state or not state.get("enrolled"):
        return False, "not_enrolled"
    receipt = state.get("hook_receipt")
    hook_receipts = receipt.get("hooks") if isinstance(receipt, dict) else None
    if not isinstance(hook_receipts, dict):
        return False, "reenrollment_required"
    try:
        command = hook_command_builder(CURRENT_SYNC_LAUNCHER, Path(identity.repo))
        hook_dir = resolve_hooks_path(Path(identity.repo))
    except Exception:
        return False, "error"
    expected_block = f"{BEGIN_MARKER}\n{command}\n{END_MARKER}\n"
    for name in ("post-merge", "pre-push"):
        path = hook_dir / name
        raw_receipt = hook_receipts.get(str(path))
        # A changed hooksPath must not make a read-only GET inspect an
        # arbitrary location. Only the exact path approved at enrollment may
        # be opened, including an explicit core.hooksPath outside .git.
        if not isinstance(raw_receipt, dict):
            return False, "reenrollment_required"
        try:
            content = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            executable = bool(path.stat().st_mode & 0o111) and os.access(path, os.X_OK)
        except OSError:
            return False, "reenrollment_required"
        if any(flag in content for flag in RETIRED_HOOK_FLAGS):
            return False, "legacy"
        if (
            not executable
            or raw_receipt.get("new_sha256") != digest
            or content.count(BEGIN_MARKER) != 1
            or content.count(END_MARKER) != 1
            or expected_block not in content
        ):
            return False, "reenrollment_required"
    return True, "ready"


def _last_sync_log_line(path: Path) -> str:
    """Read a bounded tail so a large retained log cannot stall status GET."""
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            stream.seek(max(0, size - MAX_SYNC_LOG_TAIL_BYTES))
            tail = stream.read(MAX_SYNC_LOG_TAIL_BYTES)
    except OSError:
        return ""
    lines = [
        line
        for line in tail.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    return lines[-1] if lines else ""


def _sync_log_payload(line: str) -> dict[str, Any] | None:
    """Decode the JSON object a worker line carries, with or without its prefix."""
    start = line.find("{")
    if start < 0:
        return None
    try:
        payload = json.loads(line[start:])
    except (json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _safe_sync_log_result(line: str) -> tuple[int, str]:
    """Return relevance plus non-sensitive compatibility copy for one line."""
    trigger_failure = re.match(
        r"^github sync trigger failed for "
        r"([A-Za-z][A-Za-z0-9_-]*-[A-Za-z0-9]+(?:\.[0-9]+)*):",
        line,
    )
    if trigger_failure:
        return 2, f"github sync trigger failed for {trigger_failure.group(1)}"
    # A run summary reports its counters by name, and `"failed": 0` is what a
    # healthy run looks like. Reading the key as prose made every successful
    # sync report a failure, which is exactly the signal this field exists for.
    payload = _sync_log_payload(line)
    if payload is not None:
        summary = payload.get("summary")
        counters = summary if isinstance(summary, dict) else payload
        if payload.get("error"):
            return 1, "github sync worker failed; check log"
        failed = counters.get("failed")
        if isinstance(failed, (int, float)) and failed:
            return 1, "github sync worker failed; check log"
        if isinstance(summary, dict) or any(
            key in counters for key in ("beads", "github", "planned")
        ):
            return 0, "github sync activity recorded"
    lowered = line.lower()
    if any(marker in lowered for marker in ("error", "failed", "traceback")):
        return 1, "github sync worker failed; check log"
    return 0, "github sync activity recorded"


def _repair_epoch(status: dict[str, Any]) -> int:
    """When the state last recorded a success, as an epoch; 0 when it never did."""
    raw = status.get("last_success")
    if not isinstance(raw, str) or not raw:
        return 0
    try:
        return int(_parse_sync_time(raw).timestamp())
    except ValueError:
        return 0


def _newest_sync_log(paths: list[Path]) -> tuple[int, str]:
    """Merge bounded tails, deduplicating a requested/canonical common dir."""
    candidates: list[tuple[int, int, int, str]] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        line = _last_sync_log_line(resolved)
        if not line:
            continue
        try:
            stat_result = resolved.stat()
        except OSError:
            continue
        relevance, safe_result = _safe_sync_log_result(line)
        candidates.append(
            (stat_result.st_mtime_ns, relevance, int(stat_result.st_mtime), safe_result)
        )
    if not candidates:
        return 0, ""
    _, _, modified, result = max(candidates)
    return modified, result


def _safe_exclusion_reason(reason: str) -> str:
    """Collapse operator text to a non-sensitive reason understood by the UI."""
    normalized = " ".join(reason.lower().replace("_", " ").split())
    if any(
        phrase in normalized
        for phrase in (
            "no github origin",
            "missing github origin",
            "github origin missing",
            "github origin not configured",
            "github origin is not configured",
            "without github origin",
        )
    ):
        return "no_github_origin"
    return "configured"


def sync_status(
    repo: Path,
    *,
    policy_loader: Callable[[], dict[str, Any]] = load_policy,
    status_resolver: Callable[..., Any] = resolve_repository_status,
    pin_verifier: Callable[..., Any] = verify_pinned_executables,
    hook_command_builder: Callable[[Path, Path], str] = _hook_command,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Report whether sync runs on git operations, and how it went last time.

    A hook that fails silently is the failure mode worth surfacing: it never
    blocks git, so nothing else would say that syncing stopped working.
    """
    requested = Path(repo).expanduser().resolve()
    status: dict[str, Any] = {
        "repo_path": str(requested),
        "requested_repo": str(requested),
        "canonical_repo": "",
        "resolution_status": "error",
        "exclusion_reason": "",
        "hooks_installed": False,
        "last_run": 0,
        "last_result": "",
        **_runtime_status_defaults(),
    }
    try:
        policy = policy_loader()
        workspace = (
            Path(str(policy.get("workspace") or requested.parent))
            .expanduser()
            .resolve()
        )
        resolution = status_resolver(requested, policy=policy, workspace=workspace)
    except Exception as exc:
        status.update(
            state_status="error",
            state_error=f"sync identity unavailable: {exc.__class__.__name__}: {exc}",
        )
        return status
    identity = resolution.identity
    status["resolution_status"] = str(resolution.status or "ineligible")
    if identity is None:
        if resolution.status == "excluded":
            status.update(
                state_status="excluded",
                exclusion_reason=_safe_exclusion_reason(str(resolution.reason or "")),
            )
        else:
            status.update(
                state_status="error",
                state_error=resolution.reason or "repository is not eligible for sync",
            )
        return status

    status["canonical_repo"] = str(Path(identity.repo))
    runtime_status, state = _wrapper_runtime_status(
        identity,
        pin_verifier=pin_verifier,
        now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc),
    )
    status.update(runtime_status)
    hooks_installed, hook_state = _managed_hooks_status(
        identity,
        state,
        hook_command_builder=hook_command_builder,
    )
    status["hooks_installed"] = hooks_installed
    if status["state_status"] != "error":
        if resolution.status == "alias-migration-required":
            status["state_status"] = "reenrollment_required"
        elif hook_state in {"legacy", "reenrollment_required", "error"}:
            status["state_status"] = hook_state
            if hook_state == "error":
                status["state_error"] = "current managed hook cannot be resolved"

    last_run, last_result = _newest_sync_log(
        [
            github_sync_log_path(requested),
            Path(identity.git_common_dir) / "github-sync.log",
        ]
    )
    status.update(last_run=last_run, last_result=last_result)
    # Only the hooks redirect into that log. The documented operator repair,
    # `github_sync.sh --reconcile <repo>`, writes to the operator's terminal
    # instead, so a repaired repository went on reporting the failure the
    # repair had already cleared. State is the newer source then, and this
    # function already resolves competing sources by taking the newest.
    repaired = _repair_epoch(status)
    if repaired > last_run and not status["last_error"]:
        status.update(last_run=repaired, last_result="github sync activity recorded")
    return status
