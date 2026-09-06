#!/usr/bin/env python3
"""Standalone installer for an exported Orchestration Console release.

The installer deliberately uses only the Python standard library.  The release
manifest is the authority for every byte copied into a user's runtime.  A
bootstrap is planned completely before the console build or any user mutation,
and mutations are journalled so rollback can refuse drift instead of deleting
unrelated user data.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


MANIFEST_NAME = "release-manifest.json"
JOURNAL_SCHEMA = "orchestration-console-install-journal/v1"
CODEX_SKILLS = (
    "cleanup-audit",
    "graphify-project",
    "orchestration-closeout",
    "orchestration-setup",
    "orchestrator-stage",
    "prompt-authoring",
    "system-stability-check",
    "task-router",
    "technical-premortem",
    "test-pass",
)
CODEX_BEGIN = "<!-- CODEX-GLOBAL:BEGIN -->"
CODEX_END = "<!-- CODEX-GLOBAL:END -->"
KERNEL_BEGIN = "<!-- HARNESS-KERNEL:BEGIN -->"
KERNEL_END = "<!-- HARNESS-KERNEL:END -->"
ROUTING_BEGIN = "<!-- HARNESS-ROUTING:BEGIN -->"
ROUTING_END = "<!-- HARNESS-ROUTING:END -->"
REQUIRED_BINARIES = ("git", "uv", "node", "npm", "codex", "claude", "bd", "context")


class InstallerError(RuntimeError):
    """A safe, user-actionable installer failure."""


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    sha256: str
    mode: int


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    entries: Mapping[str, ManifestEntry]


@dataclass(frozen=True)
class Homes:
    user: Path
    agents: Path
    codex: Path
    claude: Path
    binary: Path
    state: Path


@dataclass(frozen=True)
class WriteOp:
    path: Path
    kind: str
    data: bytes | None = None
    mode: int = 0o644
    link_target: str | None = None
    label: str = ""
    scope_root: Path | None = None
    retire: bool = False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_mode(value: Any) -> int:
    if isinstance(value, int):
        # Exporters may use either permission bits (493) or Git mode (100755).
        text = str(value)
        if len(text) == 6 and text.startswith("100"):
            return int(text[-3:], 8)
        return value & 0o777
    if isinstance(value, str):
        text = value.strip().lower()
        if text.startswith("0o"):
            return int(text, 8) & 0o777
        if len(text) == 6 and text.startswith("100"):
            return int(text[-3:], 8)
        if re.fullmatch(r"[0-7]{3,4}", text):
            return int(text, 8) & 0o777
    raise InstallerError(f"invalid release file mode: {value!r}")


def _relative_manifest_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise InstallerError("release manifest contains an empty file path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or value != path.as_posix()
    ):
        raise InstallerError(f"unsafe release file path: {value}")
    if value.startswith(".git/") or "/.git/" in f"/{value}/" or value == ".git":
        raise InstallerError(f"release manifest must not contain Git metadata: {value}")
    return path.as_posix()


def load_manifest(root: Path) -> ReleaseManifest:
    manifest_path = root / MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InstallerError(f"release manifest is missing: {manifest_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallerError(f"cannot read release manifest {manifest_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise InstallerError("release manifest must be a JSON object")
    schema = payload.get("schema_version")
    if schema not in (1, "1", "release-manifest/v1"):
        raise InstallerError(f"unsupported release manifest schema: {schema!r}")
    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        raise InstallerError("release manifest version must be a non-empty string")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise InstallerError("release manifest files must be a non-empty list")
    entries: dict[str, ManifestEntry] = {}
    for raw in files:
        if not isinstance(raw, dict):
            raise InstallerError("release manifest file entries must be objects")
        path = _relative_manifest_path(raw.get("path"))
        digest = raw.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise InstallerError(f"invalid SHA-256 for release file: {path}")
        if path in entries:
            raise InstallerError(f"duplicate release file path: {path}")
        entries[path] = ManifestEntry(path, digest, _parse_mode(raw.get("mode")))
    return ReleaseManifest(version.strip(), entries)


def verify_release(root: Path, manifest: ReleaseManifest) -> None:
    resolved_root = root.resolve()
    failures: list[str] = []
    for entry in manifest.entries.values():
        source = root / PurePosixPath(entry.path)
        try:
            metadata = source.lstat()
        except FileNotFoundError:
            failures.append(f"missing: {entry.path}")
            continue
        if stat.S_ISLNK(metadata.st_mode):
            failures.append(f"symlink is forbidden in a release: {entry.path}")
            continue
        if not stat.S_ISREG(metadata.st_mode):
            failures.append(f"not a regular file: {entry.path}")
            continue
        try:
            source.resolve().relative_to(resolved_root)
        except ValueError:
            failures.append(f"file escapes release root: {entry.path}")
            continue
        actual_digest = _file_sha256(source)
        if actual_digest != entry.sha256:
            failures.append(f"SHA-256 mismatch: {entry.path}")
        actual_mode = stat.S_IMODE(metadata.st_mode)
        if actual_mode != entry.mode:
            failures.append(
                f"mode mismatch: {entry.path} is {actual_mode:04o}, expected {entry.mode:04o}"
            )
    generated_roots = {".venv", "node_modules", "state"}
    generated_directory_names = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    generated_prefixes = {"web/dist", "harness/distribution/__pycache__"}
    expected = set(manifest.entries)
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        relative_directory = Path(directory).relative_to(root).as_posix()
        if relative_directory == ".":
            relative_directory = ""
        kept_subdirectories: list[str] = []
        for name in subdirectories:
            relative = f"{relative_directory}/{name}".lstrip("/")
            candidate = Path(directory) / name
            # Build/state roots are allowed to be generated directories, but a
            # symlink here could redirect package managers outside the release.
            if candidate.is_symlink():
                failures.append(f"unlisted symlink in release: {relative}")
                continue
            if name == ".git":
                # A user's public clone has local Git metadata. It is not a
                # distribution input; never traverse or install it. The exporter
                # still rejects all Git history in distributable source bundles.
                if relative != ".git":
                    failures.append(f"nested Git metadata is forbidden in release: {relative}")
                continue
            if (
                relative in generated_roots
                or relative in generated_prefixes
                or name in generated_directory_names
            ):
                continue
            kept_subdirectories.append(name)
        subdirectories[:] = kept_subdirectories
        for name in filenames:
            relative = f"{relative_directory}/{name}".lstrip("/")
            if relative == MANIFEST_NAME:
                continue
            if relative not in expected:
                failures.append(f"unlisted file in release: {relative}")
    if failures:
        raise InstallerError("release integrity check failed:\n  " + "\n  ".join(failures))


def resolve_homes(home_override: Path | None, env: Mapping[str, str]) -> Homes:
    def require_under_user(user: Path, candidate: Path, label: str) -> None:
        try:
            candidate.resolve(strict=False).relative_to(user)
        except ValueError as exc:
            raise InstallerError(
                f"{label} escapes the selected home through a symlink: {candidate}"
            ) from exc

    if home_override is not None:
        user = home_override.expanduser().resolve()
        homes = Homes(
            user=user,
            agents=user / ".agents",
            codex=user / ".codex",
            claude=user / ".claude",
            binary=user / ".local" / "bin",
            state=user / ".agent-harness" / "state",
        )
        for label, candidate in (
            ("AGENTS_HOME", homes.agents),
            ("CODEX_HOME", homes.codex),
            ("CLAUDE_HOME", homes.claude),
            ("binary directory", homes.binary),
            ("state directory", homes.state),
        ):
            require_under_user(user, candidate, label)
        return homes
    configured_home = env.get("HOME")
    if not configured_home:
        raise InstallerError("HOME is not set; pass --home explicitly")
    user = Path(configured_home).expanduser().resolve()

    def configured(name: str, fallback: Path) -> Path:
        value = env.get(name)
        return Path(value).expanduser().resolve() if value else fallback

    claude_value = env.get("CLAUDE_HOME") or env.get("CLAUDE_CONFIG_DIR")
    homes = Homes(
        user=user,
        agents=configured("AGENTS_HOME", user / ".agents"),
        codex=configured("CODEX_HOME", user / ".codex"),
        claude=Path(claude_value).expanduser().resolve() if claude_value else user / ".claude",
        binary=user / ".local" / "bin",
        state=user / ".agent-harness" / "state",
    )
    for variable, candidate in (
        ("AGENTS_HOME", homes.agents),
        ("CODEX_HOME", homes.codex),
        ("CLAUDE_HOME", homes.claude),
    ):
        if not env.get(variable) and not (
            variable == "CLAUDE_HOME" and env.get("CLAUDE_CONFIG_DIR")
        ):
            require_under_user(user, candidate, variable)
    require_under_user(user, homes.binary, "binary directory")
    require_under_user(user, homes.state, "state directory")
    return homes


def _node_requirement(root: Path) -> str | None:
    lock = root / "package-lock.json"
    try:
        payload = json.loads(lock.read_text(encoding="utf-8"))
        packages = payload.get("packages", {})
        value = packages.get("", {}).get("engines", {}).get("node")
        if not value:
            # Vite is the actual frontend build entrypoint and carries the
            # authoritative Node range when the root package omits one.
            value = packages.get("node_modules/vite", {}).get("engines", {}).get("node")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return value if isinstance(value, str) and value.strip() else None


def _version_tuple(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def _node_satisfies(version: tuple[int, int, int], requirement: str | None) -> bool:
    if not requirement:
        return True
    def clause_matches(clause: str) -> bool:
        tokens = re.findall(r"(?:\^|~|>=|<=|>|<)?\s*\d+(?:\.\d+){0,2}", clause)
        if not tokens or "".join(tokens).replace(" ", "") != clause.replace(" ", ""):
            raise InstallerError(
                f"unsupported Node engine expression in package-lock.json: {requirement}"
            )
        for token in tokens:
            match = re.fullmatch(r"\s*(\^|~|>=|<=|>|<)?\s*(\d+(?:\.\d+){0,2})\s*", token)
            assert match is not None
            operator = match.group(1) or ">="
            boundary = _version_tuple(match.group(2))
            assert boundary is not None
            if operator == ">=" and not version >= boundary:
                return False
            if operator == ">" and not version > boundary:
                return False
            if operator == "<=" and not version <= boundary:
                return False
            if operator == "<" and not version < boundary:
                return False
            if operator == "^":
                upper = (boundary[0] + 1, 0, 0)
                if not boundary <= version < upper:
                    return False
            if operator == "~":
                upper = (boundary[0], boundary[1] + 1, 0)
                if not boundary <= version < upper:
                    return False
        return True

    return any(clause_matches(clause.strip()) for clause in requirement.split("||"))


def check_prerequisites(root: Path) -> list[str]:
    failures: list[str] = []
    system = platform.system()
    if system not in {"Linux", "Darwin"}:
        failures.append(f"unsupported operating system: {system or 'unknown'}")
    if sys.version_info < (3, 11):
        failures.append(
            f"Python 3.11 or newer is required; current is {platform.python_version()}"
        )
    for binary in REQUIRED_BINARIES:
        if shutil.which(binary) is None:
            failures.append(f"required command is missing: {binary}")
    for client in ("codex", "claude"):
        executable = shutil.which(client)
        if executable:
            try:
                subprocess.run(
                    [executable, "--version"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                failures.append(f"cannot run {client} --version: {exc}")
    node = shutil.which("node")
    if node:
        try:
            result = subprocess.run(
                [node, "--version"], check=True, capture_output=True, text=True, timeout=10
            )
            version = _version_tuple(result.stdout or result.stderr)
            if version is None:
                failures.append("cannot parse Node version")
            elif not _node_satisfies(version, _node_requirement(root)):
                failures.append(
                    f"Node {'.'.join(map(str, version))} does not satisfy "
                    f"{_node_requirement(root)}"
                )
        except (OSError, subprocess.SubprocessError, InstallerError) as exc:
            failures.append(f"cannot validate Node: {exc}")
    return failures


def _safe_target(base: Path, relative: str) -> Path:
    candidate = base / PurePosixPath(relative)
    resolved_base = base.resolve()
    try:
        # Resolve the parent chain, not the leaf.  Some owned leaves are
        # intentionally symlinks (the canonical console and launchers).
        candidate.parent.resolve(strict=False).relative_to(resolved_base)
    except ValueError as exc:
        raise InstallerError(f"destination escapes managed root {base}: {candidate}") from exc
    current = candidate.parent
    while current != resolved_base and current != current.parent:
        if current.is_symlink():
            try:
                current.resolve().relative_to(resolved_base)
            except ValueError as exc:
                raise InstallerError(f"destination parent symlink escapes {base}: {current}") from exc
        current = current.parent
    return candidate


def _extract_block(text: str, begin: str, end: str) -> str | None:
    begin_count, end_count = text.count(begin), text.count(end)
    if begin_count == end_count == 0:
        return None
    if begin_count != 1 or end_count != 1 or text.index(begin) > text.index(end):
        raise InstallerError(f"incomplete or duplicate managed block: {begin}")
    _, tail = text.split(begin, 1)
    body, _ = tail.split(end, 1)
    return f"{begin}{body}{end}".strip()


def _upsert_block(
    existing: str,
    block: str,
    begin: str,
    end: str,
    *,
    allow_unmanaged: bool,
) -> str:
    installed = _extract_block(existing, begin, end)
    if installed is not None:
        prefix, tail = existing.split(begin, 1)
        _, suffix = tail.split(end, 1)
        # Everything outside the marker bytes is user-owned.  Do not normalize
        # blank lines, final newlines, spaces, or line endings there.
        return prefix + block + suffix
    if existing.strip() and not allow_unmanaged:
        raise InstallerError(
            f"target has unmanaged content and no {begin} marker; reconcile it before install"
        )
    if not existing:
        return block + "\n"
    separator = "" if existing.endswith("\n\n") else "\n" if existing.endswith("\n") else "\n\n"
    return existing + separator + block + "\n"


def _render_managed(
    source_text: str,
    existing: str,
    begin: str,
    end: str,
    *,
    allow_unmanaged: bool,
) -> str:
    block = _extract_block(source_text, begin, end)
    if block is None:
        block = f"{begin}\n{source_text.strip()}\n{end}"
    return _upsert_block(existing, block, begin, end, allow_unmanaged=allow_unmanaged)


def _path_state(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        return {"kind": "symlink", "link_target": os.readlink(path)}
    if path.is_file():
        return {
            "kind": "file",
            "sha256": _file_sha256(path),
            "mode": stat.S_IMODE(path.stat().st_mode),
        }
    if path.exists():
        return {"kind": "other"}
    return {"kind": "absent"}


def _desired_state(op: WriteOp) -> dict[str, Any]:
    if op.kind == "absent":
        return {"kind": "absent"}
    if op.kind == "symlink":
        return {"kind": "symlink", "link_target": op.link_target}
    assert op.data is not None
    return {"kind": "file", "sha256": _sha256(op.data), "mode": op.mode}


def _state_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    if actual.get("kind") != expected.get("kind"):
        return False
    if actual.get("kind") == "file":
        return actual.get("sha256") == expected.get("sha256") and actual.get("mode") == expected.get("mode")
    if actual.get("kind") == "symlink":
        return actual.get("link_target") == expected.get("link_target")
    return actual.get("kind") == "absent"


class Installer:
    def __init__(
        self,
        root: Path,
        homes: Homes,
        *,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.homes = homes
        self.env = dict(os.environ if env is None else env)
        self.manifest = load_manifest(self.root)
        self.journal_path = _safe_target(homes.state, "install-journal.json")

    @property
    def plugins_root(self) -> Path:
        return self.homes.state.parent / "plugins"

    def _validate_release_contract(self) -> None:
        for required in (
            "pyproject.toml",
            "uv.lock",
            "package.json",
            "package-lock.json",
            "scripts/start_console.sh",
            "scripts/node_mcp_env.sh",
        ):
            self._source_bytes(required)

    def _source_bytes(self, path: str) -> bytes:
        if path not in self.manifest.entries:
            raise InstallerError(f"required source is absent from release manifest: {path}")
        return (self.root / PurePosixPath(path)).read_bytes()

    def _entries_below(self, prefix: str) -> list[ManifestEntry]:
        prefix = prefix.rstrip("/") + "/"
        return sorted(
            (entry for path, entry in self.manifest.entries.items() if path.startswith(prefix)),
            key=lambda entry: entry.path,
        )

    def _copy_tree_ops(self, source_prefix: str, destination: Path, label: str) -> list[WriteOp]:
        entries = self._entries_below(source_prefix)
        if not entries:
            raise InstallerError(f"required release tree is missing: {source_prefix}")
        prefix = source_prefix.rstrip("/") + "/"
        return [
            WriteOp(
                _safe_target(destination, entry.path[len(prefix) :]),
                "file",
                self._source_bytes(entry.path),
                entry.mode,
                label=label,
            )
            for entry in entries
        ]

    def _managed_op(
        self,
        source: str,
        target: Path,
        begin: str,
        end: str,
        *,
        allow_unmanaged: bool,
        transform: Any = None,
        label: str,
    ) -> WriteOp:
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise InstallerError(f"managed file target is not a regular file: {target}")
        try:
            source_text = self._source_bytes(source).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InstallerError(f"managed guidance is not UTF-8: {source}") from exc
        if transform is not None:
            source_text = transform(source_text)
        try:
            existing = target.read_bytes().decode("utf-8") if target.exists() else ""
        except UnicodeDecodeError as exc:
            raise InstallerError(f"managed target is not UTF-8: {target}") from exc
        content = _render_managed(
            source_text,
            existing,
            begin,
            end,
            allow_unmanaged=allow_unmanaged,
        )
        target_mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
        return WriteOp(target, "file", content.encode("utf-8"), target_mode, label=label)

    def _load_journal(self) -> dict[str, Any] | None:
        if not self.journal_path.exists():
            return None
        if self.journal_path.is_symlink() or not self.journal_path.is_file():
            raise InstallerError(f"install journal is not a regular file: {self.journal_path}")
        try:
            payload = json.loads(self.journal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InstallerError(f"cannot read install journal: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != JOURNAL_SCHEMA:
            raise InstallerError("unsupported or invalid install journal")
        if not isinstance(payload.get("entries"), list):
            raise InstallerError("install journal has no entries list")
        if not isinstance(payload.get("declared_paths", []), list):
            raise InstallerError("install journal has an invalid declared_paths list")
        self._validate_journal_schema(payload)
        return payload

    @staticmethod
    def _path_under(path: Path, roots: Sequence[Path]) -> bool:
        if not path.is_absolute():
            return False
        resolved_parent = path.parent.resolve(strict=False)
        for root in roots:
            resolved_root = root.resolve(strict=False)
            if resolved_parent == resolved_root:
                return True
            try:
                resolved_parent.relative_to(resolved_root)
                return True
            except ValueError:
                continue
        return False

    def _validate_journal_schema(self, payload: Mapping[str, Any]) -> None:
        status = payload.get("status", "committed")
        if status not in {"committed", "in_progress", "rollback_in_progress"}:
            raise InstallerError("install journal has invalid transaction status")
        if not isinstance(payload.get("release_version"), str) or not isinstance(
            payload.get("source_root"), str
        ):
            raise InstallerError("install journal has invalid release metadata")
        project_roots_raw = payload.get("project_roots", [])
        created_dirs = payload.get("created_dirs", [])
        declared_paths = payload.get("declared_paths", [])
        if not all(isinstance(value, str) for value in project_roots_raw):
            raise InstallerError("install journal has invalid project roots")
        if not all(isinstance(value, str) for value in created_dirs):
            raise InstallerError("install journal has invalid created directories")
        if not all(isinstance(value, str) for value in declared_paths):
            raise InstallerError("install journal has invalid declared paths")
        project_roots = [Path(value) for value in project_roots_raw]
        if any(not root.is_absolute() or not (root / ".git").exists() for root in project_roots):
            raise InstallerError("install journal contains an unsafe project root")
        entry_roots = [
            self.homes.agents,
            self.homes.codex,
            self.homes.claude,
            self.homes.binary,
            self.homes.state.parent,
            *project_roots,
        ]
        directory_roots = [
            self.homes.user,
            self.homes.agents,
            self.homes.codex,
            self.homes.claude,
            self.homes.binary.parent,
            self.homes.state.parent,
            *project_roots,
        ]
        seen: set[str] = set()
        backup_root = (self.homes.state / "backups").resolve(strict=False)
        for raw in payload["entries"]:
            if not isinstance(raw, dict):
                raise InstallerError("install journal contains a non-object entry")
            path_value = raw.get("path")
            if not isinstance(path_value, str) or path_value in seen:
                raise InstallerError("install journal contains an invalid or duplicate path")
            seen.add(path_value)
            path = Path(path_value)
            if not self._path_under(path, entry_roots):
                raise InstallerError(f"install journal path is outside managed roots: {path}")
            installed = raw.get("installed")
            before = raw.get("before")
            if not isinstance(installed, dict) or installed.get("kind") not in {"file", "symlink"}:
                raise InstallerError(f"install journal has invalid installed state: {path}")
            if installed["kind"] == "file":
                if not re.fullmatch(r"[0-9a-f]{64}", str(installed.get("sha256", ""))):
                    raise InstallerError(f"install journal has invalid installed hash: {path}")
                if not isinstance(installed.get("mode"), int) or not 0 <= installed["mode"] <= 0o777:
                    raise InstallerError(f"install journal has invalid installed mode: {path}")
            elif not isinstance(installed.get("link_target"), str):
                raise InstallerError(f"install journal has invalid link target: {path}")
            if not isinstance(before, dict) or before.get("kind") not in {"absent", "file"}:
                raise InstallerError(f"install journal has invalid prior state: {path}")
            if before["kind"] == "file":
                backup_value = before.get("backup")
                if not isinstance(backup_value, str):
                    raise InstallerError(f"install journal has invalid backup path: {path}")
                backup = Path(backup_value)
                try:
                    backup.resolve(strict=False).relative_to(backup_root)
                except ValueError as exc:
                    raise InstallerError(f"install journal backup escapes state/backups: {backup}") from exc
                if not re.fullmatch(r"[0-9a-f]{64}", str(before.get("sha256", ""))):
                    raise InstallerError(f"install journal has invalid backup hash: {path}")
                if not isinstance(before.get("mode"), int) or not 0 <= before["mode"] <= 0o777:
                    raise InstallerError(f"install journal has invalid backup mode: {path}")
        for value in declared_paths:
            if not self._path_under(Path(value), entry_roots):
                raise InstallerError(f"install journal declaration is outside managed roots: {value}")
        for value in created_dirs:
            directory = Path(value)
            if directory not in directory_roots and not self._path_under(
                directory / ".journal-boundary", directory_roots
            ):
                raise InstallerError(f"install journal directory is outside managed roots: {value}")
        if status == "in_progress":
            transaction = payload.get("transaction_entries")
            if not isinstance(transaction, list):
                raise InstallerError("unfinished install journal has no transaction entries")
            transaction_backup = payload.get("transaction_backup_root")
            if not isinstance(transaction_backup, str):
                raise InstallerError("unfinished install journal has no backup root")
            transaction_backup_path = Path(transaction_backup)
            try:
                transaction_backup_path.resolve(strict=False).relative_to(backup_root)
            except ValueError as exc:
                raise InstallerError(
                    f"unfinished transaction backup root is unsafe: {transaction_backup_path}"
                ) from exc
            if transaction_backup_path.resolve(strict=False) == backup_root:
                raise InstallerError("unfinished transaction backup root is too broad")
            transaction_dirs = payload.get("transaction_created_dirs")
            if not isinstance(transaction_dirs, list) or not all(
                isinstance(value, str) for value in transaction_dirs
            ):
                raise InstallerError("unfinished install journal has invalid created directories")
            for value in transaction_dirs:
                directory = Path(value)
                if directory not in directory_roots and not self._path_under(
                    directory / ".journal-boundary", directory_roots
                ):
                    raise InstallerError(
                        f"unfinished journal directory is outside managed roots: {value}"
                    )
            for raw in transaction:
                if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
                    raise InstallerError("unfinished install journal has an invalid path")
                path = Path(raw["path"])
                if not self._path_under(path, entry_roots):
                    raise InstallerError(f"unfinished journal path is outside managed roots: {path}")
                before = raw.get("transaction_before")
                installed = raw.get("installed")
                if not isinstance(before, dict) or before.get("kind") not in {
                    "absent",
                    "file",
                    "symlink",
                }:
                    raise InstallerError(f"unfinished journal has invalid prior state: {path}")
                if not isinstance(installed, dict) or installed.get("kind") not in {
                    "absent",
                    "file",
                    "symlink",
                }:
                    raise InstallerError(f"unfinished journal has invalid planned state: {path}")
                if before["kind"] == "file":
                    encoded = before.get("data_b64")
                    if not isinstance(encoded, str):
                        raise InstallerError(f"unfinished journal has no recovery bytes: {path}")
                    try:
                        data = base64.b64decode(encoded, validate=True)
                    except (ValueError, base64.binascii.Error) as exc:
                        raise InstallerError(f"unfinished journal has invalid recovery bytes: {path}") from exc
                    if _sha256(data) != before.get("sha256"):
                        raise InstallerError(f"unfinished journal recovery hash differs: {path}")
                    if not isinstance(before.get("mode"), int):
                        raise InstallerError(f"unfinished journal recovery mode is invalid: {path}")
                if before["kind"] == "symlink" and not isinstance(
                    before.get("link_target"), str
                ):
                    raise InstallerError(f"unfinished journal recovery link is invalid: {path}")
                if installed["kind"] == "file" and (
                    not re.fullmatch(r"[0-9a-f]{64}", str(installed.get("sha256", "")))
                    or not isinstance(installed.get("mode"), int)
                ):
                    raise InstallerError(f"unfinished journal planned file is invalid: {path}")
                if installed["kind"] == "symlink" and not isinstance(
                    installed.get("link_target"), str
                ):
                    raise InstallerError(f"unfinished journal planned link is invalid: {path}")

    def _owned_entries(self, journal: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not journal:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for raw in journal["entries"]:
            if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
                raise InstallerError("install journal contains an invalid entry")
            result[raw["path"]] = raw
        return result

    def global_ops(self) -> tuple[list[WriteOp], list[Path]]:
        self._validate_release_contract()
        ops: list[WriteOp] = []
        exclusive: list[Path] = []
        canonical = _safe_target(self.homes.agents, "orchestration-console")

        codex_global = self._managed_op(
            "harness/private/private/codex/global/AGENTS.md",
            _safe_target(self.homes.codex, "AGENTS.md"),
            CODEX_BEGIN,
            CODEX_END,
            allow_unmanaged=False,
            label="Codex global guidance",
        )
        ops.append(codex_global)
        ops.append(
            self._managed_op(
                "policy/runtime-kernel-v1.md",
                _safe_target(self.homes.agents, "AGENTS.md"),
                KERNEL_BEGIN,
                KERNEL_END,
                allow_unmanaged=True,
                label="shared runtime kernel",
            )
        )

        def render_claude(text: str) -> str:
            import_path = str(_safe_target(self.homes.agents, "AGENTS.md").resolve())
            if any(character.isspace() for character in import_path):
                raise InstallerError("Claude shared guidance path must not contain whitespace")
            return text.replace("{{SHARED_AGENTS_PATH}}", import_path)

        ops.append(
            self._managed_op(
                "claude-plugin/orchestration-bridge/templates/global/CLAUDE.md",
                _safe_target(self.homes.claude, "CLAUDE.md"),
                ROUTING_BEGIN,
                ROUTING_END,
                allow_unmanaged=True,
                transform=render_claude,
                label="Claude global routing",
            )
        )

        skill_source = "harness/private/private/codex/skills"
        available_skills = {
            path.split("/")[5]
            for path in self.manifest.entries
            if path.startswith(skill_source + "/") and len(path.split("/")) > 5
        }
        if available_skills != set(CODEX_SKILLS):
            raise InstallerError(
                "release must contain exactly the approved Codex skill set; found: "
                + ", ".join(sorted(available_skills))
            )
        for name in CODEX_SKILLS:
            target = _safe_target(self.homes.agents, f"skills/{name}")
            exclusive.append(target)
            ops.extend(self._copy_tree_ops(f"{skill_source}/{name}", target, f"Codex skill {name}"))

        bootstrap_target = _safe_target(self.homes.agents, "skills/harness-bootstrap")
        exclusive.append(bootstrap_target)
        ops.extend(
            self._copy_tree_ops(
                "harness/core/assets/codex/skills/harness-bootstrap",
                bootstrap_target,
                "harness-bootstrap skill",
            )
        )

        agent_prefix = "harness/private/private/codex/agents/"
        agents = sorted(
            [
                entry
                for entry in self.manifest.entries.values()
                if entry.path.startswith(agent_prefix) and entry.path.endswith(".toml")
            ],
            key=lambda entry: entry.path,
        )
        if len(agents) != 42:
            raise InstallerError(f"release must contain 42 Codex agent roles; found {len(agents)}")
        for entry in agents:
            name = PurePosixPath(entry.path).name
            ops.append(
                WriteOp(
                    _safe_target(self.homes.codex, f"agents/{name}"),
                    "file",
                    self._source_bytes(entry.path),
                    entry.mode,
                    label=f"Codex agent {name}",
                )
            )
        quality_pack_path = "harness/private/private/codex/agents/QUALITY_PACK.md"
        quality_pack_entry = self.manifest.entries.get(quality_pack_path)
        if quality_pack_entry is None:
            raise InstallerError("release is missing the Codex QUALITY_PACK.md")
        ops.append(
            WriteOp(
                _safe_target(self.homes.codex, "agents/QUALITY_PACK.md"),
                "file",
                self._source_bytes(quality_pack_path),
                quality_pack_entry.mode,
                label="Codex quality pack",
            )
        )

        bridge_target = _safe_target(self.plugins_root, "orchestration-bridge")
        exclusive.append(bridge_target)
        ops.extend(
            self._copy_tree_ops(
                "claude-plugin/orchestration-bridge", bridge_target, "Claude orchestration bridge"
            )
        )
        technical_target = _safe_target(bridge_target, "skills/technical-premortem")
        ops.extend(
            self._copy_tree_ops(
                "harness/private/private/claude/skills/technical-premortem",
                technical_target,
                "Claude technical-premortem skill",
            )
        )

        superpowers_entries = self._entries_below("harness/distribution/vendor/superpowers/skills")
        if not superpowers_entries:
            raise InstallerError("release is missing pinned Superpowers skills")
        for base, label in (
            (_safe_target(self.homes.codex, "superpowers"), "Codex Superpowers"),
            (_safe_target(self.plugins_root, "superpowers"), "Claude Superpowers"),
        ):
            exclusive.append(base)
            ops.extend(
                self._copy_tree_ops(
                    "harness/distribution/vendor/superpowers", base, label
                )
            )

        wrapper_source = (
            "bin/harness"
            if "bin/harness" in self.manifest.entries
            else "harness/distribution/bin/harness"
        )
        self._source_bytes(wrapper_source)
        wrapper_under_root = wrapper_source
        link_specs = (
            (canonical, str(self.root), "console source link"),
            (
                _safe_target(self.homes.agents, "skills/superpowers"),
                str(_safe_target(self.homes.codex, "superpowers/skills")),
                "Codex Superpowers discovery link",
            ),
            (
                _safe_target(self.homes.binary, "harness"),
                str(canonical / PurePosixPath(wrapper_under_root)),
                "harness launcher",
            ),
            (
                _safe_target(self.homes.binary, "orch-prompts"),
                str(canonical / "scripts/start_console.sh"),
                "orchestration console launcher",
            ),
            (
                _safe_target(self.homes.binary, "codex-prompts"),
                str(canonical / "scripts/start_console.sh"),
                "Codex console launcher",
            ),
            (
                _safe_target(self.homes.binary, "node-mcp-env"),
                str(canonical / "scripts/node_mcp_env.sh"),
                "Node MCP launcher",
            ),
        )
        for target, source, label in link_specs:
            ops.append(WriteOp(target, "symlink", link_target=source, label=label))

        # A second same-name Claude plugin can shadow or duplicate the explicit
        # --plugin-dir session.  Detect common native locations and enabled
        # marketplace registrations before writing our isolated plugin copies.
        for name in ("orchestration-bridge", "superpowers"):
            for candidate in (
                _safe_target(self.homes.claude, f"skills/{name}"),
                _safe_target(self.homes.claude, f"plugins/{name}"),
            ):
                if candidate.exists() or candidate.is_symlink():
                    raise InstallerError(f"same-name Claude asset may shadow the harness plugin: {candidate}")
        settings = _safe_target(self.homes.claude, "settings.json")
        if settings.exists():
            if settings.is_symlink() or not settings.is_file():
                raise InstallerError(f"Claude settings target is not a regular file: {settings}")
            try:
                enabled = json.loads(settings.read_text(encoding="utf-8")).get("enabledPlugins", {})
            except (OSError, json.JSONDecodeError, AttributeError) as exc:
                raise InstallerError(f"cannot inspect Claude enabled plugins: {exc}") from exc
            if isinstance(enabled, dict):
                duplicates = sorted(
                    key for key, value in enabled.items()
                    if value is True and isinstance(key, str)
                    and key.split("@", 1)[0] in {"orchestration-bridge", "superpowers"}
                )
                if duplicates:
                    raise InstallerError(
                        "same-name Claude plugin is already enabled: " + ", ".join(duplicates)
                    )
        return ops, exclusive

    def project_ops(self, project: Path) -> list[WriteOp]:
        project = project.expanduser().resolve()
        if not project.is_dir():
            raise InstallerError(f"project directory does not exist: {project}")
        if not (project / ".git").exists():
            raise InstallerError(f"project is not a Git checkout: {project}")
        templates = {
            "AGENTS.md": self._source_bytes("harness/core/templates/project/AGENTS.md"),
            ".codex/orchestrator.toml": self._source_bytes(
                "harness/core/templates/project/.codex/orchestrator.toml"
            ),
            "CLAUDE.md": b"@AGENTS.md\n",
        }
        ops: list[WriteOp] = []
        for relative, data in templates.items():
            target = _safe_target(project, relative)
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise InstallerError(f"project target is not a regular file: {target}")
            if target.exists() and target.read_bytes() != data:
                raise InstallerError(
                    f"project file already exists with different content: {target}; "
                    "merge the harness baseline manually"
                )
            target_mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
            ops.append(
                WriteOp(
                    target,
                    "file",
                    data,
                    target_mode,
                    label=f"project {relative}",
                    scope_root=project,
                )
            )
        return ops

    def _validate_existing_journal(self, journal: Mapping[str, Any] | None) -> None:
        if journal and journal.get("status", "committed") in {
            "in_progress",
            "rollback_in_progress",
        }:
            raise InstallerError(
                "an unfinished install or rollback transaction exists; "
                "run `harness rollback` before continuing"
            )
        for path, entry in self._owned_entries(journal).items():
            expected = entry.get("installed")
            if not isinstance(expected, dict) or not _state_matches(_path_state(Path(path)), expected):
                raise InstallerError(f"installed path was modified after installation: {path}")

    def _preflight(self, ops: Sequence[WriteOp], exclusive: Sequence[Path] = ()) -> dict[str, Any] | None:
        verify_release(self.root, self.manifest)
        failures = check_prerequisites(self.root)
        if failures:
            raise InstallerError("prerequisite check failed:\n  " + "\n  ".join(failures))
        journal = self._load_journal()
        self._validate_existing_journal(journal)
        owned = self._owned_entries(journal)
        desired_paths = {str(op.path) for op in ops}
        if len(desired_paths) != len(ops):
            raise InstallerError("installer generated duplicate destination paths")
        for directory in exclusive:
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                raise InstallerError(f"foreign destination collision: {directory}")
            if directory.exists() and not any(
                path == str(directory) or path.startswith(str(directory) + os.sep)
                for path in owned
            ):
                raise InstallerError(f"foreign same-name asset directory exists: {directory}")
        # Previously owned paths may be absent from a newer release. They are
        # allowed only long enough for plan() to add explicit retirement ops.
        self._audit_exclusive_roots(ops, exclusive, allowed_existing=set(owned))
        for op in ops:
            actual = _path_state(op.path)
            desired = _desired_state(op)
            if _state_matches(actual, desired):
                continue
            if actual["kind"] == "absent":
                continue
            if str(op.path) in owned:
                continue
            if op.label in {"Codex global guidance", "shared runtime kernel", "Claude global routing"}:
                # Managed-file content was already reconciled while creating the op.
                if actual["kind"] == "file":
                    continue
            raise InstallerError(f"foreign destination collision: {op.path} ({op.label})")
        return journal

    @staticmethod
    def _audit_exclusive_roots(
        ops: Sequence[WriteOp],
        exclusive: Sequence[Path],
        *,
        allowed_existing: set[str] | None = None,
    ) -> None:
        """Reject undeclared nodes inside harness-owned skill/plugin trees."""
        desired_files = {op.path for op in ops if op.kind != "absent"}
        desired_files.update(Path(value) for value in (allowed_existing or set()))
        for root in exclusive:
            if not root.exists():
                continue
            expected_files = {
                path for path in desired_files if path != root and root in path.parents
            }
            expected_dirs: set[Path] = {root}
            for path in expected_files:
                current = path.parent
                while current != root:
                    expected_dirs.add(current)
                    current = current.parent
            pending = [root]
            while pending:
                directory = pending.pop()
                if directory.is_symlink() or not directory.is_dir():
                    raise InstallerError(
                        f"exclusive asset directory has an unsafe node: {directory}"
                    )
                try:
                    children = list(directory.iterdir())
                except OSError as exc:
                    raise InstallerError(
                        f"cannot inspect exclusive asset directory {directory}: {exc}"
                    ) from exc
                for child in children:
                    if child in expected_dirs:
                        if child.is_symlink() or not child.is_dir():
                            raise InstallerError(
                                f"exclusive asset directory has an unsafe node: {child}"
                            )
                        pending.append(child)
                    elif child not in expected_files:
                        raise InstallerError(
                            f"undeclared file or directory in exclusive asset tree: {child}"
                        )

    def plan(self, *, project: Path | None = None) -> tuple[list[WriteOp], dict[str, Any] | None]:
        ops, exclusive = self.global_ops()
        if project is not None:
            ops.extend(self.project_ops(project))
        journal = self._preflight(ops, exclusive)
        if project is None and journal:
            desired = {str(op.path) for op in ops}
            retired = self._retired_global_ops(journal, desired)
            if retired:
                ops.extend(retired)
                journal = self._preflight(ops, exclusive)
        return ops, journal

    def _retired_global_ops(
        self, journal: Mapping[str, Any], desired: set[str]
    ) -> list[WriteOp]:
        retired: list[WriteOp] = []
        for path_value, entry in self._owned_entries(journal).items():
            if path_value in desired or str(entry.get("label", "")).startswith("project "):
                continue
            before = entry["before"]
            if before["kind"] == "absent":
                retired.append(
                    WriteOp(
                        Path(path_value),
                        "absent",
                        label=f"retire obsolete {entry.get('label', 'global asset')}",
                        retire=True,
                    )
                )
                continue
            backup = Path(before["backup"])
            if (
                backup.is_symlink()
                or not backup.is_file()
                or _file_sha256(backup) != before["sha256"]
            ):
                raise InstallerError(f"obsolete asset backup is missing or modified: {backup}")
            retired.append(
                WriteOp(
                    Path(path_value),
                    "file",
                    backup.read_bytes(),
                    int(before["mode"]),
                    label=f"retire obsolete {entry.get('label', 'global asset')}",
                    retire=True,
                )
            )
        return retired

    def _build_console(self) -> None:
        commands = (
            (["uv", "sync", "--frozen"], self.root),
            (["npm", "ci"], self.root),
            (["npm", "run", "build"], self.root),
        )
        for command, cwd in commands:
            try:
                subprocess.run(command, cwd=cwd, env=self.env, check=True)
            except (OSError, subprocess.CalledProcessError) as exc:
                raise InstallerError(f"console build failed: {' '.join(command)}: {exc}") from exc

    @staticmethod
    def _write_file(path: Path, data: bytes, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            os.chmod(temporary, mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _write_symlink(path: Path, target: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.symlink_to(target)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _snapshot(self, path: Path) -> dict[str, Any]:
        state = _path_state(path)
        if state["kind"] == "file":
            state["data"] = path.read_bytes()
        return state

    def _restore_snapshot(self, path: Path, snapshot: Mapping[str, Any]) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
        kind = snapshot.get("kind")
        if kind == "file":
            self._write_file(path, snapshot["data"], int(snapshot["mode"]))
        elif kind == "symlink":
            self._write_symlink(path, str(snapshot["link_target"]))
        elif kind != "absent":
            raise InstallerError(f"cannot restore unsupported prior path type: {path}")

    def _apply(
        self,
        ops: Sequence[WriteOp],
        prior: dict[str, Any] | None,
        *,
        build_fingerprint: str | None = None,
    ) -> list[Path]:
        prior_entries = self._owned_entries(prior)
        final_entries = dict(prior_entries)
        for op in ops:
            if op.retire:
                final_entries.pop(str(op.path), None)
        transaction: list[tuple[Path, dict[str, Any]]] = []
        transaction_dirs: set[Path] = set()
        journal_dirs: set[str] = set(prior.get("created_dirs", [])) if prior else set()
        project_roots: set[str] = set(prior.get("project_roots", [])) if prior else set()
        project_roots.update(str(op.scope_root) for op in ops if op.scope_root is not None)
        initially_missing_internal_dirs: set[Path] = set()
        current_internal = self.journal_path.parent
        while not current_internal.exists() and current_internal != current_internal.parent:
            initially_missing_internal_dirs.add(current_internal)
            current_internal = current_internal.parent
        created_backups: list[Path] = []
        changed: list[Path] = []
        install_id = uuid.uuid4().hex
        backup_root = _safe_target(self.homes.state, f"backups/{install_id}")
        journal_snapshot = self.journal_path.read_bytes() if self.journal_path.exists() else None
        transaction_entries: list[dict[str, Any]] = []
        for op in ops:
            desired = _desired_state(op)
            actual = _path_state(op.path)
            if _state_matches(actual, desired):
                continue
            snapshot = self._snapshot(op.path)
            serialized = {key: value for key, value in snapshot.items() if key != "data"}
            if snapshot["kind"] == "file":
                serialized["data_b64"] = base64.b64encode(snapshot["data"]).decode("ascii")
            transaction_entries.append(
                {
                    "path": str(op.path),
                    "transaction_before": serialized,
                    "installed": desired,
                }
            )
        prepared = {
            "schema_version": JOURNAL_SCHEMA,
            "status": "in_progress",
            "release_version": self.manifest.version,
            "source_root": str(self.root),
            "entries": prior.get("entries", []) if prior else [],
            "created_dirs": prior.get("created_dirs", []) if prior else [],
            "declared_paths": prior.get("declared_paths", []) if prior else [],
            "build_fingerprint": prior.get("build_fingerprint") if prior else None,
            "project_roots": sorted(project_roots),
            "transaction_entries": transaction_entries,
            "transaction_backup_root": str(backup_root),
            "previous_journal": prior,
            "transaction_created_dirs": sorted(
                {
                    str(directory)
                    for op in ops
                    for directory in self._missing_parent_directories(op.path)
                }
                | {str(directory) for directory in initially_missing_internal_dirs}
            ),
        }
        try:
            self._write_file(
                self.journal_path,
                (json.dumps(prepared, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                0o600,
            )
            for index, op in enumerate(ops):
                desired = _desired_state(op)
                actual = _path_state(op.path)
                if _state_matches(actual, desired):
                    continue
                snapshot = self._snapshot(op.path)
                transaction.append((op.path, snapshot))
                current_parent = op.path.parent
                while not current_parent.exists() and current_parent != current_parent.parent:
                    transaction_dirs.add(current_parent)
                    journal_dirs.add(str(current_parent))
                    current_parent = current_parent.parent
                existing_entry = prior_entries.get(str(op.path))
                if existing_entry is not None:
                    before = existing_entry["before"]
                elif snapshot["kind"] == "file":
                    backup = backup_root / f"{index:04d}.bak"
                    self._write_file(backup, snapshot["data"], int(snapshot["mode"]))
                    created_backups.append(backup)
                    before = {
                        "kind": "file",
                        "backup": str(backup),
                        "mode": snapshot["mode"],
                        "sha256": snapshot["sha256"],
                    }
                elif snapshot["kind"] == "absent":
                    before = {"kind": "absent"}
                else:
                    raise InstallerError(f"cannot replace unsupported path type: {op.path}")
                if op.kind == "file":
                    assert op.data is not None
                    self._write_file(op.path, op.data, op.mode)
                elif op.kind == "symlink":
                    assert op.link_target is not None
                    self._write_symlink(op.path, op.link_target)
                else:
                    if op.path.is_symlink() or op.path.is_file():
                        op.path.unlink()
                if not op.retire:
                    final_entries[str(op.path)] = {
                        "path": str(op.path),
                        "label": op.label,
                        "before": before,
                        "installed": desired,
                    }
                changed.append(op.path)
            for op in ops:
                if not op.retire:
                    continue
                current_parent = op.path.parent
                while str(current_parent) in journal_dirs:
                    try:
                        current_parent.rmdir()
                    except OSError:
                        break
                    journal_dirs.remove(str(current_parent))
                    current_parent = current_parent.parent
            prior_project_paths = {
                path
                for path, entry in prior_entries.items()
                if str(entry.get("label", "")).startswith("project ")
            }
            if any(op.scope_root is None for op in ops):
                declared_paths = prior_project_paths | {
                    str(op.path) for op in ops if not op.retire
                }
            else:
                declared_paths = (
                    set(prior.get("declared_paths", [])) if prior else set()
                ) | {str(op.path) for op in ops}
            journal = {
                "schema_version": JOURNAL_SCHEMA,
                "status": "committed",
                "release_version": self.manifest.version,
                "source_root": str(self.root),
                "entries": [final_entries[path] for path in sorted(final_entries)],
                "created_dirs": sorted(journal_dirs),
                "declared_paths": sorted(declared_paths),
                "build_fingerprint": (
                    build_fingerprint
                    if build_fingerprint is not None
                    else prior.get("build_fingerprint") if prior else None
                ),
                "project_roots": sorted(project_roots),
            }
            journal_dirs.update(str(path) for path in initially_missing_internal_dirs)
            journal["created_dirs"] = sorted(journal_dirs)
            encoded = (json.dumps(journal, indent=2, sort_keys=True) + "\n").encode("utf-8")
            # The physical journal currently contains the in-progress record,
            # even when the final committed bytes equal its pre-run snapshot.
            self._write_file(self.journal_path, encoded, 0o600)
            for op in ops:
                if not op.retire:
                    continue
                old_entry = prior_entries.get(str(op.path), {})
                old_before = old_entry.get("before", {})
                if old_before.get("kind") == "file":
                    try:
                        Path(old_before["backup"]).unlink()
                    except OSError:
                        pass
            return changed
        except BaseException:
            for path, snapshot in reversed(transaction):
                self._restore_snapshot(path, snapshot)
            for directory in sorted(transaction_dirs, key=lambda path: len(path.parts), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if journal_snapshot is None:
                self.journal_path.unlink(missing_ok=True)
            else:
                self._write_file(self.journal_path, journal_snapshot, 0o600)
            for backup in created_backups:
                backup.unlink(missing_ok=True)
            self._prune_empty(backup_root, self.homes.state)
            for directory in sorted(
                initially_missing_internal_dirs,
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise

    @staticmethod
    def _prune_empty(path: Path, stop: Path) -> None:
        stop = stop.resolve()
        current = path
        while current != stop and current != current.parent:
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent

    @staticmethod
    def _missing_parent_directories(path: Path) -> list[Path]:
        missing: list[Path] = []
        current = path.parent
        while not current.exists() and current != current.parent:
            missing.append(current)
            current = current.parent
        return missing

    def bootstrap(self, *, update: bool = False) -> list[Path]:
        ops, prior = self.plan()
        fingerprint = self._release_fingerprint()
        if not self._build_is_reusable(prior, fingerprint):
            self._build_console()
        # Build commands may be long.  Re-read every source and destination so
        # concurrent edits become a clean conflict instead of being overwritten.
        ops, prior = self.plan()
        return self._apply(ops, prior, build_fingerprint=fingerprint)

    def _release_fingerprint(self) -> str:
        material = "\n".join(
            f"{entry.path}\0{entry.sha256}\0{entry.mode:04o}"
            for entry in sorted(self.manifest.entries.values(), key=lambda item: item.path)
        )
        return _sha256(material.encode("utf-8"))

    def _build_is_reusable(
        self, prior: Mapping[str, Any] | None, fingerprint: str
    ) -> bool:
        return bool(
            prior
            and prior.get("source_root") == str(self.root)
            and prior.get("build_fingerprint") == fingerprint
            and (self.root / ".venv/bin/python").is_file()
            and (self.root / "node_modules").is_dir()
            and (self.root / "web/dist/index.html").is_file()
        )

    def init_project(self, project: Path) -> list[Path]:
        verify_release(self.root, self.manifest)
        failures = check_prerequisites(self.root)
        if failures:
            raise InstallerError("prerequisite check failed:\n  " + "\n  ".join(failures))
        ops = self.project_ops(project)
        prior = self._load_journal()
        self._validate_existing_journal(prior)
        # Project files are exact/non-overwriting, so their own checks complete
        # the conflict preflight without rebuilding the already installed panel.
        return self._apply(ops, prior)

    def doctor(self) -> list[str]:
        failures: list[str] = []
        try:
            verify_release(self.root, self.manifest)
        except InstallerError as exc:
            failures.append(str(exc))
        failures.extend(check_prerequisites(self.root))
        runtime_python = self.root / ".venv/bin/python"
        if not runtime_python.is_file() or not os.access(runtime_python, os.X_OK):
            failures.append(f"Python console runtime is missing or not executable: {runtime_python}")
        frontend_dependencies = self.root / "node_modules"
        if not frontend_dependencies.is_dir():
            failures.append(f"frontend dependencies directory is missing: {frontend_dependencies}")
        frontend = self.root / "web/dist/index.html"
        if not frontend.is_file():
            failures.append(f"built frontend is missing: {frontend}")
        try:
            journal = self._load_journal()
            if journal is None:
                failures.append(f"install journal is missing: {self.journal_path}")
            else:
                if journal.get("status", "committed") in {
                    "in_progress",
                    "rollback_in_progress",
                }:
                    failures.append(
                        "install or rollback transaction is unfinished; "
                        "run `harness rollback` before continuing"
                    )
                for path, entry in self._owned_entries(journal).items():
                    expected = entry.get("installed")
                    if not isinstance(expected, dict) or not _state_matches(_path_state(Path(path)), expected):
                        failures.append(f"installed path differs from journal: {path}")
                try:
                    required_ops, required_exclusive = self.global_ops()
                    self._audit_exclusive_roots(required_ops, required_exclusive)
                    declared = set(journal.get("declared_paths", []))
                    missing_declarations = sorted(
                        str(op.path) for op in required_ops if str(op.path) not in declared
                    )
                    if missing_declarations:
                        failures.append(
                            "install journal does not declare required paths: "
                            + ", ".join(missing_declarations)
                        )
                    for op in required_ops:
                        if not _state_matches(_path_state(op.path), _desired_state(op)):
                            failures.append(f"required installed path is missing or stale: {op.path}")
                except InstallerError as exc:
                    failures.append(str(exc))
        except InstallerError as exc:
            failures.append(str(exc))
        return failures

    def _validate_complete_install(self, journal: Mapping[str, Any]) -> None:
        """Apply the fail-closed checks required before launching a client."""
        self._validate_existing_journal(journal)
        required_ops, required_exclusive = self.global_ops()
        self._audit_exclusive_roots(required_ops, required_exclusive)
        declared = set(journal.get("declared_paths", []))
        missing_declarations = sorted(
            str(op.path) for op in required_ops if str(op.path) not in declared
        )
        if missing_declarations:
            raise InstallerError(
                "install journal does not declare required paths: "
                + ", ".join(missing_declarations)
            )
        stale = [
            str(op.path)
            for op in required_ops
            if not _state_matches(_path_state(op.path), _desired_state(op))
        ]
        if stale:
            raise InstallerError(
                "required installed paths are missing or stale: " + ", ".join(stale)
            )

    def rollback(self) -> list[Path]:
        verify_release(self.root, self.manifest)
        journal = self._load_journal()
        if journal is None:
            raise InstallerError("nothing to roll back: install journal is missing")
        status = journal.get("status", "committed")
        if status == "in_progress":
            return self._rollback_in_progress(journal)
        if status == "rollback_in_progress":
            return self._resume_committed_rollback(journal)
        self._validate_existing_journal(journal)
        prepared = dict(journal)
        prepared["status"] = "rollback_in_progress"
        self._write_file(
            self.journal_path,
            (json.dumps(prepared, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            0o600,
        )
        return self._resume_committed_rollback(prepared)

    @staticmethod
    def _prior_entry_state(entry: Mapping[str, Any]) -> dict[str, Any]:
        before = entry["before"]
        if before["kind"] == "absent":
            return {"kind": "absent"}
        return {
            "kind": "file",
            "sha256": before["sha256"],
            "mode": before["mode"],
        }

    def _resume_committed_rollback(self, journal: Mapping[str, Any]) -> list[Path]:
        entries = list(self._owned_entries(journal).values())
        actions: list[dict[str, Any]] = []
        for entry in entries:
            before = entry.get("before", {})
            if before.get("kind") == "file":
                backup = Path(before.get("backup", ""))
                if (
                    backup.is_symlink()
                    or not backup.is_file()
                    or _file_sha256(backup) != before.get("sha256")
                ):
                    raise InstallerError(f"rollback backup is missing or modified: {backup}")
            path = Path(entry["path"])
            actual = _path_state(path)
            if _state_matches(actual, self._prior_entry_state(entry)):
                continue
            if not _state_matches(actual, entry["installed"]):
                raise InstallerError(
                    f"rollback path has unexpected user changes; refusing rollback: {path}"
                )
            actions.append(entry)
        restored: list[Path] = []
        # Validation is complete before the first write.  Restore deepest paths
        # first and remove only empty directories, preserving user sentinels.
        try:
            for entry in sorted(
                actions, key=lambda item: len(Path(item["path"]).parts), reverse=True
            ):
                path = Path(entry["path"])
                before = entry["before"]
                if before["kind"] == "file":
                    backup = Path(before["backup"])
                    # Atomic replacement keeps the installed file recoverable
                    # until the restored bytes are fully written.
                    self._write_file(path, backup.read_bytes(), int(before["mode"]))
                else:
                    path.unlink()
                restored.append(path)
            self.journal_path.unlink()
        except Exception as exc:
            raise InstallerError(
                f"rollback was interrupted; recoverable journal was retained: {exc}"
            ) from exc
        backup_paths = [
            Path(entry["before"]["backup"])
            for entry in entries
            if entry.get("before", {}).get("kind") == "file"
        ]
        for backup in backup_paths:
            backup.unlink(missing_ok=True)
            self._prune_empty(backup.parent, self.homes.state)
        for raw in sorted(
            journal.get("created_dirs", []),
            key=lambda value: len(Path(value).parts),
            reverse=True,
        ):
            directory = Path(raw)
            try:
                directory.rmdir()
            except OSError:
                pass
        return restored

    def _rollback_in_progress(self, journal: Mapping[str, Any]) -> list[Path]:
        transaction = journal["transaction_entries"]
        actions: list[tuple[Path, dict[str, Any]]] = []
        for raw in transaction:
            path = Path(raw["path"])
            before = dict(raw["transaction_before"])
            if before["kind"] == "file":
                before["data"] = base64.b64decode(before["data_b64"], validate=True)
            actual = _path_state(path)
            before_state = {key: value for key, value in before.items() if key not in {"data", "data_b64"}}
            if _state_matches(actual, before_state):
                continue
            if not _state_matches(actual, raw["installed"]):
                raise InstallerError(
                    f"unfinished install path has unexpected user changes; refusing rollback: {path}"
                )
            actions.append((path, before))

        previous = journal.get("previous_journal")
        if previous is not None:
            if not isinstance(previous, dict):
                raise InstallerError("unfinished install has an invalid previous journal")
            self._validate_journal_schema(previous)
            if previous.get("status", "committed") != "committed":
                raise InstallerError("unfinished install previous journal is not committed")

        snapshots = {str(path): self._snapshot(path) for path, _before in actions}
        restored: list[Path] = []
        try:
            for path, before in actions:
                self._restore_snapshot(path, before)
                restored.append(path)
            if previous is None:
                self.journal_path.unlink()
            else:
                self._write_file(
                    self.journal_path,
                    (json.dumps(previous, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                    0o600,
                )
        except BaseException as exc:
            failures: list[str] = []
            for path in reversed(restored):
                try:
                    self._restore_snapshot(path, snapshots[str(path)])
                except BaseException as compensation_error:  # pragma: no cover - catastrophic I/O
                    failures.append(f"{path}: {compensation_error}")
            detail = "; compensation also failed: " + "; ".join(failures) if failures else ""
            raise InstallerError(
                f"unfinished transaction rollback failed; journal retained: {exc}{detail}"
            ) from exc

        backup_root = Path(journal.get("transaction_backup_root", ""))
        expected_backup_root = (self.homes.state / "backups").resolve(strict=False)
        try:
            backup_root.resolve(strict=False).relative_to(expected_backup_root)
        except ValueError as exc:
            raise InstallerError(f"unfinished transaction backup root is unsafe: {backup_root}") from exc
        if backup_root.name and backup_root != expected_backup_root:
            shutil.rmtree(backup_root, ignore_errors=True)
        for raw in sorted(
            journal.get("transaction_created_dirs", []),
            key=lambda value: len(Path(value).parts),
            reverse=True,
        ):
            try:
                Path(raw).rmdir()
            except OSError:
                pass
        return restored

    def launch_claude(self, arguments: Sequence[str]) -> None:
        verify_release(self.root, self.manifest)
        journal = self._load_journal()
        if journal is None:
            raise InstallerError("bootstrap must complete before `harness claude`")
        self._validate_complete_install(journal)
        executable = shutil.which("claude")
        if executable is None:
            raise InstallerError("required command is missing: claude")
        bridge = _safe_target(self.plugins_root, "orchestration-bridge")
        superpowers = _safe_target(self.plugins_root, "superpowers")
        for plugin in (bridge, superpowers):
            if not plugin.is_dir():
                raise InstallerError(f"installed Claude plugin is missing: {plugin}")
        forwarded = list(arguments)
        if forwarded[:1] == ["--"]:
            forwarded = forwarded[1:]
        os.execvpe(
            executable,
            [
                executable,
                "--plugin-dir",
                str(bridge),
                "--plugin-dir",
                str(superpowers),
                *forwarded,
            ],
            self.env,
        )


def _default_root() -> Path:
    # In the source monorepo this file is harness/distribution/installer.py;
    # the public export retains that path.  Both resolve to the release root.
    return Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness", description="Install a pinned public agent harness release.")
    parser.add_argument("--root", type=Path, default=None, help="explicit exported release root")
    parser.add_argument("--home", type=Path, default=None, help="override all user destinations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "bootstrap", "doctor", "rollback", "update"):
        command = subparsers.add_parser(name)
        command.add_argument("--root", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--home", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)
        command.add_argument("--verbose", action="store_true", help="list individual file operations")
    project = subparsers.add_parser("init-project")
    project.add_argument("project", nargs="?", type=Path, default=Path.cwd())
    project.add_argument("--root", type=Path, default=argparse.SUPPRESS)
    project.add_argument("--home", type=Path, default=argparse.SUPPRESS)
    project.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)
    claude = subparsers.add_parser("claude", help="run Claude with the pinned harness plugins")
    claude.add_argument("--root", type=Path, default=argparse.SUPPRESS)
    claude.add_argument("--home", type=Path, default=argparse.SUPPRESS)
    claude.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = (args.root or _default_root()).expanduser().resolve()
    try:
        homes = resolve_homes(args.home, os.environ)
        installer = Installer(root, homes)
        if args.command == "plan":
            ops, _ = installer.plan()
            print(f"release {installer.manifest.version}; {len(ops)} planned file/link operations:")
            for label, destination in (
                ("Codex", homes.codex),
                ("Shared skills and guidance", homes.agents),
                ("Claude guidance", homes.claude),
                ("Claude plugins and recovery journal", homes.state.parent),
                ("Launchers", homes.binary),
            ):
                print(f"  {label}: {destination}")
            print("Use plan --verbose for the exact file list. Bootstrap builds the console before installing.")
            if args.verbose:
                for op in ops:
                    print(f"  {op.path} ({op.label})")
            if platform.system() == "Darwin":
                print("note: macOS support is experimental")
        elif args.command in {"bootstrap", "update"}:
            changed = installer.bootstrap(update=args.command == "update")
            verb = "updated" if args.command == "update" else "installed"
            print(f"{verb} release {installer.manifest.version}; changed {len(changed)} paths")
            print(f"recovery journal: {installer.journal_path}")
            print("Next: harness doctor; start a new Codex session or run harness claude.")
            if args.verbose:
                for path in changed:
                    print(f"  {path}")
        elif args.command == "doctor":
            failures = installer.doctor()
            if failures:
                print("doctor found problems:", file=sys.stderr)
                for failure in failures:
                    print(f"  {failure}", file=sys.stderr)
                return 1
            print(f"doctor: release {installer.manifest.version} and installed paths are exact")
        elif args.command == "init-project":
            changed = installer.init_project(args.project)
            print(f"initialized project; changed {len(changed)} paths")
            for path in changed:
                print(f"  {path}")
        elif args.command == "rollback":
            restored = installer.rollback()
            print(f"rolled back {len(restored)} owned paths")
        elif args.command == "claude":
            installer.launch_claude(args.arguments)
        return 0
    except InstallerError as exc:
        print(f"harness: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
