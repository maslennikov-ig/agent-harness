"""Beads board data and guarded Beads mutations for the orchestration panel.

Queries `bd` per repository containing `.beads/` and returns ready,
in-progress, and blocked issues so the dashboard can show work state,
not just tool presence.

Mutations follow the same rule as reads: `bd` is the only writer. The panel
holds an allowlist of transitions, validates the repository path, runs one CLI
command, and then rereads the issue so the browser always renders Beads truth
rather than the move the user attempted.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from orch_panel.coordination.workflow import (
    BoardPlacement,
    BoardTransition,
    TransitionError,
    blocking_dependencies,
    column_for_issue,
    issue_belongs_to_epic,
    place_issue,
    plan_transition,
)

BD_TIMEOUT = 20
ISSUE_LIMIT = 20
REPO_WORKERS = 16
STATUS_QUERIES: tuple[tuple[str, list[str]], ...] = (
    ("ready", ["bd", "ready", "--limit=0", "--json"]),
    ("in_progress", ["bd", "list", "--status=in_progress", "--limit=0", "--json"]),
    ("blocked", ["bd", "blocked", "--json"]),
)


def bd_available() -> bool:
    return shutil.which("bd") is not None


def beads_repos(candidates: list[Path]) -> list[Path]:
    repos: list[Path] = []
    seen: set[Path] = set()
    for repo in candidates:
        resolved = repo.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / ".beads").is_dir():
            repos.append(resolved)
    return repos


def run_bd(repo: Path, args: list[str]) -> tuple[list[dict[str, Any]], str]:
    try:
        result = subprocess.run(
            args,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=BD_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"{args[1]}: {exc.__class__.__name__}"
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        return [], f"{args[1]}: {tail[-1] if tail else f'exit {result.returncode}'}"
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return [], f"{args[1]}: invalid JSON output"
    if not isinstance(data, list):
        return [], ""
    return [item for item in data if isinstance(item, dict)], ""


def issue_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or ""),
        "status": str(item.get("status") or ""),
        "priority": item.get("priority"),
        "issue_type": str(item.get("issue_type") or ""),
        "assignee": str(item.get("assignee") or item.get("owner") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        # `bd github sync` stores the issue URL here, so the card can link back
        # to the GitHub side of the same work.
        "external_ref": str(item.get("external_ref") or ""),
    }


def repo_board(repo: Path, issue_limit: int | None = ISSUE_LIMIT) -> dict[str, Any]:
    board: dict[str, Any] = {
        "project": repo.name,
        "repo_path": str(repo),
        "counts": {},
        "errors": [],
    }
    for key, args in STATUS_QUERIES:
        issues, error = run_bd(repo, args)
        visible = issues if issue_limit is None else issues[:issue_limit]
        board[key] = [issue_summary(item) for item in visible]
        board["counts"][key] = len(issues)
        if error:
            board["errors"].append(error)
    return board


# A Beads issue id as the CLI prints it: prefix, digits, and dotted children.
# Anything else never reaches argv, so a flag or a shell fragment cannot be
# smuggled in through an id even though argv is already a list.
ISSUE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*-[A-Za-z0-9]+(\.[0-9]+)*$")
SYNC_LAUNCHER = Path(".agents/orchestration-console/scripts/github_sync.sh")


class BeadsMutationError(RuntimeError):
    """A refused or failed mutation, carrying the state to roll back to.

    `issue` and `column` are the canonical reread when one was possible, so the
    browser can revert the card to Beads truth instead of to its own guess.
    """

    def __init__(
        self,
        message: str,
        *,
        issue: dict[str, Any] | None = None,
        column: str | None = None,
    ) -> None:
        super().__init__(message)
        self.issue = issue or {}
        self.column = column


def github_sync_trigger_argv(
    repo: Path,
    issue_id: str,
    *,
    home: Path | None = None,
) -> list[str]:
    """Build the one stable, bounded sync trigger for a changed Bead."""
    if not ISSUE_ID.match(issue_id or ""):
        raise BeadsMutationError(f"'{issue_id}' is not a Beads issue id")
    launcher = (home or Path.home()) / SYNC_LAUNCHER
    return [str(launcher), "--trigger", "--bead", issue_id, str(repo)]


def github_sync_log_path(repo: Path) -> Path:
    """Resolve Git's shared sync log without starting another process."""
    dot_git = repo / ".git"
    git_dir = dot_git
    if dot_git.is_file():
        try:
            marker = dot_git.read_text(encoding="utf-8").strip()
        except OSError:
            marker = ""
        if marker.startswith("gitdir:"):
            candidate = Path(marker.removeprefix("gitdir:").strip())
            git_dir = candidate if candidate.is_absolute() else (repo / candidate).resolve()
    common_dir = git_dir
    common_marker = git_dir / "commondir"
    if common_marker.is_file():
        try:
            candidate = Path(common_marker.read_text(encoding="utf-8").strip())
            common_dir = candidate if candidate.is_absolute() else (git_dir / candidate).resolve()
        except OSError:
            common_dir = git_dir
    return common_dir / "github-sync.log"


