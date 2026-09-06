"""Kanban projection rules for Beads-backed work.

The board shows Beads status and nothing else. Ready, Running, Blocked, and
Done are projections of `bd`; planning, execution, review, and acceptance are
derived badges. Keeping them in separate namespaces is what stops the panel
from quietly becoming a second task tracker.

This module decides what a transition means and which work the board may touch
at all, never how to run it. `orch_panel.beads` owns the `bd` invocation and
the canonical reread. It also owns planning-path containment, because deciding
which file an epic may adopt is the same kind of rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

# Board columns, in display order.
BOARD_COLUMNS: tuple[str, ...] = ("ready", "running", "blocked", "done")

# Derived badges. Deliberately disjoint from BOARD_COLUMNS so that no phase can
# be mistaken for a status a `bd` command would accept.
BOARD_PHASES: tuple[str, ...] = ("planning", "execution", "review", "accepted")

# Only this column implies a runtime, and therefore an explicit Start sheet.
EXECUTION_COLUMNS = frozenset({"running"})

# Beads statuses the board renders. `deferred`, `pinned`, and `hooked` are real
# Beads statuses that this board does not own; issues in them stay off it.
_STATUS_COLUMN: dict[str, str] = {
    "open": "ready",
    "in_progress": "running",
    "blocked": "blocked",
    "closed": "done",
}

_ACTIVE_DISPATCH_STATES = frozenset({"draft", "awaiting_start", "running", "needs_input"})


# Accepted planning documents live under these roots inside the repository.
PLANNING_ROOTS: dict[str, tuple[str, ...]] = {
    "specification": ("docs", "superpowers", "specs"),
    "plan": ("docs", "superpowers", "plans"),
}


class TransitionError(ValueError):
    """A board move that the transition table does not allow."""


class PlanningPathError(ValueError):
    """A planning path that does not resolve to a file the epic may adopt."""


@dataclass(frozen=True)
class BoardPlacement:
    """Where an issue sits, and whether Beads is what is holding it there.

    `dependency_blocked` separates "Beads says a dependency is unfinished" from
    "somebody set the status to blocked". The first is not the board's to undo.
    """

    column: str | None
    dependency_blocked: bool = False


def issue_belongs_to_epic(issue: dict[str, Any], epic_issue_id: str) -> bool:
    """Report whether one issue is in the selected epic, by canonical `bd` data.

    Membership is the epic itself or a direct child, which is exactly the set
    the board lists through `bd list --parent`. It is decided on whole ids, so
    a shared prefix like `orch-e360` is never read as a child of `orch-e36`.
    """
    epic = (epic_issue_id or "").strip()
    if not epic:
        return False
    issue_id = str(issue.get("id") or "").strip()
    parent = str(issue.get("parent") or "").strip()
    return issue_id == epic or parent == epic


def blocking_dependencies(issue: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """List the unfinished dependencies worth naming in a refusal.

    `bd show --json` nests the parent epic alongside real blockers and carries
    no relationship type, so the parent is excluded by id. This is used for the
    reason text only; `bd blocked` still decides whether an issue is blocked.
    """
    parent = str(issue.get("parent") or "").strip()
    blockers: list[dict[str, Any]] = []
    for dependency in issue.get("dependencies") or []:
        if not isinstance(dependency, dict):
            continue
        if "depends_on_id" in dependency:
            # `bd list --parent` shape: no dependency status, but it does carry
            # the relation type, which is what separates a declared blocker
            # from the parent-child link to the epic.
            if str(dependency.get("type") or "").strip() != "blocks":
                continue
            dependency_id = str(dependency.get("depends_on_id") or "").strip()
            if dependency_id and dependency_id != parent:
                blockers.append({"id": dependency_id})
            continue
        # `bd show` shape: nested issues with a status but no relation type.
        dependency_id = str(dependency.get("id") or "").strip()
        if not dependency_id or dependency_id == parent:
            continue
        if str(dependency.get("status") or "").strip() != "closed":
            blockers.append({"id": dependency_id, **dependency})
    return tuple(blockers)


def resolve_planning_path(repo: Path, kind: str, raw: str) -> Path:
    """Resolve one accepted spec or plan to a real file inside the repository.

    Containment is decided on path components rather than on a string prefix,
    so `docs/superpowers/plans-evil/` cannot pass as `docs/superpowers/plans/`.
    The resolved path is then checked against the resolved repository root,
    which is what rejects a symlink pointing outside the worktree. Both run
    before the caller reads or hashes anything.
    """
    root = PLANNING_ROOTS.get(kind)
    if root is None:
        raise PlanningPathError(f"kind must be one of {sorted(PLANNING_ROOTS)}: {kind!r}")
    relative = PurePosixPath(raw.strip())
    if not raw.strip() or relative.is_absolute() or ".." in relative.parts:
        raise PlanningPathError(
            "path must be repository-relative and stay inside the repository"
        )
    if relative.parts[: len(root)] != root:
        raise PlanningPathError(f"a {kind} must live under {'/'.join(root)}/")
    if len(relative.parts) <= len(root):
        raise PlanningPathError(f"a {kind} must name a file under {'/'.join(root)}/")
    repo_root = Path(repo).resolve()
    planning_root = repo_root.joinpath(*root).resolve()
    resolved = (repo_root / relative).resolve()
    if not resolved.is_relative_to(planning_root):
        raise PlanningPathError(f"{relative} resolves outside {planning_root}")
    if not resolved.is_file():
        raise PlanningPathError(f"{relative} does not exist in {repo_root}")
    return resolved


@dataclass(frozen=True)
class BoardTransition:
    """One allowed move, expressed as intent rather than as a command line."""

    from_column: str
    to_column: str
    action: str  # update | close | reopen
    target_status: str
    requires_start: bool = False

    @property
    def starts_runtime(self) -> bool:
        """Always false. A transition stages work; only Start spends money."""
        return False


_TRANSITIONS: dict[tuple[str, str], BoardTransition] = {
    ("ready", "running"): BoardTransition(
        "ready", "running", "update", "in_progress", requires_start=True
    ),
    ("blocked", "running"): BoardTransition(
        "blocked", "running", "update", "in_progress", requires_start=True
    ),
    ("running", "ready"): BoardTransition("running", "ready", "update", "open"),
    ("running", "blocked"): BoardTransition("running", "blocked", "update", "blocked"),
    ("blocked", "ready"): BoardTransition("blocked", "ready", "update", "open"),
    ("running", "done"): BoardTransition("running", "done", "close", "closed"),
    ("done", "ready"): BoardTransition("done", "ready", "reopen", "open"),
}


def column_for_issue(
    issue: dict[str, Any], blocked_ids: Iterable[str] = ()
) -> str | None:
    """Project one Beads issue onto a board column, or off the board.

    `blocked_ids` comes from `bd blocked`, which is the only thing that knows
    which dependency actually blocks. The nested dependency list in `bd show`
    mixes the parent epic with real blockers and carries no relationship type,
    so re-deriving "blocked" here would mark every child of an open epic
    blocked. Beads decides; this function only projects.
    """
    status = str(issue.get("status") or "").strip()
    column = _STATUS_COLUMN.get(status)
    if column is None:
        return None
    if column == "ready" and str(issue.get("id") or "") in set(blocked_ids):
        return "blocked"
    return column


def place_issue(issue: dict[str, Any], blocked_ids: Iterable[str] = ()) -> BoardPlacement:
    """Project one issue and record why it landed in Blocked, when it did."""
    status = str(issue.get("status") or "").strip()
    column = _STATUS_COLUMN.get(status)
    if column is None:
        return BoardPlacement(None)
    if column == "ready" and str(issue.get("id") or "") in set(blocked_ids):
        return BoardPlacement("blocked", dependency_blocked=True)
    return BoardPlacement(column)


def derive_phase(column: str, dispatches: Sequence[dict[str, Any]] | Iterable[Any]) -> str:
    """Derive the orchestration badge. This never becomes a Beads status."""
    if column == "done":
        return "accepted"
    states = {str(item.get("state") or "") for item in dispatches if isinstance(item, dict)}
    if states & _ACTIVE_DISPATCH_STATES:
        return "execution"
    if states:
        return "review"
    return "planning"


def plan_transition(
    from_column: str, to_column: str, *, dependency_blocked: bool = False
) -> BoardTransition:
    """Resolve one requested move against the allowlist.

    The reason is part of the contract: a rejected drop has to tell the user
    what was refused, not just snap the card back.
    """
    if from_column not in BOARD_COLUMNS:
        raise TransitionError(f"'{from_column}' is not a board column")
    if to_column not in BOARD_COLUMNS:
        raise TransitionError(f"'{to_column}' is not a board column")
    if from_column == to_column:
        raise TransitionError(f"'{from_column}' is already the current column")
    if dependency_blocked and to_column not in allowed_targets(
        from_column, dependency_blocked=True
    ):
        # Beads put this card in Blocked because something it depends on is
        # unfinished. Moving it here would only desynchronise the board from
        # `bd`, which would undo the move on the next read.
        raise TransitionError(
            f"'{from_column}' to '{to_column}' is refused: Beads reports an "
            "unfinished dependency, so this card cannot leave Blocked until "
            "that dependency closes"
        )
    transition = _TRANSITIONS.get((from_column, to_column))
    if transition is None:
        raise TransitionError(
            f"moving '{from_column}' to '{to_column}' is not an allowed Beads transition"
        )
    return transition


def allowed_targets(
    from_column: str, *, dependency_blocked: bool = False
) -> tuple[str, ...]:
    """List the moves the board may offer, for menus and keyboard controls.

    A dependency-blocked card offers nothing: the board must not present a
    control whose only outcome is a refusal.
    """
    if dependency_blocked:
        return ()
    return tuple(
        target for (source, target) in _TRANSITIONS if source == from_column
    )
