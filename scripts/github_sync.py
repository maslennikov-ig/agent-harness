#!/usr/bin/env python3
"""Low-overhead, Beads-authoritative GitHub issue reconciliation.

The coordinator owns its cursors and durable queue.  It deliberately does not
call ``bd github``: targeted Beads sync mutates Beads' integration cursor and
cannot express the asymmetric status authority required here.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol


BEGIN_MARKER = "# >>> orchestration-console github sync >>>"
END_MARKER = "# <<< orchestration-console github sync <<<"
STATE_SCHEMA = "beads-github-sync/v1"
DEFAULT_OVERLAP_SECONDS = 300
MIN_RATE_REMAINING = 500
BD_TIMEOUT_SECONDS = 60.0
IDENTITY_TIMEOUT_SECONDS = 5.0
VERSION_TIMEOUT_SECONDS = 10.0
AUTH_TIMEOUT_SECONDS = 10.0
WORKSPACE_SWEEP_BUDGET_SECONDS = 150.0
WORKSPACE_SWEEP_SCHEMA = "beads-github-workspace-sweep/v1"
LINK_INDEX_VERSION = "canonical-v1"
_STATE_MUTEXES: dict[str, threading.RLock] = {}
_STATE_MUTEXES_GUARD = threading.Lock()
_AUTH_TOKEN_CACHE: dict[str, str] = {}
_AUTH_TOKEN_LOCK = threading.Lock()


class SyncError(RuntimeError):
    pass


class IdentityError(SyncError):
    pass


class LockBusy(SyncError):
    pass


class PartialDiscovery(SyncError):
    pass


class RateLimited(SyncError):
    pass


class LeaseLost(SyncError):
    pass


@dataclass(frozen=True)
class Bead:
    id: str
    title: str
    description: str
    status: str
    updated_at: str
    external_ref: str = ""


@dataclass(frozen=True)
class GithubIssue:
    number: int
    title: str
    body: str
    state: str
    updated_at: str
    url: str
    is_pull_request: bool = False


@dataclass(frozen=True)
class RepositoryIdentity:
    repo: Path
    slug: str
    git_common_dir: Path
    beads_dir: Path
    database_id: str
    state_dir: Path
    state_file: Path
    lock_file: Path
    # `issue-prefix` from the repository's own `.beads/config.yaml`, or None when
    # the file does not declare one. A bead id belongs to exactly one database,
    # and this is the only local statement of which.
    issue_prefix: str | None = None


def read_issue_prefix(beads_dir: Path) -> str | None:
    """The `issue-prefix` this Beads database stamps on every id it owns.

    Parsed with a regex rather than a YAML parser: this module has no third-party
    dependencies, and the key is a plain scalar on its own line. Returns None when
    the file is missing or says nothing, which callers must treat as "unknown",
    never as "matches nothing".
    """
    config = beads_dir / "config.yaml"
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(
        r"^\s*issue-prefix\s*:\s*['\"]?([A-Za-z0-9][A-Za-z0-9_-]*?)['\"]?\s*(?:#.*)?$",
        text,
        re.MULTILINE,
    )
    return match.group(1) if match else None


def bead_belongs_to_prefix(bead_id: str, prefix: str | None) -> bool:
    """Whether `bead_id` was issued by the database that stamps `prefix`.

    Unknown prefix answers True: a repository that does not declare one keeps the
    behaviour it had before this check existed. `"*"` is the full-scan sentinel and
    belongs to every repository.
    """
    if prefix is None or bead_id == "*":
        return True
    return bead_id.startswith(f"{prefix}-")


@dataclass
class RepositoryInventory:
    identities: list[RepositoryIdentity]
    entries: list[dict[str, Any]]
    errors: list[str]
    alias_migrations: list["AliasMigration"] = field(default_factory=list)

    def require_unambiguous(self) -> list[RepositoryIdentity]:
        if self.errors:
            raise IdentityError("; ".join(self.errors))
        return self.identities


@dataclass(frozen=True)
class AliasMigration:
    source_repo: Path
    source_beads: Path
    canonical_repo: Path
    canonical_beads: Path
    slug: str
    database_id: str


@dataclass(frozen=True)
class RepositoryStatus:
    status: str
    identity: RepositoryIdentity | None
    reason: str = ""
    alias_migration: AliasMigration | None = None


class BeadsPort(Protocol):
    def list_candidates(
        self, since: str | None, pending_ids: Iterable[str], full_scan: bool
    ) -> list[Bead]: ...
    def list_linked(self) -> list[Bead]: ...
    def find_by_external_ref(
        self,
        url: str,
        candidates: Iterable[Bead] = (),
        *,
        default_slug: str | None = None,
    ) -> Bead | None: ...
    def find_by_external_refs(
        self,
        urls: Iterable[str],
        slug: str,
        candidates: Iterable[Bead] = (),
        *,
        default_slug: str | None = None,
    ) -> dict[str, Bead]: ...
    def import_issue(self, issue: GithubIssue) -> Bead: ...
    def create_import(self, issue: GithubIssue) -> Bead: ...
    def set_status(self, bead_id: str, status: str) -> None: ...
    def set_external_ref(self, bead_id: str, url: str) -> None: ...
    def get(self, bead_id: str) -> Bead: ...


class GithubPort(Protocol):
    def discover(
        self,
        since: str | None,
        *,
        start_url: str | None = None,
        page_checkpoint: Callable[[str, list[GithubIssue]], None] | None = None,
    ) -> list[GithubIssue]: ...
    def get(self, number: int) -> GithubIssue: ...
    def find_by_markers(
        self, markers: Iterable[str], since: str | None
    ) -> dict[str, GithubIssue]: ...
    def create(self, bead: Bead, marker: str) -> GithubIssue: ...
    def patch_state(self, number: int, state: str) -> GithubIssue: ...


def _run_git(repo: Path, *args: str, timeout: float = 5.0) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise IdentityError(
            f"git {' '.join(args)} timed out after {timeout:g}s for {repo}"
        ) from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise IdentityError(detail[-1] if detail else f"git {' '.join(args)} failed")
    return result.stdout.strip()


def normalize_github_slug(remote: str) -> str:
    value = remote.strip()
    match = re.fullmatch(
        r"(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)([^/\s]+/[^/\s]+?)(?:\.git)?/?",
        value,
        re.IGNORECASE,
    )
    if not match:
        raise IdentityError(f"origin is not an unambiguous GitHub repository: {remote!r}")
    slug = match.group(1).removesuffix(".git")
    if slug.count("/") != 1:
        raise IdentityError(f"invalid GitHub slug: {slug!r}")
    return slug.lower()


def _worktree_main(root: Path) -> Path:
    raw = _run_git(root, "worktree", "list", "--porcelain", "-z")
    paths = [
        Path(record.removeprefix("worktree ")).resolve()
        for record in raw.split("\0")
        if record.startswith("worktree ")
    ]
    if not paths:
        raise IdentityError(f"cannot establish canonical Git worktree for {root}")
    return paths[0]


def _database_identity(beads_dir: Path) -> str:
    metadata_path = beads_dir / "metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityError(f"missing or invalid Beads identity metadata: {metadata_path}") from exc
    backend = str(metadata.get("backend") or "").strip().lower()
    database = str(metadata.get("dolt_database") or "").strip()
    physical: set[str] = set()
    if not database or not backend:
        for parent_name in ("embeddeddolt", "dolt"):
            parent = beads_dir / parent_name
            if not parent.is_dir():
                continue
            physical.update(
                item.name
                for item in parent.iterdir()
                if item.is_dir() and (item / ".dolt").is_dir()
            )
        if len(physical) != 1:
            raise IdentityError(
                f"cannot derive one physical Beads database from {metadata_path}: {sorted(physical)}"
            )
    if not backend:
        backend = "dolt"
    if not database:
        database = next(iter(physical))
    if not backend or not database or not re.fullmatch(r"[A-Za-z0-9_.-]+", database):
        raise IdentityError(f"missing or invalid Beads database identity: {metadata_path}")
    raw_project = str(metadata.get("project_id") or "")
    if raw_project:
        try:
            project_id = str(uuid.UUID(raw_project))
        except (ValueError, AttributeError) as exc:
            raise IdentityError(f"invalid Beads project_id: {metadata_path}") from exc
        return f"{backend}:{database}:{project_id}"
    return f"{backend}:{database}"


def _beads_project_uuid(beads_dir: Path) -> str | None:
    metadata_path = beads_dir / "metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityError(f"missing or invalid Beads identity metadata: {metadata_path}") from exc
    raw_project = str(metadata.get("project_id") or "").strip()
    if not raw_project:
        return None
    try:
        return str(uuid.UUID(raw_project))
    except (ValueError, AttributeError) as exc:
        raise IdentityError(f"invalid Beads project_id: {metadata_path}") from exc


def resolve_repository(repo: Path | str) -> RepositoryIdentity:
    requested = Path(repo).expanduser().resolve()
    root = Path(_run_git(requested, "rev-parse", "--show-toplevel")).resolve()
    requested_beads = root / ".beads"
    if not requested_beads.exists() or not requested_beads.is_dir():
        raise IdentityError(f"requested Git root has no owned .beads database: {root}")
    requested_database_id = _database_identity(requested_beads.resolve())
    common_raw = Path(_run_git(root, "rev-parse", "--git-common-dir"))
    common = (root / common_raw).resolve() if not common_raw.is_absolute() else common_raw.resolve()
    canonical_root = _worktree_main(root)
    beads = canonical_root / ".beads"
    if not beads.exists() or not beads.is_dir():
        raise IdentityError(f"canonical Git root has no owned .beads database: {canonical_root}")
    beads = beads.resolve()
    database_id = _database_identity(beads)
    if requested_database_id != database_id:
        raise IdentityError(
            f"worktree Beads identity does not match canonical owner: {root} != {canonical_root}"
        )
    slug = normalize_github_slug(_run_git(canonical_root, "remote", "get-url", "origin"))
    key = hashlib.sha256(f"{database_id}\0{slug}".encode()).hexdigest()[:20]
    state_dir = common / "beads-github-sync" / key
    return RepositoryIdentity(
        repo=canonical_root,
        slug=slug,
        git_common_dir=common,
        beads_dir=beads,
        database_id=database_id,
        state_dir=state_dir,
        state_file=state_dir / "state.json",
        lock_file=state_dir / "worker.lock",
        issue_prefix=read_issue_prefix(beads),
    )


def inventory_repositories(
    repositories: Iterable[Path | str], exclusions: Iterable[str] = ()
) -> list[RepositoryIdentity]:
    inventory = audit_repositories(repositories, exclusions=exclusions)
    ineligible = [
        entry for entry in inventory.entries if entry.get("status") == "ineligible"
    ]
    if ineligible:
        raise IdentityError("; ".join(str(item.get("reason")) for item in ineligible))
    return inventory.require_unambiguous()


def _exclusion_reasons(exclusions: Iterable[Any]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for item in exclusions:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip().lower()
            reason = str(item.get("reason") or "explicitly excluded").strip()
        else:
            name = str(item).strip().lower()
            reason = "explicitly excluded"
        if name:
            reasons[name] = reason
    return reasons


def audit_repositories(
    repositories: Iterable[Path | str],
    *,
    workspace: Path | None = None,
    aliases: dict[str, Any] | None = None,
    alias_backup_root: Path | None = None,
    exclusions: Iterable[str] = (),
) -> RepositoryInventory:
    workspace = (workspace or Path.cwd()).expanduser().resolve()
    aliases = aliases or {}
    excluded = _exclusion_reasons(exclusions)
    identities: list[RepositoryIdentity] = []
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    by_slug: dict[str, tuple[str, str]] = {}
    by_database: dict[str, tuple[str, str]] = {}
    seen: set[tuple[str, str, str]] = set()
    alias_migrations: list[AliasMigration] = []
    for candidate in repositories:
        requested = Path(candidate).expanduser()
        path = requested
        if path.name.lower() in excluded:
            entries.append(
                {
                    "path": str(path),
                    "status": "excluded",
                    "reason": excluded[path.name.lower()],
                }
            )
            continue
        alias_spec = aliases.get(path.name)
        status = "eligible"
        if alias_spec is not None:
            if not isinstance(alias_spec, dict) or alias_spec.get("mode") != "redirect":
                entries.append(
                    {
                        "path": str(path),
                        "status": "ineligible",
                        "reason": "repository alias must declare redirect mode",
                    }
                )
                continue
            alias_target = str(alias_spec.get("canonical") or "")
            target = Path(alias_target)
            if target.is_absolute() or ".." in target.parts:
                entries.append(
                    {
                        "path": str(path),
                        "status": "ineligible",
                        "reason": f"unsafe repository alias target: {alias_target}",
                    }
                )
                continue
            canonical_path = workspace / target
            try:
                identity = resolve_repository(canonical_path)
                canonical_project_id = _beads_project_uuid(identity.beads_dir)
                if canonical_project_id is None:
                    raise IdentityError(
                        "alias redirect requires a canonical Beads project_id UUID"
                    )
                source_root = Path(
                    _run_git(requested.resolve(), "rev-parse", "--show-toplevel")
                ).resolve()
                source_slug = normalize_github_slug(
                    _run_git(source_root, "remote", "get-url", "origin")
                )
                if source_slug != identity.slug:
                    raise IdentityError(
                        f"alias origin {source_slug} does not match canonical {identity.slug}"
                    )
                source_beads = source_root / ".beads"
                migration = AliasMigration(
                    source_repo=source_root,
                    source_beads=source_beads,
                    canonical_repo=identity.repo,
                    canonical_beads=identity.beads_dir,
                    slug=identity.slug,
                    database_id=identity.database_id,
                )
                redirect = source_beads / "redirect"
                if redirect.is_file():
                    lines = [
                        line.strip()
                        for line in redirect.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    if len(lines) != 1:
                        raise IdentityError(f"alias redirect must contain one path: {redirect}")
                    raw_target = Path(lines[0]).expanduser()
                    redirect_target = (
                        raw_target.resolve()
                        if raw_target.is_absolute()
                        else (source_root / raw_target).resolve()
                    )
                    if redirect_target != identity.beads_dir:
                        raise IdentityError(
                            f"alias redirect target does not match canonical Beads: {redirect}"
                        )
                    if (redirect_target / "redirect").exists():
                        raise IdentityError(f"redirect chain is not supported: {redirect}")
                    status = "alias"
                else:
                    if not source_beads.is_dir():
                        if alias_backup_root is None:
                            raise IdentityError(
                                f"alias has no .beads database: {source_root}"
                            )
                        _, receipt_path, original, staged = _alias_paths(
                            migration, alias_backup_root.expanduser().resolve()
                        )
                        if not (receipt_path.is_file() and original.is_dir()):
                            raise IdentityError(
                                f"alias has no recoverable .beads migration: {source_root}"
                            )
                        receipt = _validated_alias_receipt(
                            migration,
                            alias_backup_root.expanduser().resolve(),
                            phases={
                                "backed_up",
                                "rollback_prepared",
                                "redirect_backed_up",
                            },
                        )
                        installed = original.parent / "installed-redirect"
                        if receipt["phase"] == "backed_up" and not staged.is_dir():
                            raise IdentityError(
                                f"alias migration staged redirect is missing: {staged}"
                            )
                        if (
                            receipt["phase"]
                            in {"rollback_prepared", "redirect_backed_up"}
                            and not installed.is_dir()
                        ):
                            raise IdentityError(
                                f"alias rollback redirect backup is missing: {installed}"
                            )
                        if installed.is_dir():
                            _validated_redirect_target(installed, migration)
                        status = "alias-migration-required"
                        alias_migrations.append(migration)
                        source_database_id = identity.database_id
                    else:
                        source_database_id = _database_identity(source_beads)
                    if source_database_id != identity.database_id:
                        raise IdentityError(
                            "alias Beads identity does not match canonical: "
                            f"{source_database_id} != {identity.database_id}"
                        )
                    status = "alias-migration-required"
                    if migration not in alias_migrations:
                        alias_migrations.append(migration)
            except IdentityError as exc:
                entries.append(
                    {"path": str(requested), "status": "ineligible", "reason": str(exc)}
                )
                continue
            path = canonical_path
        else:
            try:
                identity = resolve_repository(path)
            except IdentityError as exc:
                entries.append(
                    {"path": str(requested), "status": "ineligible", "reason": str(exc)}
                )
                continue
        ownership = (identity.database_id, str(identity.git_common_dir))
        prior_db = by_slug.setdefault(identity.slug, ownership)
        if prior_db != ownership:
            errors.append(
                f"GitHub slug {identity.slug} is owned by multiple Beads databases: "
                f"{prior_db} and {ownership}"
            )
        target = (identity.slug, str(identity.git_common_dir))
        prior_slug = by_database.setdefault(identity.database_id, target)
        if prior_slug != target:
            errors.append(
                f"Beads database {identity.database_id} maps to multiple GitHub slugs: "
                f"{prior_slug} and {target}"
            )
        pair = (identity.database_id, identity.slug, str(identity.git_common_dir))
        if pair not in seen:
            identities.append(identity)
            seen.add(pair)
        entry = {
            "path": str(requested),
            "status": status,
            "canonical_repo": str(identity.repo),
            "slug": identity.slug,
            "database_id": identity.database_id,
        }
        entries.append(entry)
    return RepositoryInventory(
        identities=identities,
        entries=entries,
        errors=errors,
        alias_migrations=alias_migrations,
    )


def audit_external_references(
    inventory: RepositoryInventory,
    *,
    repository_routes: dict[str, Any],
    loader: Callable[[RepositoryIdentity], Iterable[Bead]],
) -> RepositoryInventory:
    """Fail strict enrollment on GitHub-shaped refs outside configured routes."""
    for identity in inventory.identities:
        config = dict(repository_routes.get(identity.repo.name, {}))
        allowed = {identity.slug}
        allowed.update(str(item).lower() for item in config.get("allowed_slugs", []))
        aliases = {
            str(name).lower(): str(slug).lower()
            for name, slug in dict(config.get("short_aliases", {})).items()
        }
        try:
            beads = list(loader(identity))
        except Exception as exc:
            reason = (
                f"cannot audit GitHub refs for {identity.repo}: "
                f"{exc.__class__.__name__}: {exc}"
            )
            inventory.entries.append(
                {
                    "path": str(identity.repo),
                    "status": "reference-audit-failed",
                    "reason": reason,
                }
            )
            inventory.errors.append(reason)
            continue
        normalized: dict[tuple[str, int], Bead] = {}
        for bead in beads:
            try:
                target = github_issue_target(
                    bead.external_ref, identity.slug, allowed, aliases
                )
            except IdentityError as exc:
                reason = f"Bead {bead.id}: {exc}"
                inventory.entries.append(
                    {
                        "path": str(identity.repo),
                        "status": "reference-ineligible",
                        "bead_id": bead.id,
                        "external_ref": bead.external_ref,
                        "reason": reason,
                    }
                )
                inventory.errors.append(reason)
                continue
            if target is None:
                continue
            prior = normalized.get(target)
            if prior is not None and prior.id != bead.id:
                reason = (
                    f"Beads {prior.id} and {bead.id} both link "
                    f"GitHub issue {target[0]}#{target[1]}"
                )
                inventory.entries.append(
                    {
                        "path": str(identity.repo),
                        "status": "reference-ineligible",
                        "bead_id": bead.id,
                        "external_ref": bead.external_ref,
                        "reason": reason,
                    }
                )
                inventory.errors.append(reason)
                continue
            normalized[target] = bead
    return inventory


def resolve_repository_status(
    repo: Path | str,
    *,
    policy: dict[str, Any],
    workspace: Path | None = None,
) -> RepositoryStatus:
    """Resolve one policy-aware repository status for bounded read-only callers."""
    root = (workspace or Path.cwd()).expanduser().resolve()
    raw_backup = Path(
        str(policy.get("alias_backup_root") or ".beads-github-sync-backups")
    ).expanduser()
    backup_root = (
        raw_backup.resolve()
        if raw_backup.is_absolute()
        else (root / raw_backup).resolve()
    )
    inventory = audit_repositories(
        [repo],
        workspace=root,
        aliases=dict(policy.get("repository_aliases", {})),
        alias_backup_root=backup_root,
        exclusions=list(policy.get("exclude_repositories", [])),
    )
    entry = inventory.entries[0] if inventory.entries else {
        "status": "ineligible",
        "reason": "repository was not classified",
    }
    migration = inventory.alias_migrations[0] if inventory.alias_migrations else None
    identity = inventory.identities[0] if inventory.identities else None
    return RepositoryStatus(
        status=str(entry.get("status") or "ineligible"),
        identity=identity,
        reason=str(entry.get("reason") or ""),
        alias_migration=migration,
    )


def _atomic_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _alias_paths(
    migration: AliasMigration, backup_root: Path
) -> tuple[Path, Path, Path, Path]:
    key = hashlib.sha256(
        f"{migration.source_repo}\0{migration.canonical_repo}".encode()
    ).hexdigest()[:16]
    backup_dir = backup_root / f"{migration.source_repo.name}-{key}"
    receipt = backup_dir / "migration.json"
    original = backup_dir / "original-beads"
    staged = migration.source_repo / f".beads-redirect-stage-{key}"
    return backup_dir, receipt, original, staged


_ALIAS_RECEIPT_KEYS = {
    "schema_version",
    "phase",
    "source_repo",
    "canonical_repo",
    "canonical_beads",
    "database_id",
    "slug",
    "backup_dir",
}
_ALIAS_RECEIPT_PHASES = {
    "prepared",
    "backed_up",
    "applied",
    "rollback_prepared",
    "redirect_backed_up",
    "rolled_back",
}


def _alias_receipt_payload(
    migration: AliasMigration, backup_dir: Path, phase: str
) -> dict[str, Any]:
    return {
        "schema_version": "beads-alias-redirect/v1",
        "phase": phase,
        "source_repo": str(migration.source_repo),
        "canonical_repo": str(migration.canonical_repo),
        "canonical_beads": str(migration.canonical_beads),
        "database_id": migration.database_id,
        "slug": migration.slug,
        "backup_dir": str(backup_dir),
    }


def _validated_alias_receipt(
    migration: AliasMigration,
    backup_root: Path,
    *,
    phases: Iterable[str] = _ALIAS_RECEIPT_PHASES,
) -> dict[str, Any]:
    backup_dir, receipt_path, _, _ = _alias_paths(migration, backup_root)
    try:
        loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityError(f"invalid alias migration receipt: {receipt_path}") from exc
    if not isinstance(loaded, dict) or set(loaded) != _ALIAS_RECEIPT_KEYS:
        raise IdentityError(f"invalid alias migration receipt schema: {receipt_path}")
    phase = str(loaded.get("phase") or "")
    allowed_phases = set(phases)
    if phase not in _ALIAS_RECEIPT_PHASES or phase not in allowed_phases:
        raise IdentityError(
            f"invalid alias migration receipt phase {phase!r}: {receipt_path}"
        )
    expected = _alias_receipt_payload(migration, backup_dir, phase)
    if loaded != expected:
        raise IdentityError(f"alias migration receipt identity mismatch: {receipt_path}")
    return expected


def _nearest_existing(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _validated_redirect_target(path: Path, migration: AliasMigration) -> Path:
    redirect = path / "redirect"
    if not redirect.is_file():
        raise IdentityError(f"managed alias redirect is missing: {path}")
    target = Path(redirect.read_text(encoding="utf-8").strip())
    target = (
        target.resolve()
        if target.is_absolute()
        else (migration.source_repo / target).resolve()
    )
    if target != migration.canonical_beads:
        raise IdentityError(f"managed alias redirect target changed: {path}")
    return target


def apply_alias_redirects(
    migrations: Iterable[AliasMigration],
    *,
    backup_root: Path,
    barrier: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Losslessly replace validated clone databases with single-level redirects."""
    plans = list(migrations)
    root = backup_root.expanduser().resolve()
    prepared: list[tuple[AliasMigration, Path, Path, Path, Path]] = []
    for migration in plans:
        backup_dir, receipt, original, staged = _alias_paths(migration, root)
        if root == migration.source_repo or root.is_relative_to(migration.source_repo):
            raise SyncError(
                f"alias backup must be outside repository: {migration.source_repo}"
            )
        if _nearest_existing(root).stat().st_dev != migration.source_repo.stat().st_dev:
            raise SyncError("alias backup and repository must share a filesystem")
        if (migration.canonical_beads / "redirect").exists():
            raise IdentityError("canonical Beads owner cannot itself be a redirect")
        canonical_project_id = _beads_project_uuid(migration.canonical_beads)
        if canonical_project_id is None:
            raise IdentityError(
                "alias redirect requires a canonical Beads project_id UUID"
            )
        if _database_identity(migration.canonical_beads) != migration.database_id:
            raise IdentityError("canonical Beads identity changed before alias migration")
        if migration.source_beads.exists():
            redirect = migration.source_beads / "redirect"
            if redirect.exists():
                target = Path(redirect.read_text(encoding="utf-8").strip())
                target = (
                    target.resolve()
                    if target.is_absolute()
                    else (migration.source_repo / target).resolve()
                )
                if target != migration.canonical_beads:
                    raise IdentityError("existing alias redirect targets another database")
            elif _database_identity(migration.source_beads) != migration.database_id:
                raise IdentityError("alias Beads identity changed before migration")
        elif not (receipt.is_file() and original.is_dir()):
            raise SyncError(f"alias database disappeared before backup: {migration.source_beads}")
        else:
            _validated_alias_receipt(migration, root, phases={"backed_up"})
        prepared.append((migration, backup_dir, receipt, original, staged))

    completed: list[dict[str, Any]] = []
    completed_migrations: list[AliasMigration] = []
    try:
        for migration, backup_dir, receipt_path, original, staged in prepared:
            if receipt_path.is_file():
                receipt = _validated_alias_receipt(migration, root)
            else:
                backup_dir.mkdir(parents=True, exist_ok=False)
                receipt = _alias_receipt_payload(migration, backup_dir, "prepared")
                _atomic_json_file(receipt_path, receipt)
            installed = backup_dir / "installed-redirect"
            if receipt["phase"] == "rolled_back":
                if original.exists() or not migration.source_beads.is_dir():
                    raise IdentityError(
                        f"rolled-back alias layout is inconsistent: {migration.source_repo}"
                    )
                if staged.exists():
                    _validated_redirect_target(staged, migration)
                    if installed.exists():
                        raise IdentityError(
                            f"two saved alias redirects exist: {migration.source_repo}"
                        )
                else:
                    _validated_redirect_target(installed, migration)
                    os.replace(installed, staged)
                receipt = _alias_receipt_payload(migration, backup_dir, "prepared")
                _atomic_json_file(receipt_path, receipt)
            if not staged.exists() and not migration.source_beads.exists():
                staged.mkdir()
                (staged / "redirect").write_text(
                    f"{migration.canonical_beads}\n", encoding="utf-8"
                )
            elif not staged.exists() and not (migration.source_beads / "redirect").exists():
                staged.mkdir()
                (staged / "redirect").write_text(
                    f"{migration.canonical_beads}\n", encoding="utf-8"
                )
            if migration.source_beads.exists() and not (
                migration.source_beads / "redirect"
            ).exists():
                if original.exists():
                    raise SyncError(f"alias backup already exists: {original}")
                os.replace(migration.source_beads, original)
                receipt["phase"] = "backed_up"
                _atomic_json_file(receipt_path, receipt)
            if barrier is not None:
                barrier("backed_up")
            if not migration.source_beads.exists():
                if not staged.is_dir():
                    raise SyncError(f"missing staged redirect: {staged}")
                os.replace(staged, migration.source_beads)
            redirect_target = Path(
                (migration.source_beads / "redirect")
                .read_text(encoding="utf-8")
                .strip()
            ).resolve()
            if redirect_target != migration.canonical_beads:
                raise IdentityError("installed alias redirect failed verification")
            receipt["phase"] = "applied"
            _atomic_json_file(receipt_path, receipt)
            completed.append(receipt)
            completed_migrations.append(migration)
    except Exception:
        rollback_alias_redirects(completed_migrations, backup_root=root)
        raise
    return completed