# Compatibility for focused callers created before the helper became shared
# with the policy-aware status reader.
_github_sync_log_path = github_sync_log_path


def launch_github_sync(
    repo: Path,
    issue_id: str,
    *,
    popen: Callable[..., Any] | None = None,
    log_path: Path | None = None,
) -> bool:
    """Detach one durable sync trigger; a spawn failure never undoes Beads.

    Both launcher output and a failure to spawn it use the repository's
    existing ``github-sync.log``, which is already exposed by the panel status
    endpoint. The caller deliberately ignores the boolean: the Beads write is
    committed, while the durable periodic sweep repairs eventual consistency.
    """
    popen = popen or subprocess.Popen
    target = log_path or github_sync_log_path(repo)
    argv = github_sync_trigger_argv(repo, issue_id)
    try:
        with target.open("ab") as stream:
            try:
                popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as exc:
                message = f"github sync trigger failed for {issue_id}: {exc}\n"
                stream.write(message.encode("utf-8", errors="replace"))
                stream.flush()
                print(message.rstrip(), file=sys.stderr)
                return False
    except OSError as exc:
        print(f"github sync trigger log failed for {issue_id}: {exc}", file=sys.stderr)
        return False
    return True


@dataclass(frozen=True)
class TransitionResult:
    """Canonical state after one accepted mutation."""

    issue: dict[str, Any]
    column: str | None
    transition: BoardTransition

    @property
    def requires_start(self) -> bool:
        """Only a card that actually landed in an execution column may ask."""
        return self.transition.requires_start and self.column == self.transition.to_column


def _linked_worktree_has_common_beads(repo: Path) -> bool:
    """Recognize Git's mutually linked worktree metadata without running Git.

    A registered path alone is not enough to trust an external ``.beads``
    directory. The worktree pointer, common-directory placement, and Git's
    backlink must all agree before the common repository may supply Beads.
    """
    dot_git = repo / ".git"
    if dot_git.is_symlink() or not dot_git.is_file():
        return False
    try:
        marker_lines = dot_git.read_text(encoding="utf-8").splitlines()
        if len(marker_lines) != 1 or not marker_lines[0].startswith("gitdir: "):
            return False
        raw_git_dir = marker_lines[0].removeprefix("gitdir: ").strip()
        if not raw_git_dir:
            return False
        candidate = Path(raw_git_dir)
        git_dir = (candidate if candidate.is_absolute() else repo / candidate).resolve()
        if not git_dir.is_dir():
            return False

        common_marker = git_dir / "commondir"
        backlink_marker = git_dir / "gitdir"
        if (
            common_marker.is_symlink()
            or backlink_marker.is_symlink()
            or not common_marker.is_file()
            or not backlink_marker.is_file()
        ):
            return False

        raw_common = common_marker.read_text(encoding="utf-8").strip()
        raw_backlink = backlink_marker.read_text(encoding="utf-8").strip()
        if not raw_common or not raw_backlink:
            return False
        common_path = Path(raw_common)
        common_dir = (
            common_path if common_path.is_absolute() else git_dir / common_path
        ).resolve()
        backlink_path = Path(raw_backlink)
        backlink = (
            backlink_path if backlink_path.is_absolute() else git_dir / backlink_path
        ).resolve()
        dot_git = dot_git.resolve()
    except (OSError, RuntimeError, UnicodeError):
        return False

    return (
        common_dir.is_dir()
        and common_dir.name == ".git"
        and git_dir.parent == common_dir / "worktrees"
        and backlink == dot_git
        and (common_dir.parent / ".beads").is_dir()
    )


