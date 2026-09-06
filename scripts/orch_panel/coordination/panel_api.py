"""HTTP glue between the panel routes and the coordination broker.

The panel keeps routing; everything a coordination request needs to build a
payload, resolve a runtime, or refuse a POST lives here. `orchestration_panel`
is imported as a module object, so the two files can reference each other
without an import cycle.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

_BOUND_NAMESPACE: dict[str, Any] | None = None


def bind(namespace: dict[str, Any]) -> None:
    """Name the panel namespace this glue reads and writes through.

    The panel is loaded as a fresh module object in several places — the ASGI
    host injects one into `build_app`, and tests load an isolated copy and patch
    its paths and adapters, repeatedly, under one `sys.modules` name. Binding the
    namespace dict rather than the module keeps a running host pointed at the
    copy that started it.
    """
    global _BOUND_NAMESPACE
    _BOUND_NAMESPACE = namespace


def panel_namespace() -> dict[str, Any]:
    global _BOUND_NAMESPACE
    if _BOUND_NAMESPACE is None:
        import orchestration_panel

        _BOUND_NAMESPACE = vars(orchestration_panel)
    return _BOUND_NAMESPACE


class _PanelProxy:
    """Forward every attribute to the panel namespace currently bound.

    A name the panel still owns, or one a test replaced on it, resolves there;
    anything else is this module's own definition.
    """

    def __getattr__(self, name: str) -> Any:
        namespace = panel_namespace()
        if name in namespace:
            return namespace[name]
        try:
            return globals()[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


panel = _PanelProxy()


COORDINATION_DB_NAME = "coordination.sqlite3"
COORDINATION_JOURNAL_NAME = "sessions.json"
DEFAULT_PROJECT_ID = "orchestration-console"
# The rollout that kept coordination mutations behind this flag is accepted, so
# writes default to on: a read-only workspace cannot register a project or an
# epic, which is the only way into it. `ORCH_COORDINATION=0` restores the
# read-only panel.
COORDINATION_FLAG = "ORCH_COORDINATION"
_COORDINATION_LOCK = threading.Lock()
_COORDINATION: dict[str, Any] = {}


def coordination_enabled() -> bool:
    return os.environ.get(COORDINATION_FLAG, "1").strip().lower() in {"1", "on", "true", "yes"}


def coordination_paths() -> tuple[Path, Path]:
    base = panel.STATE_DIR / "coordination"
    return base / COORDINATION_DB_NAME, base / COORDINATION_JOURNAL_NAME


def coordination_panel_process_active() -> bool:
    """Return True only when the recorded PID owns this panel process."""
    pid_path = panel.STATE_DIR / "server.pid"
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        command = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
    except (OSError, ValueError):
        return False
    expected = str(panel.CONSOLE_DIR / "scripts" / "orchestration_panel.py").encode()
    return expected in command


def coordination_archive_state(*, confirm: str) -> Path:
    """Move local coordination state to a recoverable archive directory."""
    if confirm != "archive-local-coordination":
        raise ValueError(
            "archive requires --confirm archive-local-coordination"
        )
    with _COORDINATION_LOCK:
        if _COORDINATION.get("broker") is not None or _COORDINATION.get("store") is not None:
            raise ValueError("coordination state is open in this process; stop the panel first")
    if coordination_panel_process_active():
        raise ValueError("the panel is running; stop it before archiving coordination state")
    source = panel.STATE_DIR / "coordination"
    if not source.is_dir():
        raise ValueError(f"coordination state does not exist: {source}")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    destination = panel.STATE_DIR / f"coordination-archive-{stamp}-{os.getpid()}"
    if destination.exists():
        raise ValueError(f"archive destination already exists: {destination}")
    source.rename(destination)
    return destination


def coordination_store(create: bool = False) -> Any:
    """Return the shared store, or None when there is nothing to read yet.

    Reads never create the database: a panel that has never been used for
    coordination should report an empty workspace instead of leaving a file
    behind in `state/`.
    """
    database, _ = coordination_paths()
    if not create and not database.exists():
        return None
    with _COORDINATION_LOCK:
        store = _COORDINATION.get("store")
        if store is not None and _COORDINATION.get("database") == database:
            return store
        from orch_panel.coordination.store import CoordinationStore

        store = CoordinationStore(database)
        _COORDINATION["store"] = store
        _COORDINATION["database"] = database
        _COORDINATION.pop("broker", None)
        return store


def codex_binary() -> str | None:
    """Find the Codex executable, including the Windows build WSL can run.

    On this workstation Codex is installed as the desktop application, which
    puts `codex.exe` on the interop PATH and leaves no bare `codex`. Looking up
    one name would report the runtime missing while it is right there — the same
    incomplete-discovery mistake Task 0 already recorded for the Claude CLI.
    """
    for name in ("codex", "codex.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def coordination_runtime_command(provider: str) -> list[str] | None:
    """Resolve the executable for one provider, or None when it is unavailable."""
    if provider == "claude":
        binary = panel.claude_binary()
        return [binary] if binary else None
    if provider == "codex":
        binary = codex_binary()
        return [binary, "app-server", "--stdio"] if binary else None
    return None


def coordination_adapter(provider: str, journal: Any) -> Any:
    command = panel.coordination_runtime_command(provider)
    if command is None:
        raise RuntimeError(f"{provider} runtime is not installed or not discoverable")
    if provider == "claude":
        from orch_panel.coordination.adapters.claude import ClaudeCliAdapter

        return ClaudeCliAdapter(command=command, journal=journal, timeout=180)
    from orch_panel.coordination.adapters.codex import CodexAppServerAdapter

    env = os.environ.copy()
    env["CODEX_HOME"] = str(panel.codex_home())
    # `CODEX_HOME` is the isolated session home; the catalog and its sync runner
    # live in the asset home, which prompts read through `CODEX_ASSET_HOME`.
    env["CODEX_ASSET_HOME"] = str(panel.codex_asset_home())
    return CodexAppServerAdapter(command=command, journal=journal, env=env, timeout=180)


def coordination_codex_preflight(command: list[str], home: Path) -> dict[str, Any]:
    """Complete the app-server handshake without creating a thread or turn."""
    from orch_panel.coordination.adapters.codex import CodexAppServerAdapter
    from orch_panel.coordination.contracts import SessionJournal

    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    env["CODEX_ASSET_HOME"] = str(panel.codex_asset_home())
    _, journal_path = coordination_paths()
    adapter = CodexAppServerAdapter(
        command=command,
        journal=SessionJournal(journal_path),
        env=env,
        timeout=5,
    )
    try:
        initialization = adapter.preflight()
        return {
            "ok": True,
            "error": "",
            "user_agent": str(initialization.get("userAgent") or ""),
            "platform_family": str(initialization.get("platformFamily") or ""),
        }
    except Exception as exc:
        return {"ok": False, "error": panel.mask_secret_text(str(exc))[:500]}
    finally:
        adapter.close()


def coordination_project_cwd(project_id: str) -> Path:
    store = panel.coordination_store(create=True)
    project = store.project(project_id)
    return Path(project.repo_path) if project else panel.CONSOLE_DIR


def coordination_broker() -> Any:
    store = panel.coordination_store(create=True)
    with _COORDINATION_LOCK:
        broker = _COORDINATION.get("broker")
        if broker is None:
            from orch_panel.coordination.broker import Broker

            _, journal = coordination_paths()
            broker = Broker(
                store,
                journal_path=journal,
                # Read through the proxy so a panel copy that replaced one of
                # these seams supplies its own.
                adapter_factory=lambda provider, journal: panel.coordination_adapter(
                    provider, journal
                ),
                cwd_resolver=lambda project_id: panel.coordination_project_cwd(project_id),
                prompt_resolver=lambda card_id, runtime: panel.coordination_root_role(
                    card_id, runtime
                ),
            )
            _COORDINATION["broker"] = broker
        return broker


def coordination_startup() -> list[Any]:
    """Reconcile persisted active dispatches before the ASGI host accepts work."""
    if panel.coordination_store() is None:
        return []
    return panel.coordination_broker().reconcile()


def coordination_root_role(card_id: str, runtime: str) -> dict[str, Any]:
    """Resolve one root-role card through the existing manifest path.

    This is `prompt-get` with an exact id, not a search: the panel never asks a
    runtime to browse the catalogue or pick a card for itself.
    """
    return panel.prompt_get_payload(card_id, runtime, "launcher")


def coordination_shutdown() -> None:
    """Release coordination on a normal panel exit. Safe to call twice.

    Startup reconciliation owns dispatches a crash left `running`; this path
    only releases resources during a normal exit.
    """
    with _COORDINATION_LOCK:
        broker = _COORDINATION.pop("broker", None)
        store = _COORDINATION.pop("store", None)
        _COORDINATION.pop("database", None)
    if broker is not None:
        broker.close()
    if store is not None:
        store.close()


def coordination_artifact_payload(ref: Any) -> dict[str, Any]:
    return {"path": ref.path, "digest": ref.digest, "media_type": ref.media_type}


def coordination_event_payload(event: Any) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "event_id": event.event_id,
        "project_id": event.project_id,
        "epic_id": event.epic_id,
        "beads_issue_id": event.beads_issue_id,
        "dispatch_id": event.dispatch_id,
        "runtime_session_id": event.runtime_session_id,
        "author_kind": event.author_kind,
        "event_kind": event.event_kind,
        "body_text": event.body_text,
        "artifact_refs": [coordination_artifact_payload(ref) for ref in event.artifact_refs],
        "reply_to": event.reply_to,
        "created_at": event.created_at,
    }


def coordination_dispatch_payload(dispatch: Any) -> dict[str, Any]:
    return {
        "dispatch_id": dispatch.dispatch_id,
        "project_id": dispatch.project_id,
        "epic_id": dispatch.epic_id,
        "beads_issue_id": dispatch.beads_issue_id,
        "provider": dispatch.provider,
        "state": str(dispatch.state),
        "runtime_session_id": dispatch.runtime_session_id,
        "write_zone": dispatch.write_zone,
        "prompt_card_id": dispatch.prompt_card_id,
        "prompt_digest": dispatch.prompt_digest,
        "detail": dispatch.detail,
        "created_at": dispatch.created_at,
        "updated_at": dispatch.updated_at,
        # Task 3 fields ride in the record's metadata rather than widening the
        # shared dataclass; the wire shape keeps them flat for the browser.
        "role": dispatch.metadata.get("role", "executor"),
        "review_required": bool(dispatch.metadata.get("review_required")),
        "parent_dispatch_id": dispatch.metadata.get("parent_dispatch_id", ""),
    }


def coordination_review_payload(item: Any) -> dict[str, Any]:
    return {
        "review_id": item.review_id,
        "round": item.round,
        "executor_dispatch_id": item.executor_dispatch_id,
        "executor_provider": item.executor_provider,
        "judge_dispatch_id": item.judge_dispatch_id,
        "judge_provider": item.judge_provider,
        "judge_session_id": item.judge_session_id,
        "outcome": item.outcome,
        "summary": item.summary,
        "findings": [finding.as_dict() for finding in item.findings],
        "revision_returned": item.revision_returned,
        "decided_by": item.decided_by,
        "created_at": item.created_at,
    }


def coordination_reviews_payload(
    epic_id: str, beads_issue_id: str | None = None
) -> dict[str, Any]:
    """Project the review loop: rounds so far, the next legal step, and the gate.

    The browser never derives the bound itself. It renders what the policy
    already decided, so a stale tab cannot offer a third judge call.
    """
    from orch_panel.coordination.review import MAX_JUDGE_ROUNDS, done_gate, next_action

    payload: dict[str, Any] = {
        "epic_id": epic_id,
        "beads_issue_id": beads_issue_id,
        "max_judge_rounds": MAX_JUDGE_ROUNDS,
        "executors": [],
    }
    store = panel.coordination_store()
    if store is None:
        return payload
    rounds = store.review_rounds(epic_id=epic_id, beads_issue_id=beads_issue_id)
    grouped: dict[str, list[Any]] = {}
    for item in rounds:
        grouped.setdefault(item.executor_dispatch_id, []).append(item)
    # Only the current run per issue decides Done, so the projection says which
    # one that is rather than leaving the browser to guess from ordering.
    current_ids = {
        current.dispatch_id
        for current in (
            store.current_executor_for_issue(epic_id, issue)
            for issue in {
                dispatch.beads_issue_id
                for dispatch in store.dispatches(
                    epic_id=epic_id, beads_issue_id=beads_issue_id
                )
                if dispatch.beads_issue_id
            }
        )
        if current is not None
    }
    for dispatch in store.dispatches(epic_id=epic_id, beads_issue_id=beads_issue_id):
        if dispatch.metadata.get("role") != "executor":
            continue
        own = grouped.get(dispatch.dispatch_id, [])
        required = bool(dispatch.metadata.get("review_required"))
        allowed, reason = done_gate(review_required=required, rounds=own)
        payload["executors"].append(
            {
                "dispatch_id": dispatch.dispatch_id,
                "beads_issue_id": dispatch.beads_issue_id,
                "executor_provider": dispatch.provider,
                "state": str(dispatch.state),
                "review_required": required,
                "is_current": dispatch.dispatch_id in current_ids,
                "next_action": next_action(own),
                "done_allowed": allowed,
                "done_blocked_reason": reason,
                "rounds": [coordination_review_payload(item) for item in own],
            }
        )
    return payload


def coordination_repo_file(repo: Path, raw: str, label: str) -> Path:
    """Resolve one repository-relative reference the review request names.

    The path arrives from a browser form, so traversal, absolute paths, and a
    symlink pointing out of the worktree are refused before anything is read.
    """
    from orch_panel.beads import BeadsMutationError

    text = (raw or "").strip()
    relative = PurePosixPath(text)
    if not text or relative.is_absolute() or ".." in relative.parts:
        raise BeadsMutationError(f"{label} must be a repository-relative path")
    root = repo.resolve()
    resolved = (root / Path(text)).resolve()
    if not resolved.is_relative_to(root):
        raise BeadsMutationError(f"{label} resolves outside {root}")
    if not resolved.is_file():
        raise BeadsMutationError(f"{label} does not exist: {text}")
    return resolved


@lru_cache(maxsize=1)
def coordination_evidence_verifier():
    """Load the canonical verifier, never a target repository's executable copy."""
    path = (
        panel.CONSOLE_DIR
        / "harness"
        / "private"
        / "private"
        / "codex"
        / "skills"
        / "orchestration-setup"
        / "templates"
        / "scripts"
        / "verification_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("panel_verification_evidence_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical verification evidence helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def coordination_git_common_file(repo: Path, raw: str, label: str) -> Path:
    """Resolve a receipt-owned report below the repository's Git common dir."""
    from orch_panel.beads import BeadsMutationError

    text = (raw or "").strip()
    relative = PurePosixPath(text)
    if not text or relative.is_absolute() or ".." in relative.parts:
        raise BeadsMutationError(f"{label} must be a Git-common-relative path")
    found = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if found.returncode != 0 or not found.stdout.strip():
        raise BeadsMutationError(f"{label} requires a Git repository")
    common = Path(found.stdout.strip())
    if not common.is_absolute():
        common = repo / common
    root = common.resolve()
    candidate = root
    for component in relative.parts:
        candidate = candidate / component
        if candidate.is_symlink():
            raise BeadsMutationError(f"{label} may not traverse a symlink")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise BeadsMutationError(f"{label} resolves outside {root}")
    if not resolved.is_file():
        raise BeadsMutationError(f"{label} does not exist: {text}")
    return resolved


def coordination_runtime_status() -> list[dict[str, Any]]:
    """Report which runtimes could actually be dispatched, without starting one."""
    from orch_panel.coordination.broker import ROOT_ROLE_CARDS

    providers = []
    for provider in ("codex", "claude"):
        command = panel.coordination_runtime_command(provider)
        status = "ready" if command else "missing"
        error = "" if command else f"{provider} executable was not found"
        detail: dict[str, Any] = {}
        if provider == "codex" and command is not None:
            home = panel.codex_home()
            identity = hashlib.sha256(
                json.dumps([command, str(home)], separators=(",", ":")).encode()
            ).hexdigest()[:16]
            detail = panel.cached_runtime(
                f"coordination-codex-preflight:{identity}",
                15,
                lambda: panel.coordination_codex_preflight(command, home),
            )
            status = "ready" if detail.get("ok") else "unhealthy"
            error = str(detail.get("error") or "")
        providers.append(
            {
                "id": provider,
                "available": bool(command) and status == "ready",
                "status": status,
                "error": panel.mask_secret_text(error),
                "command": panel.mask_secret_text(" ".join(command)) if command else "",
                "home": str(panel.codex_home()) if provider == "codex" else str(panel.claude_home()),
                "root_role": ROOT_ROLE_CARDS[provider],
                **{key: value for key, value in detail.items() if key not in {"ok", "error"}},
            }
        )
    return providers


def coordination_overview_payload() -> dict[str, Any]:
    from orch_panel.coordination.store import SCHEMA_VERSION

    store = panel.coordination_store()
    payload: dict[str, Any] = {
        "enabled": panel.coordination_enabled(),
        "flag": COORDINATION_FLAG,
        "schema_version": SCHEMA_VERSION,
        "providers": coordination_runtime_status(),
        "projects": [],
        "epics": [],
        "latest_seq": 0,
        "console_repo": str(panel.CONSOLE_DIR),
        # Registration is the allowlist for project creation, so the browser
        # gets the same set instead of guessing a path the endpoint rejects.
        "repositories": [
            {"repo_path": str(item), "name": item.name}
            for item in sorted({panel.CONSOLE_DIR.resolve(), *(repo.resolve() for repo in panel.discover_repos())})
        ],
    }
    if store is None:
        return payload
    payload["projects"] = [
        {"project_id": item.project_id, "name": item.name, "repo_path": item.repo_path}
        for item in store.projects()
    ]
    payload["epics"] = [
        {
            "epic_id": item.epic_id,
            "project_id": item.project_id,
            "title": item.title,
            "beads_issue_id": item.beads_issue_id,
            "source_kind": item.source_kind,
            "source_ref": item.source_ref,
            "source_url": item.source_url,
        }
        for item in store.epics()
    ]
    payload["latest_seq"] = store.latest_seq()
    return payload


def coordination_events_payload(
    epic_id: str,
    *,
    beads_issue_id: str | None = None,
    after_seq: int = 0,
    limit: int = 500,
) -> dict[str, Any]:
    store = panel.coordination_store()
    if store is None:
        return {"epic_id": epic_id, "events": [], "latest_seq": 0}
    events = store.events(
        epic_id=epic_id,
        beads_issue_id=beads_issue_id,
        after_seq=after_seq,
        limit=limit,
    )
    return {
        "epic_id": epic_id,
        "beads_issue_id": beads_issue_id,
        "events": [coordination_event_payload(event) for event in events],
        "latest_seq": store.latest_seq(),
    }


def coordination_dispatches_payload(epic_id: str) -> dict[str, Any]:
    store = panel.coordination_store()
    if store is None:
        return {"epic_id": epic_id, "dispatches": []}
    return {
        "epic_id": epic_id,
        "dispatches": [
            coordination_dispatch_payload(item) for item in store.dispatches(epic_id=epic_id)
        ],
    }


def coordination_repo_for_project(project_id: str) -> Path:
    """Resolve and validate the repository one project is registered against."""
    from orch_panel.beads import BeadsMutationError, resolve_beads_repo

    store = panel.coordination_store()
    project = store.project(project_id) if store else None
    if project is None:
        raise BeadsMutationError(f"unknown project: {project_id}")
    allowed = [panel.CONSOLE_DIR, *panel.discover_repos()]
    return resolve_beads_repo(project.repo_path, allowed)


def coordination_board_payload(epic_id: str) -> dict[str, Any]:
    """Project the epic's Beads children onto the four board columns.

    Every field here comes from `bd`. The panel adds only the derived phase,
    which is a badge and never a status.
    """
    from orch_panel.beads import bd_available, blocked_ids, issue_summary, run_bd
    from orch_panel.coordination.workflow import (
        BOARD_COLUMNS,
        allowed_targets,
        blocking_dependencies,
        derive_phase,
        place_issue,
    )

    payload: dict[str, Any] = {
        "epic_id": epic_id,
        "columns": [{"id": column, "issues": []} for column in BOARD_COLUMNS],
        "available": bd_available(),
        "writable": panel.coordination_enabled(),
        "errors": [],
    }
    store = panel.coordination_store()
    epic = store.epic(epic_id) if store else None
    if epic is None:
        payload["errors"].append(f"unknown epic: {epic_id}")
        return payload
    payload["project_id"] = epic.project_id
    payload["beads_issue_id"] = epic.beads_issue_id
    if not payload["available"]:
        payload["errors"].append("bd CLI not found")
        return payload
    if not epic.beads_issue_id:
        payload["errors"].append(
            "this epic has no Beads issue, so it has no board; link one to see tasks"
        )
        return payload
    try:
        repo = panel.coordination_repo_for_project(epic.project_id)
    except Exception as exc:
        payload["errors"].append(str(exc))
        return payload
    payload["repo_path"] = str(repo)

    issues, error = run_bd(
        repo, ["bd", "list", f"--parent={epic.beads_issue_id}", "--all", "--limit=0", "--json"]
    )
    if error:
        payload["errors"].append(error)
        return payload
    try:
        blocked = blocked_ids(repo)
    except Exception as exc:
        payload["errors"].append(str(exc))
        blocked = frozenset()

    dispatches_by_issue: dict[str, list[dict[str, Any]]] = {}
    if store is not None:
        for dispatch in store.dispatches(epic_id=epic_id):
            if dispatch.beads_issue_id:
                dispatches_by_issue.setdefault(dispatch.beads_issue_id, []).append(
                    {"state": str(dispatch.state)}
                )

    columns = {column["id"]: column for column in payload["columns"]}
    off_board: list[dict[str, Any]] = []
    for item in issues:
        placement = place_issue(item, blocked_ids=blocked)
        column = placement.column
        card = issue_summary(item)
        card["column"] = column
        card["phase"] = (
            derive_phase(column, dispatches_by_issue.get(card["id"], [])) if column else ""
        )
        # A dependency-blocked card offers no targets, so the board never draws
        # a control whose only outcome is a refusal.
        card["targets"] = (
            list(allowed_targets(column, dependency_blocked=placement.dependency_blocked))
            if column
            else []
        )
        card["dependency_blocked"] = placement.dependency_blocked
        card["blocked_by"] = [
            str(dependency.get("id") or "")
            for dependency in blocking_dependencies(item)
        ] if placement.dependency_blocked else []
        if column is None:
            off_board.append(card)
            continue
        columns[column]["issues"].append(card)
    for column in payload["columns"]:
        column["issues"].sort(key=lambda card: (card.get("priority") or 9, card["id"]))
    payload["off_board"] = off_board
    return payload


def coordination_planning_payload(epic_id: str) -> dict[str, Any]:
    store = panel.coordination_store()
    if store is None:
        return {"epic_id": epic_id, "artifacts": []}
    return {
        "epic_id": epic_id,
        "artifacts": [
            {
                "kind": item.kind,
                "path": item.path,
                "digest": item.digest,
                "beads_issue_id": item.beads_issue_id,
                "registered_at": item.registered_at,
            }
            for item in store.planning_artifacts(epic_id)
        ],
    }


def coordination_register_planning(payload: dict[str, Any]) -> panel.PanelResponse:
    """Register an accepted spec or plan by path and digest.

    The digest is computed here from the file on disk, never taken from the
    request: a caller-supplied digest would let the record claim a revision the
    worktree does not contain.
    """
    from orch_panel.beads import BeadsMutationError, read_issue
    from orch_panel.coordination.store import StoreError
    from orch_panel.coordination.workflow import (
        PlanningPathError,
        issue_belongs_to_epic,
        resolve_planning_path,
    )

    store = panel.coordination_store(create=True)
    kind = str(payload.get("kind") or "").strip()
    epic_id = str(payload.get("epic_id") or "")
    epic = store.epic(epic_id)
    if epic is None:
        return panel.json_response({"error": f"unknown epic: {epic_id}"}, status=400)
    try:
        repo = panel.coordination_repo_for_project(epic.project_id)
    except Exception as exc:
        return panel.json_response({"error": str(exc)}, status=400)

    try:
        resolved = resolve_planning_path(repo, kind, str(payload.get("path") or ""))
    except PlanningPathError as exc:
        return panel.json_response({"error": str(exc)}, status=400)
    relative = resolved.relative_to(repo.resolve()).as_posix()

    beads_issue_id = str(payload.get("beads_issue_id") or "").strip()
    if beads_issue_id:
        # A named issue is a claim of ownership, so it is checked against the
        # same epic rule the board uses before anything is recorded.
        try:
            linked = read_issue(repo, beads_issue_id)
        except BeadsMutationError as exc:
            return panel.json_response({"error": str(exc)}, status=400)
        if not issue_belongs_to_epic(linked, str(epic.beads_issue_id or "")):
            return panel.json_response(
                {
                    "error": (
                        f"{beads_issue_id} does not belong to epic "
                        f"'{epic.beads_issue_id or 'unset'}'"
                    )
                },
                status=400,
            )

    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    try:
        artifact = store.register_planning_artifact(
            project_id=epic.project_id,
            epic_id=epic_id,
            kind=kind,
            path=relative,
            digest=digest,
            beads_issue_id=beads_issue_id or None,
        )
    except StoreError as exc:
        return panel.json_response({"error": str(exc)}, status=400)
    return panel.json_response(
        {
            "kind": artifact.kind,
            "path": artifact.path,
            "digest": artifact.digest,
            "beads_issue_id": artifact.beads_issue_id,
            "registered_at": artifact.registered_at,
        }
    )


def coordination_board_transition(payload: dict[str, Any]) -> panel.PanelResponse:
    """Run one guarded board move and answer with canonical Beads state.

    A conflict answers 409 with the state to roll back to, so the browser
    reverts to what `bd` says rather than to what it drew.
    """
    from orch_panel.beads import (
        BeadsMutationError,
        apply_board_transition,
        issue_summary,
        launch_github_sync,
    )
    from orch_panel.coordination.review import done_gate

    epic_id = str(payload.get("epic_id") or "")
    store = panel.coordination_store(create=True)
    epic = store.epic(epic_id)
    if epic is None:
        return panel.json_response({"error": f"unknown epic: {epic_id}"}, status=400)
    issue_id = str(payload.get("issue_id") or "")
    from_column = str(payload.get("from_column") or "")
    if str(payload.get("to_column") or "") == "done":
        # Closing is the one irreversible board move, so the review gate runs
        # before `bd` is reached. It asks about the current executor run only:
        # policy and rounds both belong to a dispatch, and mixing every round on
        # the issue would let an accepted earlier run close a newer unreviewed
        # one. A task whose current run asks for no review is untouched here and
        # closes exactly as it did in Task 2.
        current = store.current_executor_for_issue(epic_id, issue_id)
        allowed, reason = done_gate(
            review_required=bool(current and current.metadata.get("review_required")),
            rounds=(
                store.review_rounds(current.dispatch_id) if current is not None else ()
            ),
        )
        if not allowed:
            return panel.json_response(
                {"error": reason, "column": from_column, "review_gated": True},
                status=409,
            )
    try:
        repo = panel.coordination_repo_for_project(epic.project_id)
        result = apply_board_transition(
            repo,
            issue_id,
            from_column=from_column,
            to_column=str(payload.get("to_column") or ""),
            # Ownership is decided against the epic's own Beads issue, so a
            # request naming another epic's work is refused before any write.
            epic_issue_id=str(epic.beads_issue_id or ""),
        )
    except BeadsMutationError as exc:
        body: dict[str, Any] = {"error": str(exc), "column": exc.column}
        if exc.issue:
            body["issue"] = issue_summary(exc.issue)
        return panel.json_response(body, status=409)
    # Beads has committed. Queue one bounded, detached sync attempt; a launcher
    # failure is logged for the existing status surface and is repaired by the
    # periodic sweep, never by replaying or rolling back this mutation.
    launch_github_sync(repo, issue_id)
    card = issue_summary(result.issue)
    card["column"] = result.column
    return panel.json_response(
        {
            "issue": card,
            "column": result.column,
            # True only asks the browser to open the Start sheet. Nothing is
            # dispatched and nothing is charged until the user presses Start.
            "requires_start": result.requires_start,
        }
    )


def coordination_request_review(payload: dict[str, Any]) -> panel.PanelResponse:
    """Start one fresh cross-provider judge for a finished executor run.

    Every reference is resolved and digested here from the worktree: a
    caller-supplied digest would let a review claim it read a revision the
    repository does not contain.
    """
    from orch_panel.beads import BeadsMutationError
    from orch_panel.coordination.broker import BrokerError, ReviewRequest
    from orch_panel.coordination.models import ArtifactRef
    from orch_panel.coordination.review import ReviewPolicyError, validate_acceptance_receipt

    store = panel.coordination_store(create=True)
    executor_id = str(payload.get("executor_dispatch_id") or "")
    executor = store.dispatch(executor_id)
    if executor is None:
        return panel.json_response({"error": f"unknown dispatch: {executor_id}"}, status=400)
    try:
        repo = panel.coordination_repo_for_project(executor.project_id)
        receipt_path = coordination_repo_file(
            repo, str(payload.get("receipt_path") or ""), "the acceptance receipt"
        )
        # Containment only proves the file is in the repository. A judge told to
        # reuse `README.md` as verification evidence would be reviewing against
        # nothing, so the document itself is checked before a judge is created.
        receipt_relative = receipt_path.relative_to(repo.resolve()).as_posix()
        try:
            # Read once and keep the bytes: the digest the judge is shown has to
            # describe exactly the document that was validated, not whatever the
            # file happens to say by the time the digest is computed.
            receipt_bytes = receipt_path.read_bytes()
            document = json.loads(receipt_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return panel.json_response(
                {"error": f"the acceptance receipt is not readable JSON: {exc}"},
                status=400,
            )
        evidence_report = None
        evidence_report_bytes = None
        current_identity_digest = None
        if (
            isinstance(document, dict)
            and document.get("schema_version") == "acceptance-receipt/v2"
        ):
            manifest_path = coordination_repo_file(
                repo,
                str(document.get("manifest_path") or ""),
                "the verification evidence manifest",
            )
            report_path = coordination_git_common_file(
                repo,
                str(document.get("report_path") or ""),
                "the immutable verification report",
            )
            try:
                evidence_report_bytes = report_path.read_bytes()
                parsed_report = json.loads(evidence_report_bytes.decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                return panel.json_response(
                    {"error": f"the immutable verification report is not readable JSON: {exc}"},
                    status=400,
                )
            verifier = coordination_evidence_verifier()
            try:
                evidence_report = verifier.validate_reusable_receipt(
                    repo_root=repo,
                    manifest_path=manifest_path,
                    receipt_path=receipt_path,
                    report_dir=report_path.parent,
                    stage_id=str(document.get("stage_id") or ""),
                    orchestration_level=str(document.get("orchestration_level") or ""),
                )
            except verifier.EvidenceError as exc:
                return panel.json_response({"error": str(exc)}, status=400)
            if evidence_report is None or evidence_report != parsed_report:
                return panel.json_response(
                    {
                        "error": (
                            "the v2 receipt does not match the current verification identity "
                            "and immutable aggregate report"
                        )
                    },
                    status=400,
                )
            current_identity_digest = str(evidence_report.get("identity_digest") or "")
        manifest_relative = PurePosixPath(receipt_relative).with_name(
            "stage-manifest.json"
        ).as_posix()
        manifest_path = coordination_repo_file(
            repo, manifest_relative, "the acceptance receipt stage manifest"
        )
        try:
            stage_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return panel.json_response(
                {"error": f"the acceptance receipt stage manifest is not readable JSON: {exc}"},
                status=400,
            )
        try:
            validate_acceptance_receipt(
                receipt_relative,
                document,
                stage_manifest=stage_manifest,
                executor_issue_id=executor.beads_issue_id,
                evidence_report=evidence_report,
                evidence_report_bytes=evidence_report_bytes,
                current_identity_digest=current_identity_digest,
            )
        except ReviewPolicyError as exc:
            return panel.json_response({"error": str(exc)}, status=400)
        artifact_refs = []
        for raw in payload.get("artifact_paths") or []:
            resolved = coordination_repo_file(repo, str(raw), "an artifact reference")
            artifact_refs.append(
                ArtifactRef(
                    path=resolved.relative_to(repo.resolve()).as_posix(),
                    digest=hashlib.sha256(resolved.read_bytes()).hexdigest(),
                )
            )
    except BeadsMutationError as exc:
        return panel.json_response({"error": str(exc)}, status=400)

    diff_refs = tuple(
        str(item).strip()[:400] for item in payload.get("diff_refs") or [] if str(item).strip()
    )
    request = ReviewRequest(
        executor_dispatch_id=executor_id,
        requirements=str(payload.get("requirements") or ""),
        receipt=ArtifactRef(
            path=receipt_relative,
            digest=hashlib.sha256(receipt_bytes).hexdigest(),
        ),
        diff_refs=diff_refs,
        artifact_refs=tuple(artifact_refs),
        judge_provider=str(payload.get("judge_provider") or ""),
        idempotency_key=coordination_required_key(payload),
        model=str(payload.get("model") or "") or None,
        confirmed=bool(payload.get("confirm")),
    )
    try:
        dispatch = panel.coordination_broker().request_review(request)
    except BrokerError as exc:
        return panel.json_response({"error": str(exc)}, status=400)
    return panel.json_response(coordination_dispatch_payload(dispatch))


def coordination_disabled_response() -> panel.PanelResponse:
    return panel.json_response(
        {
            "error": "coordination mutations are disabled on this panel",
            "hint": f"start the panel with {COORDINATION_FLAG}=1",
        },
        status=403,
    )


class CoordinationRequestError(ValueError):
    """A malformed coordination request. Nothing is written and no key is used."""


def coordination_required_key(payload: dict[str, Any]) -> str:
    """Take the caller's idempotency key, and refuse to invent one.

    A server-generated key turns one retried submit into two paid runs, because
    each attempt would look like a new explicit action.
    """
    key = str(payload.get("idempotency_key") or "").strip()
    if not key:
        raise CoordinationRequestError(
            "idempotency_key is required: the caller must send one key per "
            "confirmed action and reuse it when retrying"
        )
    return key


def coordination_post(path: str, payload: dict[str, Any]) -> panel.PanelResponse:
    """Handle one coordination mutation behind the local rollout flag."""
    from orch_panel.coordination.broker import BrokerError, DispatchStart
    from orch_panel.coordination.models import ArtifactRef
    from orch_panel.coordination.store import StoreError

    if not panel.coordination_enabled():
        return coordination_disabled_response()
    store = panel.coordination_store(create=True)
    try:
        if path == "/api/coordination/projects":
            repo_path = Path(str(payload.get("repo_path") or panel.CONSOLE_DIR)).resolve()
            allowed = {panel.CONSOLE_DIR.resolve(), *(item.resolve() for item in panel.discover_repos())}
            if repo_path not in allowed:
                return panel.json_response({"error": "repository is not registered"}, status=400)
            project = store.upsert_project(
                str(payload.get("project_id") or DEFAULT_PROJECT_ID),
                name=str(payload.get("name") or repo_path.name),
                repo_path=str(repo_path),
            )
            return panel.json_response(
                {
                    "project_id": project.project_id,
                    "name": project.name,
                    "repo_path": project.repo_path,
                }
            )
        if path == "/api/coordination/epics":
            source_url = str(payload.get("source_url") or "")
            if source_url and not source_url.startswith("https://"):
                return panel.json_response({"error": "source_url must be https"}, status=400)
            epic = store.upsert_epic(
                str(payload.get("epic_id") or f"epic-{panel.uuid_hex()}"),
                project_id=str(payload.get("project_id") or DEFAULT_PROJECT_ID),
                title=str(payload.get("title") or "Untitled epic"),
                beads_issue_id=str(payload.get("beads_issue_id") or "") or None,
                source_kind=str(payload.get("source_kind") or ""),
                source_ref=str(payload.get("source_ref") or ""),
                source_url=source_url,
            )
            return panel.json_response(
                {
                    "epic_id": epic.epic_id,
                    "project_id": epic.project_id,
                    "title": epic.title,
                    "beads_issue_id": epic.beads_issue_id,
                    "source_kind": epic.source_kind,
                    "source_ref": epic.source_ref,
                    "source_url": epic.source_url,
                }
            )
        # The board and the planning register talk to `bd` and to Git, not to a
        # runtime, so they must not construct a broker or a runtime adapter.
        if path == "/api/coordination/planning-artifacts":
            return coordination_register_planning(payload)
        if path == "/api/coordination/board/transition":
            return coordination_board_transition(payload)
        if path == "/api/coordination/reviews":
            return coordination_request_review(payload)
        broker = panel.coordination_broker()
        if path == "/api/coordination/reviews/findings-return":
            dispatch = broker.return_findings(
                str(payload.get("executor_dispatch_id") or ""),
                idempotency_key=coordination_required_key(payload),
                confirmed=bool(payload.get("confirm")),
            )
            return panel.json_response(coordination_dispatch_payload(dispatch))
        if path == "/api/coordination/reviews/decision":
            # The user resolving an escalation is free: it records a decision
            # and starts no runtime.
            record = broker.record_user_decision(
                str(payload.get("executor_dispatch_id") or ""),
                decision=str(payload.get("decision") or ""),
                reason=str(payload.get("reason") or ""),
                idempotency_key=coordination_required_key(payload),
            )
            return panel.json_response(coordination_review_payload(record))
        if path == "/api/coordination/recovery/resolve":
            dispatch = broker.resolve_orphan(
                str(payload.get("dispatch_id") or ""),
                idempotency_key=coordination_required_key(payload),
                confirmed=bool(payload.get("confirm")),
            )
            return panel.json_response(coordination_dispatch_payload(dispatch))
        if path == "/api/coordination/messages":
            event = broker.post_message(
                project_id=str(payload.get("project_id") or DEFAULT_PROJECT_ID),
                epic_id=str(payload.get("epic_id") or ""),
                body_text=str(payload.get("body_text") or ""),
                event_kind=str(payload.get("event_kind") or "message"),
                beads_issue_id=str(payload.get("beads_issue_id") or "") or None,
                idempotency_key=coordination_required_key(payload),
                artifact_refs=[
                    ArtifactRef(
                        path=str(item.get("path") or ""),
                        digest=str(item.get("digest") or ""),
                        media_type=str(item.get("media_type") or "text/plain"),
                    )
                    for item in payload.get("artifact_refs") or []
                ],
            )
            return panel.json_response(coordination_event_payload(event))
        if path == "/api/coordination/dispatches/message":
            event = broker.send_to_dispatch(
                str(payload.get("dispatch_id") or ""),
                body_text=str(payload.get("body_text") or ""),
                idempotency_key=coordination_required_key(payload),
                confirmed=bool(payload.get("confirm")),
            )
            return panel.json_response(coordination_event_payload(event))
        if path == "/api/coordination/dispatches":
            dispatch = broker.start_dispatch(
                DispatchStart(
                    project_id=str(payload.get("project_id") or DEFAULT_PROJECT_ID),
                    epic_id=str(payload.get("epic_id") or ""),
                    provider=str(payload.get("provider") or ""),
                    task_text=str(payload.get("task_text") or ""),
                    write_zone=str(payload.get("write_zone") or ""),
                    verification=str(payload.get("verification") or ""),
                    beads_issue_id=str(payload.get("beads_issue_id") or "") or None,
                    prompt_card_id=str(payload.get("prompt_card_id") or ""),
                    idempotency_key=coordination_required_key(payload),
                    model=str(payload.get("model") or "") or None,
                    reasoning_effort=str(payload.get("reasoning_effort") or "") or None,
                    review_required=bool(payload.get("review_required")),
                    confirmed=bool(payload.get("confirm")),
                    metadata={"task_shape": str(payload.get("task_shape") or "")},
                )
            )
            return panel.json_response(coordination_dispatch_payload(dispatch))
        if path == "/api/coordination/dispatches/cancel":
            dispatch = broker.cancel_dispatch(str(payload.get("dispatch_id") or ""))
            return panel.json_response(coordination_dispatch_payload(dispatch))
    except (BrokerError, StoreError, CoordinationRequestError) as exc:
        return panel.json_response({"error": panel.mask_secret_text(str(exc))}, status=400)
    return panel.error_response(404)