def rollback_alias_redirects(
    migrations: Iterable[AliasMigration],
    *,
    backup_root: Path,
    barrier: Callable[[str], None] | None = None,
) -> None:
    root = backup_root.expanduser().resolve()
    for migration in reversed(list(migrations)):
        backup_dir, _, original, _ = _alias_paths(migration, root)
        receipt = _validated_alias_receipt(
            migration,
            root,
            phases={
                "applied",
                "rollback_prepared",
                "redirect_backed_up",
                "rolled_back",
            },
        )
        source_beads = migration.source_beads
        installed = backup_dir / "installed-redirect"
        if receipt["phase"] == "rolled_back":
            if (
                not source_beads.is_dir()
                or (source_beads / "redirect").exists()
                or original.exists()
                or not installed.is_dir()
            ):
                raise IdentityError(
                    f"rolled-back alias layout is inconsistent: {migration.source_repo}"
                )
            if _database_identity(source_beads) != migration.database_id:
                raise IdentityError("restored alias Beads identity changed")
            _validated_redirect_target(installed, migration)
            continue
        if source_beads.exists():
            if not (source_beads / "redirect").exists():
                if original.exists() or not installed.is_dir():
                    raise IdentityError(
                        f"alias rollback layout is inconsistent: {migration.source_repo}"
                    )
                if _database_identity(source_beads) != migration.database_id:
                    raise IdentityError("restored alias Beads identity changed")
                _validated_redirect_target(installed, migration)
                _atomic_json_file(
                    backup_dir / "migration.json",
                    _alias_receipt_payload(
                        migration, backup_dir, "rolled_back"
                    ),
                )
                if barrier is not None:
                    barrier("rolled_back")
                continue
            _validated_redirect_target(source_beads, migration)
            if installed.exists():
                raise IdentityError(
                    f"two live alias redirects exist: {migration.source_repo}"
                )
            if not original.is_dir():
                raise SyncError(f"alias rollback backup is missing: {original}")
            _atomic_json_file(
                backup_dir / "migration.json",
                _alias_receipt_payload(
                    migration, backup_dir, "rollback_prepared"
                ),
            )
            if barrier is not None:
                barrier("rollback_prepared")
            os.replace(source_beads, installed)
            if barrier is not None:
                barrier("redirect_moved")
        if not installed.is_dir() or not original.is_dir():
            raise IdentityError(
                f"alias rollback recovery layout is inconsistent: {migration.source_repo}"
            )
        _validated_redirect_target(installed, migration)
        _atomic_json_file(
            backup_dir / "migration.json",
            _alias_receipt_payload(
                migration, backup_dir, "redirect_backed_up"
            ),
        )
        if barrier is not None:
            barrier("redirect_backed_up")
        os.replace(original, source_beads)
        if barrier is not None:
            barrier("original_restored")
        _atomic_json_file(
            backup_dir / "migration.json",
            _alias_receipt_payload(migration, backup_dir, "rolled_back"),
        )
        if barrier is not None:
            barrier("rolled_back")