def resolve_beads_repo(repo_path: str, candidates: list[Path]) -> Path:
    """Resolve one repository path against the registered set.

    Registration is the allowlist. A path is usable only when it resolves to a
    registered repository that actually carries a Beads database, which also
    rejects `..` traversal out of a registered root.
    """
    try:
        resolved = Path(repo_path).resolve()
    except OSError as exc:
        raise BeadsMutationError(f"repository path is unusable: {exc}") from exc
    allowed = {item.resolve() for item in candidates}
    if resolved not in allowed:
        raise BeadsMutationError(f"repository is not registered: {resolved}")
    if not (resolved / ".beads").is_dir() and not _linked_worktree_has_common_beads(
        resolved
    ):
        raise BeadsMutationError(f"repository has no Beads database: {resolved}")
    return resolved


def mutation_argv(transition: BoardTransition, issue_id: str) -> list[str]:
    """Build the one allowlisted `bd` command for an approved transition."""
    if not ISSUE_ID.match(issue_id or ""):
        raise BeadsMutationError(f"'{issue_id}' is not a Beads issue id")
    if transition.action == "close":
        return ["bd", "close", issue_id, "--json"]
    if transition.action == "reopen":
        return ["bd", "reopen", issue_id, "--json"]
    if transition.action == "update":
        return ["bd", "update", issue_id, f"--status={transition.target_status}", "--json"]
    raise BeadsMutationError(f"'{transition.action}' is not an allowed Beads action")


def read_issue(
    repo: Path,
    issue_id: str,
    runner: Callable[[Path, list[str]], tuple[list[dict[str, Any]], str]] | None = None,
) -> dict[str, Any]:
    """Reread one issue from `bd`. This is the only source of board truth."""
    runner = runner or run_bd
    if not ISSUE_ID.match(issue_id or ""):
        raise BeadsMutationError(f"'{issue_id}' is not a Beads issue id")
    issues, error = runner(repo, ["bd", "show", issue_id, "--json"])
    if error:
        raise BeadsMutationError(f"reading {issue_id} failed: {error}")
    if not issues:
        raise BeadsMutationError(f"{issue_id} does not exist in {repo}")
    return issues[0]


def blocked_ids(
    repo: Path,
    runner: Callable[[Path, list[str]], tuple[list[dict[str, Any]], str]] | None = None,
) -> frozenset[str]:
    """Ask Beads which issues are blocked. Never inferred from a dependency list."""
    runner = runner or run_bd
    issues, error = runner(repo, ["bd", "blocked", "--json"])
    if error:
        raise BeadsMutationError(f"reading blocked issues failed: {error}")
    return frozenset(str(item.get("id") or "") for item in issues)


def resolve_placement(
    repo: Path,
    issue: dict[str, Any],
    runner: Callable[[Path, list[str]], tuple[list[dict[str, Any]], str]] | None = None,
) -> BoardPlacement:
    """Place one issue, consulting `bd blocked` only when it can matter.

    An issue is only ever moved into Blocked by a dependency from `open`, so
    any other status is decided without a second CLI call.
    """
    runner = runner or run_bd
    if str(issue.get("status") or "").strip() != "open":
        return place_issue(issue)
    return place_issue(issue, blocked_ids=blocked_ids(repo, runner))


def resolve_column(
    repo: Path,
    issue: dict[str, Any],
    runner: Callable[[Path, list[str]], tuple[list[dict[str, Any]], str]] | None = None,
) -> str | None:
    """Column only, for callers that do not care why a card sits in Blocked."""
    return resolve_placement(repo, issue, runner).column


def apply_board_transition(
    repo: Path,
    issue_id: str,
    *,
    from_column: str,
    to_column: str,
    epic_issue_id: str,
    runner: Callable[[Path, list[str]], tuple[list[dict[str, Any]], str]] | None = None,
) -> TransitionResult:
    """Run one guarded board move and return canonical Beads state.

    The order matters. The transition is checked before anything runs, the
    board's idea of the current column is checked against a fresh read so a
    stale card cannot overwrite newer truth, and the result always comes from a
    reread rather than from the requested target.
    """
    runner = runner or run_bd
    try:
        plan_transition(from_column, to_column)
    except TransitionError as exc:
        # Refuse a nonsense move before `bd` is touched at all.
        raise BeadsMutationError(str(exc)) from exc

    current = read_issue(repo, issue_id, runner=runner)

    if not issue_belongs_to_epic(current, epic_issue_id):
        # A repository holds many epics. Reading is fine; moving another
        # epic's work from this board is not, so this runs before any
        # mutating command and before the placement lookup.
        raise BeadsMutationError(
            f"{issue_id} does not belong to epic '{epic_issue_id or 'unset'}'; "
            "the board may only move its own epic",
            issue=current,
        )

    placement = resolve_placement(repo, current, runner)
    if placement.column != from_column:
        raise BeadsMutationError(
            f"{issue_id} is in '{placement.column or 'off-board'}', not '{from_column}'; "
            "the board was stale and nothing was changed",
            issue=current,
            column=placement.column,
        )

    try:
        transition = plan_transition(
            from_column, to_column, dependency_blocked=placement.dependency_blocked
        )
    except TransitionError as exc:
        blockers = ", ".join(
            str(item.get("id") or "") for item in blocking_dependencies(current)
        )
        detail = f" Unfinished: {blockers}." if blockers else ""
        raise BeadsMutationError(
            f"{issue_id}: {exc}.{detail}",
            issue=current,
            column=placement.column,
        ) from exc

    _, error = runner(repo, mutation_argv(transition, issue_id))
    if error:
        # The CLI refused, so nothing was written. Reread anyway: the caller
        # needs Beads truth to revert to, not the pre-drop client state.
        try:
            canonical = read_issue(repo, issue_id, runner=runner)
        except BeadsMutationError:
            raise BeadsMutationError(f"{issue_id}: {error}") from None
        raise BeadsMutationError(
            f"{issue_id}: {error}",
            issue=canonical,
            column=resolve_column(repo, canonical, runner),
        )

    canonical = read_issue(repo, issue_id, runner=runner)
    return TransitionResult(
        issue=canonical,
        column=resolve_column(repo, canonical, runner),
        transition=transition,
    )


def beads_board_payload(
    candidates: list[Path], issue_limit: int | None = ISSUE_LIMIT
) -> dict[str, Any]:
    generated_at = int(time.time())
    if not bd_available():
        return {
            "available": False,
            "error": "bd CLI not found",
            "repos": [],
            "issue_limit": issue_limit,
            "generated_at": generated_at,
        }
    repos = beads_repos(candidates)
    if not repos:
        return {
            "available": True,
            "repos": [],
            "issue_limit": issue_limit,
            "generated_at": generated_at,
        }
    with ThreadPoolExecutor(max_workers=min(REPO_WORKERS, len(repos))) as pool:
        boards = list(pool.map(lambda repo: repo_board(repo, issue_limit), repos))
    boards.sort(key=lambda board: (-board["counts"].get("ready", 0), board["project"]))
    totals = {
        key: sum(board["counts"].get(key, 0) for board in boards)
        for key, _ in STATUS_QUERIES
    }
    return {
        "available": True,
        "repos": boards,
        "totals": totals,
        "issue_limit": issue_limit,
        "generated_at": generated_at,
    }