def _mutex_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _STATE_MUTEXES_GUARD:
        return _STATE_MUTEXES.setdefault(key, threading.RLock())


class RepositoryLock:
    def __init__(self, path: Path):
        self.path = path
        self._file = None

    def acquire(self, *, blocking: bool = True) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+")
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(self._file.fileno(), flags)
        except BlockingIOError as exc:
            self._file.close()
            self._file = None
            raise LockBusy(f"reconcile already running for {self.path.parent.name}") from exc

    def release(self) -> None:
        if self._file is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()


class StateStore:
    def __init__(self, path: Path, identity: RepositoryIdentity, *, create: bool = True):
        self.path = path
        self.identity = identity
        self.guard_path = path.with_name("state.lock")
        if create and not self.path.exists():
            self.write(self.initial())

    def initial(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA,
            "identity": {
                "slug": self.identity.slug,
                "database_id": self.identity.database_id,
                "git_common_dir": str(self.identity.git_common_dir),
            },
            "enrolled": False,
            "executables": {},
            "github_cursor": None,
            "github_cursors": {},
            "local_cursor": None,
            "pending": [],
            "pending_since": {},
            "pending_generation": {},
            "run_generation": 0,
            "inflight": None,
            "link_map": {},
            "bead_links": {},
            "reservations": {},
            "link_index_seeded": False,
            "link_index_version": None,
            "last_success": None,
            "last_error": "",
        }

    @contextlib.contextmanager
    def _guard(self):
        with _mutex_for(self.guard_path):
            self.guard_path.parent.mkdir(parents=True, exist_ok=True)
            with self.guard_path.open("a+") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.initial()
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncError(f"invalid sync state {self.path}: {exc}") from exc
        expected = {"slug": self.identity.slug, "database_id": self.identity.database_id}
        actual = state.get("identity", {})
        if any(actual.get(key) != value for key, value in expected.items()):
            raise IdentityError(f"state identity does not match repository: {self.path}")
        if state.get("schema_version") != STATE_SCHEMA:
            raise SyncError(f"unsupported sync state schema: {state.get('schema_version')!r}")
        return state

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.initial()
        with self._guard():
            return self._read_unlocked()

    def _write_unlocked(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=self.path.parent)
        temporary = Path(raw)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def write(self, state: dict[str, Any]) -> None:
        with self._guard():
            self._write_unlocked(state)

    def restore_snapshot(self, existed: bool, payload: bytes) -> None:
        """Atomically restore enrollment state while holding the state guard."""
        with self._guard():
            if not existed:
                self.path.unlink(missing_ok=True)
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, raw = tempfile.mkstemp(
                prefix=".state-restore-", suffix=".json", dir=self.path.parent
            )
            temporary = Path(raw)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)

    def mutate(self, update: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        with self._guard():
            state = self._read_unlocked()
            update(state)
            self._write_unlocked(state)
            return state

    def enqueue(self, bead_ids: Iterable[str], at: str) -> dict[str, Any]:
        ids = sorted({str(item) for item in bead_ids if str(item)})

        def update(state):
            pending = set(state.get("pending", []))
            pending.update(ids)
            state["pending"] = sorted(pending)
            pending_since = state.setdefault("pending_since", {})
            generations = state.setdefault("pending_generation", {})
            for bead_id in ids:
                pending_since.setdefault(bead_id, at)
                generations[bead_id] = int(generations.get(bead_id, 0)) + 1

        return self.mutate(update)

    def set_enrolled(
        self,
        enrolled: bool,
        executables: dict[str, dict[str, str]] | None = None,
        hook_receipt: dict[str, Any] | None = None,
    ) -> None:
        def update(state):
            state["enrolled"] = bool(enrolled)
            if executables is not None:
                state["executables"] = executables
            if hook_receipt is not None:
                state["hook_receipt"] = hook_receipt

        self.mutate(update)

    @staticmethod
    def _require_lease(state: dict[str, Any], lease: str, generation: int) -> dict[str, Any]:
        inflight = state.get("inflight")
        if not isinstance(inflight, dict) or (
            inflight.get("lease"), inflight.get("generation")
        ) != (lease, generation):
            raise LeaseLost(f"run lease {lease}/{generation} is no longer current")
        return inflight

    def begin_run(self, started_at: str) -> dict[str, Any]:
        lease = uuid.uuid4().hex
        result: dict[str, Any] = {}

        def update(state):
            previous = state.get("inflight") or {}
            pending = set(state.get("pending", []))
            pending.update(previous.get("bead_ids", []))
            state["pending"] = sorted(pending)
            generation = int(state.get("run_generation", 0)) + 1
            state["run_generation"] = generation
            inflight = {
                "lease": lease,
                "generation": generation,
                "started_at": started_at,
                "recovery_started_at": previous.get("started_at"),
                "github_numbers": [],
                "bead_ids": [],
                "acked_github": list(previous.get("acked_github", [])),
                "acked_beads": list(previous.get("acked_beads", [])),
                "github_pages": list(previous.get("github_pages", [])),
                "github_next_page": previous.get("github_next_page"),
                "pending_generation": dict(state.get("pending_generation", {})),
            }
            state["inflight"] = inflight
            result.update(
                lease=lease,
                generation=generation,
                state=json.loads(json.dumps(state)),
            )

        self.mutate(update)
        return result

    def checkpoint_github_page(
        self,
        lease: str,
        generation: int,
        next_url: str,
        issues: Iterable[GithubIssue],
    ) -> None:
        def update(state):
            inflight = self._require_lease(state, lease, generation)
            inflight.setdefault("github_pages", []).extend(asdict(item) for item in issues)
            inflight["github_next_page"] = next_url

        self.mutate(update)

    def set_run_work(
        self,
        lease: str,
        generation: int,
        github_numbers: Iterable[int],
        bead_ids: Iterable[str],
    ) -> None:
        def update(state):
            inflight = self._require_lease(state, lease, generation)
            inflight["github_numbers"] = sorted(set(github_numbers))
            inflight["bead_ids"] = sorted(set(bead_ids))

        self.mutate(update)

    def ack_run(
        self, lease: str, generation: int, kind: str, item: str | int
    ) -> None:
        if kind not in {"github", "beads"}:
            raise ValueError(f"unknown ack kind: {kind}")

        def update(state):
            inflight = self._require_lease(state, lease, generation)
            key = f"acked_{kind}"
            acknowledged = list(inflight.get(key, []))
            if item not in acknowledged:
                acknowledged.append(item)
            inflight[key] = acknowledged

        self.mutate(update)

    def reserve_link(
        self,
        lease: str,
        generation: int,
        url: str,
        *,
        direction: str,
        bead_id: str | None,
        desired_state: str,
    ) -> None:
        def update(state):
            self._require_lease(state, lease, generation)
            reservation = state.setdefault("reservations", {}).setdefault(
                url,
                {
                    "direction": direction,
                    "desired_state": desired_state,
                    "bead_id": bead_id,
                },
            )
            if reservation.get("direction") != direction:
                raise IdentityError(f"conflicting link reservation for {url}")
            if bead_id:
                existing = reservation.get("bead_id")
                if existing and existing != bead_id:
                    raise IdentityError(f"conflicting Bead reservation for {url}")
                reservation["bead_id"] = bead_id
                mapped = state.setdefault("link_map", {}).get(url)
                if mapped and mapped != bead_id:
                    raise IdentityError(f"conflicting durable link for {url}")
                state["link_map"][url] = bead_id
                prior_url = state.setdefault("bead_links", {}).get(bead_id)
                if prior_url and prior_url != url:
                    raise IdentityError(f"conflicting durable GitHub link for {bead_id}")
                state["bead_links"][bead_id] = url

        self.mutate(update)

    def bind_reserved_link(
        self, lease: str, generation: int, url: str, bead_id: str
    ) -> None:
        def update(state):
            self._require_lease(state, lease, generation)
            reservation = state.setdefault("reservations", {}).get(url)
            if not reservation:
                raise SyncError(f"missing link reservation for {url}")
            existing = reservation.get("bead_id")
            if existing and existing != bead_id:
                raise IdentityError(f"conflicting Bead reservation for {url}")
            mapped = state.setdefault("link_map", {}).get(url)
            if mapped and mapped != bead_id:
                raise IdentityError(f"conflicting durable link for {url}")
            reservation["bead_id"] = bead_id
            state["link_map"][url] = bead_id
            prior_url = state.setdefault("bead_links", {}).get(bead_id)
            if prior_url and prior_url != url:
                raise IdentityError(f"conflicting durable GitHub link for {bead_id}")
            state["bead_links"][bead_id] = url

        self.mutate(update)

    def complete_reservation(
        self, lease: str, generation: int, url: str, bead_id: str
    ) -> None:
        def update(state):
            self._require_lease(state, lease, generation)
            mapped = state.setdefault("link_map", {}).get(url)
            if mapped != bead_id:
                raise IdentityError(f"durable link verification failed for {url}")
            state.setdefault("reservations", {}).pop(url, None)

        self.mutate(update)

    def seed_link_index(
        self,
        lease: str,
        generation: int,
        links: dict[str, str],
    ) -> None:
        def update(state):
            self._require_lease(state, lease, generation)
            link_map = state.setdefault("link_map", {})
            bead_links = state.setdefault("bead_links", {})
            for url, bead_id in links.items():
                prior_bead = link_map.get(url)
                if prior_bead and prior_bead != bead_id:
                    raise IdentityError(
                        f"multiple Beads rows link GitHub issue {url}: "
                        f"{prior_bead}, {bead_id}"
                    )
                prior_url = bead_links.get(bead_id)
                if prior_url and prior_url != url:
                    raise IdentityError(
                        f"Bead {bead_id} links multiple GitHub issues: "
                        f"{prior_url}, {url}"
                    )
                link_map[url] = bead_id
                bead_links[bead_id] = url
            state["link_index_seeded"] = True

        self.mutate(update)

    def replace_link_index(
        self,
        lease: str,
        generation: int,
        links: dict[str, str],
    ) -> None:
        """Atomically replace a legacy link index with canonical GitHub URLs."""
        def update(state):
            self._require_lease(state, lease, generation)
            reverse: dict[str, str] = {}
            for url, bead_id in links.items():
                prior_url = reverse.get(bead_id)
                if prior_url and prior_url != url:
                    raise IdentityError(
                        f"Bead {bead_id} links multiple GitHub issues: "
                        f"{prior_url}, {url}"
                    )
                reverse[bead_id] = url
            state["link_map"] = dict(links)
            state["bead_links"] = reverse
            state["link_index_seeded"] = True
            state["link_index_version"] = LINK_INDEX_VERSION

        self.mutate(update)

    def finalize_run(
        self,
        lease: str,
        generation: int,
        cursor: str,
        processed: set[str],
        github_cursors: dict[str, str] | None = None,
    ) -> None:
        def update(state):
            inflight = self._require_lease(state, lease, generation)
            snapshot = inflight.get("pending_generation", {})
            pending = set(state.get("pending", []))
            current_generations = state.setdefault("pending_generation", {})
            for bead_id in processed:
                if current_generations.get(bead_id) == snapshot.get(bead_id):
                    pending.discard(bead_id)
                    state.get("pending_since", {}).pop(bead_id, None)
                    current_generations.pop(bead_id, None)
            state["pending"] = sorted(pending)
            state["github_cursor"] = cursor
            if github_cursors is not None:
                state["github_cursors"] = dict(github_cursors)
            state["local_cursor"] = cursor
            state["inflight"] = None
            state["last_success"] = cursor
            state["last_error"] = ""

        self.mutate(update)

    def record_error(
        self,
        exc: BaseException,
        lease: str | None = None,
        generation: int | None = None,
    ) -> None:
        def update(state):
            if lease is not None and generation is not None:
                self._require_lease(state, lease, generation)
            state["last_error"] = f"{exc.__class__.__name__}: {exc}"

        self.mutate(update)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _overlap(value: str | None, seconds: int) -> str | None:
    return _format_time(_parse_time(value) - timedelta(seconds=seconds)) if value else None


def marker_for(slug: str, bead_id: str) -> str:
    project = urllib.parse.quote(slug.lower(), safe="")
    bead = urllib.parse.quote(str(bead_id), safe="")
    return f"<!-- beads-github-sync:v1 project={project} bead={bead} -->"


def github_issue_number(reference: str, slug: str) -> int | None:
    value = str(reference or "").strip()
    patterns = (
        rf"https://github\.com/{re.escape(slug)}/issues/(\d+)/?",
        r"gh-(\d+)",
        rf"{re.escape(slug)}#(\d+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, value, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def github_issue_target(
    reference: str,
    default_slug: str,
    allowed_slugs: Iterable[str],
    aliases: dict[str, str] | None = None,
) -> tuple[str, int] | None:
    """Resolve a GitHub-shaped reference or reject an unconfigured route."""
    value = str(reference or "").strip()
    if not value:
        return None
    allowed = {str(item).lower() for item in allowed_slugs}
    route_aliases = {str(key).lower(): str(item).lower() for key, item in (aliases or {}).items()}
    slug: str | None = None
    number: int | None = None
    match = re.fullmatch(
        r"https://github\.com/([^/\s]+/[^/\s]+)/issues/(\d+)/?", value, re.IGNORECASE
    )
    if match:
        slug, number = match.group(1).lower(), int(match.group(2))
    else:
        match = re.fullmatch(r"([^/#\s]+/[^#\s]+)#(\d+)", value, re.IGNORECASE)
        if match:
            slug, number = match.group(1).lower(), int(match.group(2))
        else:
            match = re.fullmatch(r"gh-(\d+)", value, re.IGNORECASE)
            if match:
                slug, number = default_slug.lower(), int(match.group(1))
            else:
                match = re.fullmatch(r"([A-Za-z0-9_.-]+)#(\d+)", value)
                if match:
                    alias = match.group(1).lower()
                    if alias not in route_aliases:
                        raise IdentityError(f"unknown GitHub route alias: {alias}")
                    slug, number = route_aliases[alias], int(match.group(2))
    if slug is None or number is None:
        return None
    if slug not in allowed:
        raise IdentityError(f"GitHub reference uses unconfigured slug {slug}: {value}")
    return slug, number


class Coordinator:
    def __init__(
        self,
        identity: RepositoryIdentity,
        store: StateStore,
        beads: BeadsPort,
        github: GithubPort | dict[str, GithubPort],
        *,
        route_aliases: dict[str, str] | None = None,
        now: Callable[[], str] | None = None,
        dry_run: bool = False,
        overlap_seconds: int = DEFAULT_OVERLAP_SECONDS,
    ):
        self.identity = identity
        self.store = store
        self.beads = beads
        if isinstance(github, dict):
            self.github_clients = {
                str(slug).lower(): client for slug, client in github.items()
            }
        else:
            self.github_clients = {identity.slug: github}
        if identity.slug not in self.github_clients:
            raise IdentityError(f"missing default GitHub client for {identity.slug}")
        self.github = self.github_clients[identity.slug]
        self.route_aliases = {
            str(name).lower(): str(slug).lower()
            for name, slug in (route_aliases or {}).items()
        }
        unknown_aliases = set(self.route_aliases.values()) - set(self.github_clients)
        if unknown_aliases:
            raise IdentityError(
                f"route aliases target unconfigured slugs: {sorted(unknown_aliases)}"
            )
        self.now = now or (lambda: _format_time(datetime.now(timezone.utc)))
        self.dry_run = dry_run
        self.overlap_seconds = overlap_seconds

    def _target(self, reference: str) -> tuple[str, int] | None:
        return github_issue_target(
            reference,
            self.identity.slug,
            self.github_clients,
            self.route_aliases,
        )

    def _remote_client(self, remote: GithubIssue) -> GithubPort:
        target = self._target(remote.url)
        if target is None:
            raise IdentityError(f"GitHub issue has no routable URL: {remote.url}")
        return self.github_clients[target[0]]

    def _candidate(self, bead: Bead, local_cursor: str | None, pending: set[str]) -> bool:
        if bead.id in pending or bead.status != "closed":
            return True
        return bool(local_cursor and _parse_time(bead.updated_at) > _parse_time(local_cursor))

    def _links_outside_the_candidate_window(
        self, wanted: set[str]
    ) -> dict[str, Bead]:
        """Записи с этими зеркалами, найденные по всей базе, а не по окну."""
        found: dict[str, Bead] = {}
        for bead in self.beads.list_linked():
            try:
                target = self._target(bead.external_ref)
            except IdentityError:
                continue
            if target is None:
                continue
            url = f"https://github.com/{target[0]}/issues/{target[1]}"
            if url not in wanted:
                continue
            existing = found.get(url)
            if existing is not None and existing.id != bead.id:
                # Нарушение «одна запись — одно зеркало» уже лежит в базе.
                # Отказ остановил бы синхронизацию целого репозитория, поэтому
                # выбор делается устойчиво и расхождение называется вслух.
                print(
                    f"{target[0]}#{target[1]} is linked by several Beads rows "
                    f"({existing.id}, {bead.id}); using {min(existing.id, bead.id)}",
                    file=sys.stderr,
                )
                if bead.id > existing.id:
                    continue
            found[url] = bead
        return found

    def _ensure_remote_state(self, bead: Bead, remote: GithubIssue, *, apply: bool) -> int:
        desired = "closed" if bead.status == "closed" else "open"
        if remote.state == desired:
            return 0
        if apply:
            updated = self._remote_client(remote).patch_state(remote.number, desired)
            if updated.number != remote.number or updated.state != desired:
                raise SyncError(f"GitHub state verification failed for {remote.url}")
        return 1

    def _sync_github_issue(
        self,
        remote: GithubIssue,
        *,
        apply: bool,
        run: dict[str, Any] | None,
        durable_links: dict[str, str],
        reservations: dict[str, dict[str, Any]],
        external_index: dict[str, Bead],
        candidates: dict[str, Bead],
    ) -> int:
        mapped_id = durable_links.get(remote.url)
        local = candidates.get(mapped_id) if mapped_id else None
        if local is None:
            local = external_index.get(remote.url)
        if local is None and mapped_id:
            local = self.beads.get(mapped_id)
        reservation = reservations.get(remote.url)
        if local is not None and reservation and reservation.get("direction") == "inbound":
            if apply:
                self.store.bind_reserved_link(
                    run["lease"], run["generation"], remote.url, local.id
                )
                desired = str(reservation.get("desired_state") or remote.state)
                if local.status != desired:
                    self.beads.set_status(local.id, desired)
                    local = self.beads.get(local.id)
                self.store.complete_reservation(
                    run["lease"], run["generation"], remote.url, local.id
                )
                durable_links[remote.url] = local.id
                reservations.pop(remote.url, None)
        if local is not None:
            return self._ensure_remote_state(local, remote, apply=apply)
        if apply:
            self.store.reserve_link(
                run["lease"],
                run["generation"],
                remote.url,
                direction="inbound",
                bead_id=None,
                desired_state=remote.state,
            )
            imported = self.beads.create_import(remote)
            self.store.bind_reserved_link(
                run["lease"], run["generation"], remote.url, imported.id
            )
            if imported.status != remote.state:
                self.beads.set_status(imported.id, remote.state)
            verified = self.beads.get(imported.id)
            if verified is None or verified.id != imported.id:
                raise SyncError(f"Beads import verification failed for {remote.url}")
            if verified.status != remote.state:
                raise SyncError(f"Beads import state verification failed for {remote.url}")
            self.store.complete_reservation(
                run["lease"], run["generation"], remote.url, imported.id
            )
            durable_links[remote.url] = imported.id
        return 1

    def _adopt_link(
        self,
        bead: Bead,
        remote: GithubIssue,
        run: dict[str, Any],
        durable_links: dict[str, str],
        durable_bead_links: dict[str, str],
    ) -> Bead:
        self.store.reserve_link(
            run["lease"],
            run["generation"],
            remote.url,
            direction="outbound",
            bead_id=bead.id,
            desired_state="closed" if bead.status == "closed" else "open",
        )
        existing_target = self._target(bead.external_ref)
        remote_target = self._target(remote.url)
        if existing_target is not None and existing_target != remote_target:
            raise IdentityError(f"Bead {bead.id} already links another GitHub issue")
        if not bead.external_ref:
            self.beads.set_external_ref(bead.id, remote.url)
        verified = self.beads.get(bead.id)
        if not verified.external_ref:
            raise SyncError(f"Beads link verification failed for {bead.id}")
        self.store.complete_reservation(
            run["lease"], run["generation"], remote.url, bead.id
        )
        durable_links[remote.url] = bead.id
        durable_bead_links[bead.id] = remote.url
        return verified

    def _sync_bead(
        self,
        bead: Bead,
        adopted: GithubIssue | None,
        *,
        apply: bool,
        run: dict[str, Any] | None,
        durable_links: dict[str, str],
        durable_bead_links: dict[str, str],
        remote_index: dict[tuple[str, int], GithubIssue],
    ) -> int:
        target = self._target(bead.external_ref)
        if target is not None:
            remote = remote_index.get(target)
            if remote is None:
                remote = self.github_clients[target[0]].get(target[1])
                remote_index[target] = remote
            return self._ensure_remote_state(bead, remote, apply=apply)
        if re.fullmatch(
            r"(?:duplicate-of:.+|pr-\d+)", bead.external_ref.strip(), re.IGNORECASE
        ):
            return 0
        durable_url = durable_bead_links.get(bead.id)
        if durable_url:
            durable_target = self._target(durable_url)
            if durable_target is None:
                raise IdentityError(f"invalid durable GitHub link for {bead.id}")
            remote = remote_index.get(durable_target)
            if remote is None:
                remote = self.github_clients[durable_target[0]].get(durable_target[1])
                remote_index[durable_target] = remote
            return self._ensure_remote_state(bead, remote, apply=apply)
        marker = marker_for(self.identity.slug, bead.id)
        remote = adopted
        if remote is None:
            if not apply:
                return 1
            remote = self.github.create(bead, marker)
        if apply:
            verified = self._adopt_link(
                bead, remote, run, durable_links, durable_bead_links
            )
            self._ensure_remote_state(verified, remote, apply=True)
        return 1

    def _seed_link_index(
        self, state: dict[str, Any], run: dict[str, Any] | None
    ) -> None:
        if (
            state.get("link_index_seeded")
            and state.get("link_index_version") == LINK_INDEX_VERSION
        ):
            return
        seeded_links: dict[str, str] = {}
        seeded_beads: dict[str, str] = {}
        for bead in self.beads.list_linked():
            target = self._target(bead.external_ref)
            if target is None:
                continue
            url = f"https://github.com/{target[0]}/issues/{target[1]}"
            prior_bead = seeded_links.get(url)
            if prior_bead and prior_bead != bead.id:
                raise IdentityError(
                    f"multiple Beads rows link GitHub issue {url}: "
                    f"{prior_bead}, {bead.id}"
                )
            prior_url = seeded_beads.get(bead.id)
            if prior_url and prior_url != url:
                raise IdentityError(
                    f"Bead {bead.id} links multiple GitHub issues: "
                    f"{prior_url}, {url}"
                )
            seeded_links[url] = bead.id
            seeded_beads[bead.id] = url
        if not self.dry_run:
            self.store.replace_link_index(
                run["lease"], run["generation"], seeded_links
            )
        state["link_map"] = dict(seeded_links)
        state["bead_links"] = dict(seeded_beads)
        state["link_index_seeded"] = True
        state["link_index_version"] = LINK_INDEX_VERSION

    def run(
        self, trigger_ids: Iterable[str] = (), *, full_reconcile: bool = False
    ) -> dict[str, int]:
        started_at = self.now()
        trigger = sorted({str(item) for item in trigger_ids if str(item)})
        if not self.dry_run and trigger:
            self.store.enqueue(trigger, started_at)
        lock = RepositoryLock(self.identity.lock_file)
        lock.acquire(blocking=False)
        try:
            run = None if self.dry_run else self.store.begin_run(started_at)
            state = self.store.read() if self.dry_run else run["state"]
            pending = set(state.get("pending", [])) | set(trigger)
            inflight = state.get("inflight") or {}
            pending.update(inflight.get("bead_ids", []))
            try:
                self._seed_link_index(state, run)
            except BaseException as exc:
                if not self.dry_run:
                    try:
                        self.store.record_error(
                            exc, run["lease"], run["generation"]
                        )
                    except LeaseLost:
                        pass
                raise
            cursor_map = dict(state.get("github_cursors", {}))
            if self.identity.slug not in cursor_map and state.get("github_cursor"):
                cursor_map[self.identity.slug] = state["github_cursor"]
            local_since = state.get("local_cursor")
            full_scan = full_reconcile or local_since is None or "*" in pending
            try:
                recovered_pages = [
                    GithubIssue(**item) for item in inflight.get("github_pages", [])
                ]
                next_page = inflight.get("github_next_page")
                checkpoint = None
                if not self.dry_run:
                    checkpoint = lambda url, page: self.store.checkpoint_github_page(
                        run["lease"], run["generation"], url, page
                    )
                discovered: list[GithubIssue] = []
                for slug, client in self.github_clients.items():
                    github_since = _overlap(
                        cursor_map.get(slug), self.overlap_seconds
                    )
                    if slug == self.identity.slug and recovered_pages and next_page == "":
                        routed = recovered_pages
                    else:
                        routed = client.discover(
                            github_since,
                            start_url=(
                                next_page
                                if slug == self.identity.slug and recovered_pages
                                else None
                            ),
                            page_checkpoint=(
                                checkpoint if slug == self.identity.slug else None
                            ),
                        )
                        if slug == self.identity.slug:
                            routed = recovered_pages + routed
                    if cursor_map.get(slug) is None:
                        routed = [item for item in routed if item.state == "open"]
                    discovered.extend(routed)
                acknowledged_github = {
                    str(item) for item in inflight.get("acked_github", [])
                }
                discovered = [
                    item
                    for item in discovered
                    if (
                        f"{self._target(item.url)[0]}#{item.number}"
                        not in acknowledged_github
                        and not (
                            self._target(item.url)[0] == self.identity.slug
                            and str(item.number) in acknowledged_github
                        )
                    )
                ]
                candidate_since = local_since or _overlap(
                    started_at, self.overlap_seconds
                )
                # A queued id issued by a different database can never resolve here,
                # and `bd show` on it fails the whole run. A foreign id replicated
                # into other repositories' queues can block every later run:
                # a run that aborts never clears the item that poisoned it.
                # Foreign ids are dropped instead, and joined to `processed` below so
                # the queue actually loses them.
                foreign_pending = {
                    bead_id
                    for bead_id in pending - {"*"}
                    if not bead_belongs_to_prefix(bead_id, self.identity.issue_prefix)
                }
                if foreign_pending:
                    print(
                        f"{self.identity.slug}: dropping "
                        f"{len(foreign_pending)} queued id(s) issued by another "
                        f"database: {', '.join(sorted(foreign_pending))}",
                        file=sys.stderr,
                    )
                raw_candidates = self.beads.list_candidates(
                    candidate_since, (pending - {"*"}) - foreign_pending, full_scan
                )
                # Ids the database itself could not resolve — a repository that
                # declares no prefix has nothing for the check above to compare
                # against, so this is the layer that unblocks it. `getattr` keeps
                # test doubles and any other Beads implementation working unchanged.
                unresolved = set(getattr(self.beads, "unresolved_pending", ()) or ())
                if unresolved:
                    print(
                        f"{self.identity.slug}: dropping "
                        f"{len(unresolved)} queued id(s) its Beads database cannot "
                        f"resolve: {', '.join(sorted(unresolved))}",
                        file=sys.stderr,
                    )
                    foreign_pending |= unresolved
                candidates = {
                    item.id: item
                    for item in raw_candidates
                    if self._candidate(item, candidate_since, pending)
                    and item.id not in set(inflight.get("acked_beads", []))
                }
                external_index: dict[str, Bead] = {}
                for slug in self.github_clients:
                    external_index.update(
                        self.beads.find_by_external_refs(
                            (
                                item.url
                                for item in discovered
                                if self._target(item.url)[0] == slug
                            ),
                            slug,
                            candidates.values(),
                            default_slug=self.identity.slug,
                        )
                    )
                # Кандидаты — окно, а не база. Закрытая запись выпадает из них,
                # как только её `updated_at` уходит за локальный курсор, а та же
                # Issue ещё возвращается окном перекрытия на стороне GitHub: у
                # GitHub перекрытие есть, у Beads его нет. Совпадение по одним
                # кандидатам тогда не находится, и Issue с уже существующим
                # зеркалом может импортироваться второй раз. Поэтому
                # ссылки, не покрытые окном, ищутся по всей базе: один вызов
                # `list_linked` на прогон дешевле дубля, который потом
                # схлопывают руками.
                unmatched = {
                    item.url for item in discovered if item.url not in external_index
                }
                if unmatched:
                    external_index.update(
                        self._links_outside_the_candidate_window(unmatched)
                    )
                remote_index = {
                    self._target(item.url): item for item in discovered
                }
                for candidate in candidates.values():
                    candidate_target = self._target(candidate.external_ref)
                    if candidate_target is None:
                        continue
                    remote = remote_index.get(candidate_target)
                    if remote is not None:
                        external_index[remote.url] = candidate
                marker_since_values = [
                    state.get("pending_since", {}).get(item.id)
                    for item in candidates.values()
                    if state.get("pending_since", {}).get(item.id)
                ]
                durable_attempt = inflight.get("recovery_started_at") or started_at
                marker_since = min(marker_since_values + [durable_attempt])
                marker_since = _overlap(marker_since, self.overlap_seconds)
                unlinked_markers = {}
                for item in candidates.values():
                    if self._target(item.external_ref) is not None:
                        continue
                    if (
                        item.id not in state.get("bead_links", {})
                        or state.get("bead_links", {}).get(item.id)
                        in state.get("reservations", {})
                    ):
                        unlinked_markers[item.id] = marker_for(
                            self.identity.slug, item.id
                        )
                adopted_by_marker = self.github.find_by_markers(
                    unlinked_markers.values(), marker_since
                ) if unlinked_markers else {}
                if not self.dry_run:
                    self.store.set_run_work(
                        run["lease"],
                        run["generation"],
                        (
                            f"{self._target(item.url)[0]}#{item.number}"
                            for item in discovered
                        ),
                        candidates,
                    )

                durable_links = dict(state.get("link_map", {}))
                durable_bead_links = dict(state.get("bead_links", {}))
                reservations = dict(state.get("reservations", {}))
                if not self.dry_run:
                    for bead_id, marker in unlinked_markers.items():
                        adopted = adopted_by_marker.get(marker)
                        if adopted is None:
                            continue
                        candidates[bead_id] = self._adopt_link(
                            candidates[bead_id],
                            adopted,
                            run,
                            durable_links,
                            durable_bead_links,
                        )
                        reservations.pop(adopted.url, None)

                planned = 0
                handled_bead_ids: set[str] = set()
                for remote in discovered:
                    if remote.is_pull_request:
                        continue
                    linked = external_index.get(remote.url)
                    if linked is None:
                        linked_id = durable_links.get(remote.url)
                        linked = candidates.get(linked_id) if linked_id else None
                    planned += self._sync_github_issue(
                        remote,
                        apply=not self.dry_run,
                        run=run,
                        durable_links=durable_links,
                        reservations=reservations,
                        external_index=external_index,
                        candidates=candidates,
                    )
                    if linked is not None:
                        handled_bead_ids.add(linked.id)
                    if not self.dry_run:
                        self.store.ack_run(
                            run["lease"],
                            run["generation"],
                            "github",
                            f"{self._target(remote.url)[0]}#{remote.number}",
                        )
                for bead in candidates.values():
                    if bead.id in handled_bead_ids:
                        if not self.dry_run:
                            self.store.ack_run(
                                run["lease"], run["generation"], "beads", bead.id
                            )
                        continue
                    if not self.dry_run:
                        bead = self.beads.get(bead.id)
                    marker = unlinked_markers.get(bead.id)
                    planned += self._sync_bead(
                        bead,
                        adopted_by_marker.get(marker) if marker else None,
                        apply=not self.dry_run,
                        run=run,
                        durable_links=durable_links,
                        durable_bead_links=durable_bead_links,
                        remote_index=remote_index,
                    )
                    if not self.dry_run:
                        self.store.ack_run(
                            run["lease"], run["generation"], "beads", bead.id
                        )

                if not self.dry_run:
                    # `foreign_pending` counts as processed: the decision about it is
                    # final and needs no second look, and leaving it queued would make
                    # every later run repeat the same warning forever.
                    processed = set(candidates) | foreign_pending | {"*"}
                    self.store.finalize_run(
                        run["lease"],
                        run["generation"],
                        started_at,
                        processed,
                        github_cursors={
                            slug: started_at for slug in self.github_clients
                        },
                    )
                return {"planned": planned, "github": len(discovered), "beads": len(candidates)}
            except BaseException as exc:
                if not self.dry_run:
                    try:
                        self.store.record_error(exc, run["lease"], run["generation"])
                    except LeaseLost:
                        pass
                raise
        finally:
            lock.release()


def _block(command: str) -> str:
    return f"{BEGIN_MARKER}\n{command}\n{END_MARKER}\n"


def _plan_managed_hook(path: Path, command: str) -> dict[str, Any]:
    existing = path.read_text(encoding="utf-8") if path.exists() else "#!/bin/sh\n"
    begin_count, end_count = existing.count(BEGIN_MARKER), existing.count(END_MARKER)
    if begin_count != end_count or begin_count > 1:
        raise SyncError(f"ambiguous managed marker in {path}")
    replacement = _block(command)
    if begin_count:
        pattern = re.compile(
            rf"(?m)^{re.escape(BEGIN_MARKER)}\n.*?^{re.escape(END_MARKER)}\n?",
            re.DOTALL,
        )
        updated = pattern.sub(replacement, existing)
    else:
        updated = existing
        if updated and not updated.endswith("\n"):
            updated += "\n"
        updated += ("\n" if updated.strip() else "") + replacement
    return {
        "path": path,
        "existed": path.exists(),
        "existing": existing,
        "existing_mode": path.stat().st_mode if path.exists() else None,
        "updated": updated,
        "changed": updated != existing,
    }


def _apply_managed_hook_plan(plan: dict[str, Any]) -> None:
    path = plan["path"]
    if plan["changed"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        temporary.write_text(plan["updated"], encoding="utf-8")
        temporary.chmod(0o755)
        os.replace(temporary, path)
    elif path.exists():
        path.chmod(path.stat().st_mode | 0o100)


def _restore_managed_hook_plan(plan: dict[str, Any]) -> None:
    path = plan["path"]
    if not plan["existed"]:
        path.unlink(missing_ok=True)
        return
    path.write_text(plan["existing"], encoding="utf-8")
    path.chmod(plan["existing_mode"])


def install_managed_hook(path: Path, command: str, *, dry_run: bool = False) -> bool:
    plan = _plan_managed_hook(path, command)
    if not dry_run:
        _apply_managed_hook_plan(plan)
    return bool(plan["changed"])


def _bead_from_dict(item: dict[str, Any]) -> Bead:
    return Bead(
        id=str(item["id"]),
        title=str(item.get("title") or ""),
        description=str(item.get("description") or ""),
        status=str(item.get("status") or "open"),
        updated_at=str(item.get("updated_at") or item.get("created_at") or "1970-01-01T00:00:00Z"),
        external_ref=str(item.get("external_ref") or ""),
    )


class BeadsCLI:
    def __init__(
        self,
        repo: Path,
        executable: str = "bd",
        *,
        timeout: float = BD_TIMEOUT_SECONDS,
    ):
        self.repo = repo
        self.executable = executable
        self.timeout = timeout

    def _json(self, args: list[str], *, input_text: str | None = None) -> Any:
        try:
            result = subprocess.run(
                [self.executable, "-C", str(self.repo), *args, "--json"],
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise SyncError(
                f"bd {' '.join(args)} timed out after {self.timeout:g}s for {self.repo}"
            ) from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise SyncError(detail[-1] if detail else f"bd {' '.join(args)} failed")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise SyncError(f"bd returned invalid JSON for {' '.join(args)}") from exc

    @staticmethod
    def _issue_rows(payload: Any, command: str) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and "issues" in payload:
            payload = payload["issues"]
        if not isinstance(payload, list) or any(
            not isinstance(item, dict) for item in payload
        ):
            raise SyncError(f"bd returned malformed issues response for {command}")
        return payload

    def list_candidates(
        self, since: str | None, pending_ids: Iterable[str], full_scan: bool
    ) -> list[Bead]:
        # `--all` не косметика: без него `bd list` отдаёт только незакрытые
        # записи. Полное сканирование тогда не видит закрытую каноническую
        # запись, совпадение по external_ref не находится — и Issue, у которой
        # зеркало уже есть, импортируется второй раз. Дубликат появляется
        # именно в момент закрытия задачи. Соседний `list_linked` и ветка
        # `--updated-after` ниже флаг ставят; здесь он был потерян.
        rows = (
            self._issue_rows(
                self._json(["list", "--all", "--limit=0", "--skip-labels"]), "list"
            )
            if full_scan
            else []
        )
        if since:
            rows += self._issue_rows(
                self._json(
                    ["list", "--all", f"--updated-after={since}", "--limit=0", "--skip-labels"]
                ),
                "list --updated-after",
            )
        # `bd show` fails the whole call when any one id is unknown, and the queue
        # is the one place ids arrive from outside this database. A prefix check
        # catches the common case, but a repository whose `.beads/config.yaml`
        # declares no `issue-prefix` has no prefix to check against — so the bulk
        # call is retried per id and the unresolvable ones are reported rather than
        # raised. Callers read `unresolved_pending` to clear them from the queue;
        # without that, an id nobody can fetch blocks the repository forever.
        self.unresolved_pending: set[str] = set()
        ids = sorted(set(pending_ids))
        if ids:
            try:
                rows += self._issue_rows(self._json(["show", *ids]), "show")
            except SyncError:
                for bead_id in ids:
                    try:
                        rows += self._issue_rows(
                            self._json(["show", bead_id]), "show"
                        )
                    except SyncError:
                        self.unresolved_pending.add(bead_id)
        return list({_bead_from_dict(item).id: _bead_from_dict(item) for item in rows}.values())

    def list_linked(self) -> list[Bead]:
        rows = self._issue_rows(
            self._json(["list", "--all", "--limit=0", "--skip-labels"]),
            "list --all",
        )
        return [
            bead
            for item in rows
            if (bead := _bead_from_dict(item)).external_ref
        ]

    def find_by_external_ref(
        self,
        url: str,
        candidates: Iterable[Bead] = (),
        *,
        default_slug: str | None = None,
    ) -> Bead | None:
        match = re.fullmatch(
            r"https://github\.com/([^/\s]+/[^/\s]+)/issues/(\d+)/?",
            url,
            re.IGNORECASE,
        )
        if not match:
            exact = [item for item in candidates if item.external_ref == url]
            if len(exact) > 1:
                raise IdentityError(f"multiple Beads rows have external_ref {url}")
            return exact[0] if exact else None
        found = self.find_by_external_refs(
            [url],
            match.group(1).lower(),
            candidates,
            default_slug=default_slug or match.group(1).lower(),
        )
        return found.get(url)

    def find_by_external_refs(
        self,
        urls: Iterable[str],
        slug: str,
        candidates: Iterable[Bead] = (),
        *,
        default_slug: str | None = None,
    ) -> dict[str, Bead]:
        wanted = {str(url) for url in urls}
        if not wanted:
            return {}
        result: dict[str, Bead] = {}
        origin = (default_slug or slug).lower()
        for bead in candidates:
            try:
                target = github_issue_target(
                    bead.external_ref,
                    origin,
                    {origin, slug.lower()},
                )
            except IdentityError:
                continue
            if target is None or target[0] != slug.lower():
                continue
            canonical = f"https://github.com/{target[0]}/issues/{target[1]}"
            if canonical not in wanted:
                continue
            existing = result.get(canonical)
            if existing is not None and existing.id != bead.id:
                raise IdentityError(
                    f"multiple Beads rows link GitHub issue {target[0]}#{target[1]}"
                )
            result[canonical] = bead
        return result

    def import_issue(self, issue: GithubIssue) -> Bead:
        imported = self.create_import(issue)
        if imported.status != issue.state:
            self.set_status(imported.id, issue.state)
        return self.get(imported.id)

    def create_import(self, issue: GithubIssue) -> Bead:
        payload = self._json(
            [
                "create",
                f"--title={issue.title}",
                "--body-file=-",
                "--type=task",
                f"--external-ref={issue.url}",
            ],
            input_text=issue.body,
        )
        bead_id = payload.get("id") if isinstance(payload, dict) else payload
        if not bead_id:
            raise SyncError(f"bd create did not return an id for {issue.url}")
        return self.get(str(bead_id))

    def set_status(self, bead_id: str, status: str) -> None:
        self._json(["update", bead_id, f"--status={status}"])

    def set_external_ref(self, bead_id: str, url: str) -> None:
        self._json(["update", bead_id, f"--external-ref={url}"])

    def get(self, bead_id: str) -> Bead:
        payload = self._json(["show", bead_id])
        item = payload[0] if isinstance(payload, list) else payload
        return _bead_from_dict(item)


def _github_issue(item: dict[str, Any]) -> GithubIssue:
    url = str(item.get("html_url") or "")
    match = re.fullmatch(
        r"https://github\.com/([^/\s]+/[^/\s]+)/issues/(\d+)/?",
        url,
        re.IGNORECASE,
    )
    if match:
        url = f"https://github.com/{match.group(1).lower()}/issues/{int(match.group(2))}"
    return GithubIssue(
        number=int(item["number"]),
        title=str(item.get("title") or ""),
        body=str(item.get("body") or ""),
        state=str(item.get("state") or "open"),
        updated_at=str(item.get("updated_at") or "1970-01-01T00:00:00Z"),
        url=url,
        is_pull_request="pull_request" in item,
    )


class GithubREST:
    def __init__(self, slug: str, token: str):
        self.slug = slug
        self.token = token
        self.base = f"https://api.github.com/repos/{slug}"
        self._last_discovered: list[GithubIssue] = []

    def _request(self, method: str, url: str, payload: dict[str, Any] | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "orchestration-console-beads-sync/1",
            },
        )
        try:
            response = urllib.request.urlopen(request, timeout=30)
            raw = response.read()
        except urllib.error.HTTPError as exc:
            retry_after = exc.headers.get("Retry-After")
            if exc.code in {403, 429} or retry_after:
                raise RateLimited(f"GitHub rate limited ({exc.code}, retry-after={retry_after})") from exc
            raise SyncError(f"GitHub API {method} {url}: HTTP {exc.code}") from exc
        except (OSError, TimeoutError) as exc:
            raise PartialDiscovery(f"GitHub API {method} {url}: {exc}") from exc
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) < MIN_RATE_REMAINING:
            raise RateLimited(f"GitHub rate remaining {remaining} is below {MIN_RATE_REMAINING}")
        return (json.loads(raw or b"null"), response.headers)

    def _issues(
        self,
        *,
        since: str | None,
        state: str,
        start_url: str | None = None,
        page_checkpoint: Callable[[str, list[GithubIssue]], None] | None = None,
    ) -> list[GithubIssue]:
        query = {"state": state, "per_page": "100", "sort": "updated", "direction": "asc"}
        if since:
            query["since"] = since
        url = start_url or f"{self.base}/issues?{urllib.parse.urlencode(query)}"
        found: list[GithubIssue] = []
        while url:
            payload, headers = self._request("GET", url)
            if not isinstance(payload, list):
                raise PartialDiscovery("GitHub issues page was not a list")
            page = [_github_issue(item) for item in payload if "pull_request" not in item]
            found.extend(page)
            match = re.search(r'<([^>]+)>; rel="next"', headers.get("Link", ""))
            url = match.group(1) if match else ""
            if page_checkpoint is not None:
                page_checkpoint(url, page)
        return found

    def discover(
        self,
        since: str | None,
        *,
        start_url: str | None = None,
        page_checkpoint: Callable[[str, list[GithubIssue]], None] | None = None,
    ) -> list[GithubIssue]:
        self._last_discovered = self._issues(
            since=since,
            state="all" if since else "open",
            start_url=start_url,
            page_checkpoint=page_checkpoint,
        )
        return self._last_discovered

    def get(self, number: int) -> GithubIssue:
        payload, _ = self._request("GET", f"{self.base}/issues/{number}")
        return _github_issue(payload)

    def find_by_markers(
        self, markers: Iterable[str], since: str | None
    ) -> dict[str, GithubIssue]:
        wanted = set(markers)
        matches: dict[str, list[GithubIssue]] = {marker: [] for marker in wanted}
        cached = list(self._last_discovered)
        for item in cached:
            for marker in wanted:
                if marker in item.body:
                    matches[marker].append(item)
        missing = {marker for marker, items in matches.items() if not items}
        if missing:
            for item in self._issues(since=since, state="all"):
                for marker in missing:
                    if marker in item.body and item not in matches[marker]:
                        matches[marker].append(item)
        duplicates = [marker for marker, items in matches.items() if len(items) > 1]
        if duplicates:
            raise IdentityError(f"multiple GitHub issues carry marker {duplicates[0]}")
        return {marker: items[0] for marker, items in matches.items() if items}

    def create(self, bead: Bead, marker: str) -> GithubIssue:
        body = f"{bead.description}\n\n{marker}".strip()
        payload, _ = self._request("POST", f"{self.base}/issues", {"title": bead.title, "body": body})
        return _github_issue(payload)

    def patch_state(self, number: int, state: str) -> GithubIssue:
        payload, _ = self._request("PATCH", f"{self.base}/issues/{number}", {"state": state})
        return _github_issue(payload)


def _default_config() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "github-sync.json"


def _load_policy(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"cannot load enrollment policy {path}: {exc}") from exc
    if policy.get("schema_version") != "github-sync-enrollment/v1":
        raise SyncError(f"unsupported enrollment policy: {policy.get('schema_version')!r}")
    return policy


def load_policy(path: Path | None = None) -> dict[str, Any]:
    """Load the versioned policy without mutating repository or runtime state."""
    return _load_policy((path or _default_config()).expanduser().resolve())


def discover_workspace(
    workspace: Path,
    exclusions: Iterable[str],
    *,
    timeout: float = IDENTITY_TIMEOUT_SECONDS,
) -> list[Path]:
    excluded = _exclusion_reasons(exclusions)
    found = []
    for item in sorted(workspace.iterdir()):
        if not item.is_dir() or not (item / ".beads").is_dir() or item.name.lower() in excluded:
            continue
        try:
            result = subprocess.run(
                ["git", "-C", str(item), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise IdentityError(
                f"git origin discovery timed out after {timeout:g}s for {item}"
            ) from exc
        if result.returncode:
            continue
        try:
            normalize_github_slug(result.stdout.strip())
        except IdentityError:
            continue
        found.append(item)
    return found


def _strict_reference_candidates(identity: RepositoryIdentity) -> list[Bead]:
    has_physical = any(
        (item / ".dolt").is_dir()
        for parent_name in ("embeddeddolt", "dolt")
        for item in (
            list((identity.beads_dir / parent_name).iterdir())
            if (identity.beads_dir / parent_name).is_dir()
            else []
        )
        if item.is_dir()
    )
    if not has_physical and not (identity.beads_dir / "issues.jsonl").is_file():
        return []
    state = StateStore(identity.state_file, identity, create=False).read()
    if state.get("enrolled"):
        executable = verify_pinned_executables(state)["bd"]["path"]
    else:
        executable = os.environ.get("BEADS_SYNC_BD") or shutil.which("bd")
        if not executable:
            raise SyncError("bd is unavailable for strict external-ref audit")
    return BeadsCLI(identity.repo, executable=str(executable)).list_candidates(
        state.get("local_cursor"), [], True
    )


def resolve_executables(
    overrides: dict[str, str] | None = None,
    *,
    timeout: float = VERSION_TIMEOUT_SECONDS,
) -> dict[str, dict[str, str]]:
    overrides = overrides or {}
    receipt: dict[str, dict[str, str]] = {}
    for name, version_args in (("bd", ["version"]), ("gh", ["--version"])):
        requested = overrides.get(name) or shutil.which(name)
        if not requested:
            raise SyncError(f"required executable is unavailable: {name}")
        path = Path(requested).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise SyncError(f"required executable is not runnable: {path}")
        try:
            result = subprocess.run(
                [str(path), *version_args],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise SyncError(
                f"executable version check timed out after {timeout:g}s: {path}"
            ) from exc
        if result.returncode:
            raise SyncError(f"cannot verify executable {path}")
        version = (result.stdout or result.stderr).strip().splitlines()
        receipt[name] = {
            "path": str(path),
            "version": version[0] if version else "unknown",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return receipt


def verify_pinned_executables(
    state: dict[str, Any],
    *,
    run_versions: bool = True,
    version_timeout: float = VERSION_TIMEOUT_SECONDS,
) -> dict[str, dict[str, str]]:
    receipt = state.get("executables")
    if not isinstance(receipt, dict):
        raise SyncError("repository enrollment has no executable receipt")
    for name in ("bd", "gh"):
        raw = receipt.get(name)
        path = Path(str(raw.get("path") if isinstance(raw, dict) else ""))
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise SyncError(f"pinned {name} executable is unavailable; re-enroll repository")
        expected_digest = str(raw.get("sha256") or "")
        if not expected_digest:
            raise SyncError(
                f"reenrollment_required: pinned {name} receipt has no sha256"
            )
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise SyncError(f"pinned {name} executable changed; re-enroll repository")
        expected_version = str(raw.get("version") or "")
        if not expected_version:
            raise SyncError(
                f"reenrollment_required: pinned {name} receipt has no version"
            )
        if not run_versions:
            continue
        version_args = ["version"] if name == "bd" else ["--version"]
        try:
            result = subprocess.run(
                [str(path), *version_args],
                capture_output=True,
                text=True,
                check=False,
                timeout=version_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise SyncError(
                f"pinned {name} version check timed out after {version_timeout:g}s"
            ) from exc
        lines = (result.stdout or result.stderr).strip().splitlines()
        actual_version = lines[0] if lines else "unknown"
        if result.returncode or actual_version != expected_version:
            raise SyncError(f"pinned {name} version changed; re-enroll repository")
    return receipt


def verify_launcher(shell_script: Path, python_script: Path | None = None) -> None:
    shell = shell_script.resolve()
    if not shell.is_file() or not os.access(shell, os.X_OK):
        raise SyncError(f"stable GitHub sync launcher is unavailable: {shell}")
    if python_script is not None and not python_script.resolve().is_file():
        raise SyncError(f"GitHub sync worker is unavailable: {python_script.resolve()}")


def _token(
    gh_executable: str, *, timeout: float = AUTH_TIMEOUT_SECONDS
) -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return token
    executable = str(Path(gh_executable).expanduser().resolve())
    with _AUTH_TOKEN_LOCK:
        cached = _AUTH_TOKEN_CACHE.get(executable)
        if cached:
            return cached
        try:
            result = subprocess.run(
                [executable, "auth", "token"],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise SyncError(
                f"GitHub authentication timed out after {timeout:g}s"
            ) from exc
        if result.returncode or not result.stdout.strip():
            raise SyncError("GitHub token unavailable; authenticate gh or set GITHUB_TOKEN")
        resolved = result.stdout.strip()
        _AUTH_TOKEN_CACHE[executable] = resolved
        return resolved


def reconcile(
    identity: RepositoryIdentity,
    *,
    dry_run: bool = False,
    full_reconcile: bool = True,
    route_config: dict[str, Any] | None = None,
) -> dict[str, int]:
    verify_launcher(Path(__file__).with_suffix(".sh"), Path(__file__))
    store = StateStore(identity.state_file, identity, create=False)
    state = store.read()
    if not state.get("enrolled"):
        return {"planned": 0, "github": 0, "beads": 0}
    executables = verify_pinned_executables(state)
    route_config = route_config or {}
    allowed_slugs = {identity.slug}
    allowed_slugs.update(
        normalize_github_slug(f"https://github.com/{slug}")
        for slug in route_config.get("allowed_slugs", [])
    )
    route_aliases = {
        str(name).lower(): normalize_github_slug(f"https://github.com/{slug}")
        for name, slug in dict(route_config.get("short_aliases", {})).items()
    }
    if set(route_aliases.values()) - allowed_slugs:
        raise IdentityError("short GitHub route points outside allowed_slugs")
    token = _token(executables["gh"]["path"])
    coordinator = Coordinator(
        identity,
        store,
        BeadsCLI(identity.repo, executable=executables["bd"]["path"]),
        {slug: GithubREST(slug, token) for slug in sorted(allowed_slugs)},
        route_aliases=route_aliases,
        dry_run=dry_run,
    )
    return drain_coordinator(coordinator, full_reconcile=full_reconcile)


class WorkspaceSweepStore:
    """Durable round-robin cursor for a bounded global scheduled sweep."""

    def __init__(self, workspace: Path):
        self.root = workspace.expanduser().resolve() / ".beads-github-sync"
        self.state_file = self.root / "workspace-sweep.json"
        self.state_lock = self.root / "workspace-sweep-state.lock"
        self.run_lock = self.root / "workspace-sweep-run.lock"

    @staticmethod
    def key(identity: RepositoryIdentity) -> str:
        return "\0".join(
            (
                identity.slug,
                identity.database_id,
                str(identity.git_common_dir),
            )
        )

    def _read(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {"schema_version": WORKSPACE_SWEEP_SCHEMA, "next_key": None}
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncError(f"invalid workspace sweep state {self.state_file}") from exc
        if (
            not isinstance(state, dict)
            or state.get("schema_version") != WORKSPACE_SWEEP_SCHEMA
        ):
            raise SyncError(f"unsupported workspace sweep state {self.state_file}")
        return state

    def ordered(
        self, identities: Iterable[RepositoryIdentity]
    ) -> list[RepositoryIdentity]:
        ordered = sorted(identities, key=self.key)
        if not ordered:
            return []
        next_key = self._read().get("next_key")
        start = next(
            (
                index
                for index, identity in enumerate(ordered)
                if self.key(identity) == next_key
            ),
            0,
        )
        return ordered[start:] + ordered[:start]

    def quarantine_corrupt(self) -> Path:
        quarantine = self.state_file.with_name(
            f"workspace-sweep.corrupt-{uuid.uuid4().hex}.json"
        )
        try:
            os.replace(self.state_file, quarantine)
        except OSError as exc:
            raise SyncError(
                f"cannot quarantine workspace sweep state {self.state_file}"
            ) from exc
        return quarantine

    def advance(self, next_identity: RepositoryIdentity) -> None:
        lock = RepositoryLock(self.state_lock)
        lock.acquire()
        try:
            self._read()
            _atomic_json_file(
                self.state_file,
                {
                    "schema_version": WORKSPACE_SWEEP_SCHEMA,
                    "next_key": self.key(next_identity),
                    "updated_at": _format_time(datetime.now(timezone.utc)),
                },
            )
        finally:
            lock.release()


def reconcile_repositories_fair(
    identities: Iterable[RepositoryIdentity],
    *,
    runner: Callable[[RepositoryIdentity], dict[str, int]],
    sweep_store: WorkspaceSweepStore,
    budget_seconds: float = WORKSPACE_SWEEP_BUDGET_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Run a durable bounded rotation, advancing before each repository."""
    if budget_seconds <= 0:
        raise ValueError("workspace sweep budget must be positive")
    run_lock = RepositoryLock(sweep_store.run_lock)
    try:
        run_lock.acquire(blocking=False)
    except LockBusy:
        return {
            "exit_code": 0,
            "succeeded": {},
            "failed": {},
            "deferred": [],
            "coalesced": True,
            "warnings": [],
        }
    try:
        warnings: list[str] = []
        try:
            ordered = sweep_store.ordered(identities)
        except SyncError as exc:
            quarantine = sweep_store.quarantine_corrupt()
            warnings.append(f"{exc}; quarantined as {quarantine}")
            ordered = sorted(identities, key=sweep_store.key)
        succeeded: dict[str, dict[str, int]] = {}
        failed: dict[str, str] = {}
        attempted = 0
        started = monotonic()
        for index, identity in enumerate(ordered):
            if attempted and monotonic() - started >= budget_seconds:
                break
            next_identity = ordered[(index + 1) % len(ordered)]
            sweep_store.advance(next_identity)
            attempted += 1
            try:
                succeeded[identity.slug] = runner(identity)
            except Exception as exc:
                failed[identity.slug] = f"{exc.__class__.__name__}: {exc}"
                try:
                    StateStore(
                        identity.state_file, identity, create=False
                    ).record_error(exc)
                except Exception as state_exc:
                    failed[identity.slug] += (
                        f"; state-error={state_exc.__class__.__name__}: {state_exc}"
                    )
        return {
            "exit_code": 1 if failed else 0,
            "succeeded": succeeded,
            "failed": failed,
            "deferred": [identity.slug for identity in ordered[attempted:]],
            "coalesced": False,
            "warnings": warnings,
        }
    finally:
        run_lock.release()


def reconcile_repositories(
    identities: Iterable[RepositoryIdentity],
    *,
    runner: Callable[[RepositoryIdentity], dict[str, int]],
) -> dict[str, Any]:
    """Run every repository independently and retain an aggregate failure code."""
    succeeded: dict[str, dict[str, int]] = {}
    failed: dict[str, str] = {}
    for identity in identities:
        try:
            succeeded[identity.slug] = runner(identity)
        except Exception as exc:
            failed[identity.slug] = f"{exc.__class__.__name__}: {exc}"
            try:
                StateStore(identity.state_file, identity, create=False).record_error(exc)
            except Exception as state_exc:
                failed[identity.slug] += (
                    f"; state-error={state_exc.__class__.__name__}: {state_exc}"
                )
    return {
        "exit_code": 1 if failed else 0,
        "succeeded": succeeded,
        "failed": failed,
    }


def reconcile_inventory_selection(
    inventory: RepositoryInventory,
) -> tuple[list[RepositoryIdentity], dict[str, str]]:
    """Isolate invalid ownership groups while retaining independent repos."""
    failed: dict[str, str] = {}
    for entry in inventory.entries:
        if entry.get("status") != "ineligible":
            continue
        path = str(entry.get("path") or "unknown")
        failed[path] = f"IdentityError: {entry.get('reason') or 'ineligible repository'}"

    by_slug: dict[str, set[tuple[str, str]]] = {}
    by_database: dict[str, set[tuple[str, str]]] = {}
    for identity in inventory.identities:
        by_slug.setdefault(identity.slug, set()).add(
            (identity.database_id, str(identity.git_common_dir))
        )
        by_database.setdefault(identity.database_id, set()).add(
            (identity.slug, str(identity.git_common_dir))
        )
    bad_slugs = {slug for slug, owners in by_slug.items() if len(owners) > 1}
    bad_databases = {
        database for database, targets in by_database.items() if len(targets) > 1
    }
    selected: list[RepositoryIdentity] = []
    for identity in inventory.identities:
        if identity.slug not in bad_slugs and identity.database_id not in bad_databases:
            selected.append(identity)
            continue
        reason = next(
            (
                error
                for error in inventory.errors
                if identity.slug in error or identity.database_id in error
            ),
            "ambiguous repository ownership",
        )
        key = f"{identity.slug}@{identity.git_common_dir}"
        failed[key] = f"IdentityError: {reason}"
        try:
            StateStore(
                identity.state_file, identity, create=False
            ).record_error(IdentityError(reason))
        except Exception as state_exc:
            failed[key] += (
                f"; state-error={state_exc.__class__.__name__}: {state_exc}"
            )
    for index, error in enumerate(inventory.errors):
        if not any(error in value for value in failed.values()):
            failed[f"inventory:{index}"] = f"IdentityError: {error}"
    return selected, failed


def drain_coordinator(
    coordinator: Coordinator,
    *,
    full_reconcile: bool = False,
    max_passes: int = 8,
) -> dict[str, int]:
    totals = {"planned": 0, "github": 0, "beads": 0, "passes": 0, "coalesced": 0}
    if full_reconcile and not coordinator.dry_run:
        coordinator.store.enqueue(["*"], coordinator.now())
    for pass_index in range(max_passes):
        try:
            result = coordinator.run(full_reconcile=full_reconcile and pass_index == 0)
        except LockBusy:
            totals["coalesced"] = 1
            return totals
        totals["passes"] += 1
        for key in ("planned", "github", "beads"):
            totals[key] += result[key]
        if coordinator.dry_run or not coordinator.store.read().get("pending"):
            return totals
    raise SyncError(f"pending work remains after {max_passes} bounded drain passes")


def _hook_command(shell_script: Path, repo: Path) -> str:
    log = _run_git(repo, "rev-parse", "--git-path", "github-sync.log")
    log_path = Path(log)
    if not log_path.is_absolute():
        log_path = (repo / log_path).resolve()
    command = " ".join(shlex.quote(str(item)) for item in (shell_script, "--trigger", repo))
    return f"( {command} >> {shlex.quote(str(log_path))} 2>&1 & ) >/dev/null 2>&1 || true"


def resolve_hooks_path(repo: Path) -> Path:
    """Resolve the effective Git hooks directory with a bounded Git probe."""
    hooks_raw = Path(_run_git(repo, "rev-parse", "--git-path", "hooks"))
    return (
        (repo / hooks_raw).resolve()
        if not hooks_raw.is_absolute()
        else hooks_raw.resolve()
    )


def install_hooks(
    identity: RepositoryIdentity,
    shell_script: Path,
    *,
    dry_run: bool,
    executable_overrides: dict[str, str] | None = None,
) -> int:
    return install_hooks_batch(
        [identity],
        shell_script,
        dry_run=dry_run,
        executable_overrides=executable_overrides,
    )[identity.repo]


def install_hooks_batch(
    identities: Iterable[RepositoryIdentity],
    shell_script: Path,
    *,
    dry_run: bool,
    executable_overrides: dict[str, str] | None = None,
    alias_migrations: Iterable[AliasMigration] = (),
    alias_backup_root: Path | None = None,
) -> dict[Path, int]:
    """Preflight every target, then atomically enroll each repository."""
    targets = list(identities)
    verify_launcher(shell_script, Path(__file__))
    executables = resolve_executables(executable_overrides)
    plans: list[tuple[RepositoryIdentity, list[dict[str, Any]]]] = []
    for identity in targets:
        StateStore(identity.state_file, identity, create=False).read()
        hooks = resolve_hooks_path(identity.repo)
        command = _hook_command(shell_script, identity.repo)
        plans.append(
            (
                identity,
                [
                    _plan_managed_hook(hooks / name, command)
                    for name in ("post-merge", "pre-push")
                ],
            )
        )

    changed_by_repo = {
        identity.repo: sum(bool(item["changed"]) for item in hook_plans)
        for identity, hook_plans in plans
    }
    if dry_run:
        return changed_by_repo

    migrations = list(alias_migrations)
    if migrations and alias_backup_root is None:
        raise SyncError("alias migration requires an external backup root")
    locks: list[RepositoryLock] = []
    snapshots: dict[Path, tuple[bool, bytes]] = {}
    applied_hooks: list[dict[str, Any]] = []
    alias_receipts: list[dict[str, Any]] = []
    try:
        for identity, _ in plans:
            lock = RepositoryLock(identity.lock_file)
            lock.acquire(blocking=False)
            locks.append(lock)
        for identity, _ in plans:
            existed = identity.state_file.exists()
            snapshots[identity.repo] = (
                existed,
                identity.state_file.read_bytes() if existed else b"",
            )
        if migrations:
            alias_receipts = apply_alias_redirects(
                migrations, backup_root=alias_backup_root
            )
        for identity, hook_plans in plans:
            for hook_plan in hook_plans:
                _apply_managed_hook_plan(hook_plan)
                applied_hooks.append(hook_plan)
            receipt = {
                "applied_at": _format_time(datetime.now(timezone.utc)),
                "hooks": {
                    str(item["path"]): {
                        "previous_content": item["existing"],
                        "previous_mode": item["existing_mode"],
                        "new_sha256": hashlib.sha256(
                            item["updated"].encode("utf-8")
                        ).hexdigest(),
                    }
                    for item in hook_plans
                },
            }
            StateStore(identity.state_file, identity).set_enrolled(
                True, executables, receipt
            )
    except BaseException:
        for hook_plan in reversed(applied_hooks):
            _restore_managed_hook_plan(hook_plan)
        for identity, _ in reversed(plans):
            snapshot = snapshots.get(identity.repo)
            if snapshot is not None:
                StateStore(
                    identity.state_file, identity, create=False
                ).restore_snapshot(*snapshot)
        if alias_receipts:
            rollback_alias_redirects(
                migrations, backup_root=alias_backup_root
            )
        raise
    finally:
        for lock in reversed(locks):
            lock.release()
    return changed_by_repo


def _start_worker(identity: RepositoryIdentity, python_script: Path) -> None:
    verify_launcher(python_script.with_suffix(".sh"), python_script)
    log = identity.git_common_dir / "github-sync.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as stream:
        subprocess.Popen(
            [
                sys.executable,
                str(python_script),
                "reconcile",
                "--queued-only",
                str(identity.repo),
            ],
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_default_config())
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("trigger", "reconcile", "install-hooks", "inventory", "legacy"):
        item = sub.add_parser(name)
        item.add_argument("repositories", nargs="*")
        item.add_argument("--dry-run", action="store_true")
        if name == "trigger":
            item.add_argument("--bead", action="append", default=[])
            item.add_argument("--no-start", action="store_true")
        if name == "reconcile":
            item.add_argument("--queued-only", action="store_true")
        if name == "install-hooks":
            item.add_argument("--apply-alias-redirects", action="store_true")
    return parser


def uses_fair_workspace_sweep(args: argparse.Namespace) -> bool:
    """Only the scheduled global incremental command may defer for fairness."""
    return bool(
        args.command == "reconcile"
        and args.queued_only
        and not args.repositories
        and not args.dry_run
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    policy = load_policy(args.config)
    workspace = Path(os.environ.get("CODEX_WORKSPACE", policy.get("workspace", "~/code"))).expanduser()
    exclusions = list(policy.get("exclude_repositories", []))
    if os.environ.get("GITHUB_SYNC_SKIP", "").strip():
        raise SyncError(
            "GITHUB_SYNC_SKIP is unsupported; record every exclusion with a "
            "reason in the versioned github-sync policy"
        )
    aliases = dict(policy.get("repository_aliases", {}))
    raw_backup_root = Path(
        str(policy.get("alias_backup_root") or ".beads-github-sync-backups")
    ).expanduser()
    if not raw_backup_root.is_absolute() and ".." in raw_backup_root.parts:
        raise SyncError("alias backup root cannot escape the workspace")
    alias_backup_root = (
        raw_backup_root.resolve()
        if raw_backup_root.is_absolute()
        else (workspace / raw_backup_root).resolve()
    )
    repositories = [Path(item) for item in args.repositories] or discover_workspace(
        workspace, exclusions
    )
    if not args.repositories:
        known = {item.resolve() for item in repositories}
        for excluded_name in _exclusion_reasons(exclusions):
            excluded_path = workspace / excluded_name
            if excluded_path.exists() and excluded_path.resolve() not in known:
                repositories.append(excluded_path)
                known.add(excluded_path.resolve())
        for alias_name in aliases:
            alias_path = workspace / alias_name
            if alias_path.exists() and alias_path.resolve() not in known:
                repositories.append(alias_path)
                known.add(alias_path.resolve())
    inventory = audit_repositories(
        repositories,
        workspace=workspace,
        aliases=aliases,
        alias_backup_root=alias_backup_root,
        exclusions=exclusions,
    )
    if args.command in {"inventory", "install-hooks"}:
        audit_external_references(
            inventory,
            repository_routes=dict(policy.get("repository_routes", {})),
            loader=_strict_reference_candidates,
        )
    if args.command == "inventory":
        for entry in inventory.entries:
            print(json.dumps(entry, sort_keys=True))
        for error in inventory.errors:
            print(json.dumps({"status": "ambiguous", "reason": error}, sort_keys=True))
        has_ineligible = any(
            entry.get("status") in {"ineligible", "alias-migration-required"}
            for entry in inventory.entries
        )
        return 1 if inventory.errors or has_ineligible else 0
    if args.command == "reconcile":
        identities, inventory_failures = reconcile_inventory_selection(inventory)
        runner = lambda identity: reconcile(
            identity,
            dry_run=args.dry_run,
            full_reconcile=not args.queued_only,
            route_config=dict(policy.get("repository_routes", {})).get(
                identity.repo.name, {}
            ),
        )
        if uses_fair_workspace_sweep(args) and identities:
            summary = reconcile_repositories_fair(
                identities,
                runner=runner,
                sweep_store=WorkspaceSweepStore(workspace),
            )
        else:
            summary = reconcile_repositories(identities, runner=runner)
            summary["deferred"] = []
            summary["coalesced"] = False
            summary["warnings"] = []
        summary["failed"].update(inventory_failures)
        summary["exit_code"] = 1 if summary["failed"] else 0
        for slug, result in summary["succeeded"].items():
            print(f"{slug}: {json.dumps(result, sort_keys=True)}")
        for slug, error in summary["failed"].items():
            print(f"{slug}: {json.dumps({'error': error}, sort_keys=True)}")
        for warning in summary.get("warnings", []):
            print(
                "workspace-sweep: "
                f"{json.dumps({'warning': warning}, sort_keys=True)}"
            )
        print(
            json.dumps(
                {
                    "summary": {
                        "succeeded": len(summary["succeeded"]),
                        "failed": len(summary["failed"]),
                        "deferred": len(summary.get("deferred", [])),
                        "coalesced": bool(summary.get("coalesced")),
                        "warnings": len(summary.get("warnings", [])),
                    }
                },
                sort_keys=True,
            )
        )
        return int(summary["exit_code"])
    identities = inventory.require_unambiguous()
    ineligible = [item for item in inventory.entries if item.get("status") == "ineligible"]
    if ineligible:
        raise IdentityError("; ".join(str(item.get("reason")) for item in ineligible))
    migration_required = [
        item
        for item in inventory.entries
        if item.get("status") == "alias-migration-required"
    ]
    if migration_required and not (
        args.command == "install-hooks" and args.apply_alias_redirects
    ):
        raise IdentityError(
            "validated aliases require explicit --apply-alias-redirects enrollment"
        )
    shell_script = Path(__file__).with_suffix(".sh").resolve()
    if args.command == "install-hooks":
        changed_by_repo = install_hooks_batch(
            identities,
            shell_script,
            dry_run=args.dry_run,
            executable_overrides={
                "bd": os.environ.get("BEADS_SYNC_BD", ""),
                "gh": os.environ.get("BEADS_SYNC_GH", ""),
            },
            alias_migrations=(
                inventory.alias_migrations if args.apply_alias_redirects else []
            ),
            alias_backup_root=alias_backup_root,
        )
        for identity in identities:
            print(
                f"{identity.slug}: "
                f"{'would change' if args.dry_run else 'changed'} "
                f"{changed_by_repo[identity.repo]} hook(s)"
            )
        return 0
    for identity in identities:
        store = StateStore(identity.state_file, identity, create=False)
        if args.command == "trigger":
            if not store.read().get("enrolled"):
                print(f"skip {identity.slug}: not enrolled")
                continue
            verify_pinned_executables(store.read())
            requested = list(args.bead)
            # `--bead` without a repository argument reaches every enrolled
            # repository. A bead id belongs to one database, so route it by its
            # own prefix instead of queuing it where it cannot resolve.
            ids = [
                bead_id
                for bead_id in requested
                if bead_belongs_to_prefix(bead_id, identity.issue_prefix)
            ]
            if requested and not ids:
                print(
                    f"skip {identity.slug}: "
                    f"{','.join(requested)} belongs to another Beads database"
                )
                continue
            if not args.dry_run and ids:
                store.enqueue(ids, _format_time(datetime.now(timezone.utc)))
            if not args.dry_run:
                if not args.no_start:
                    _start_worker(identity, Path(__file__).resolve())
            detail = ",".join(ids) if ids else "incremental-discovery"
            print(
                f"{identity.slug}: "
                f"{'would enqueue' if args.dry_run else 'enqueued'} {detail}"
            )
        elif args.command == "legacy":
            if not store.read().get("enrolled"):
                print(f"skip {identity.slug}: legacy trigger disabled until enrollment")
                continue
            verify_pinned_executables(store.read())
            _start_worker(identity, Path(__file__).resolve())
            print(f"{identity.slug}: legacy trigger converted to incremental reconcile")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SyncError, OSError) as exc:
        print(f"github_sync: {exc}", file=sys.stderr)
        raise SystemExit(1)
