#!/usr/bin/env python3
"""Copy mode-appropriate orchestration support templates into a repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import tomllib


SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]

COMMON_FILES = {
    "templates/stage-artifact-template.md": ".codex/stage-artifact-template.md",
    "templates/stage-manifest-template.json": ".codex/stage-manifest-template.json",
    "templates/scope-preservation-ledger-template.json": ".codex/scope-preservation-ledger-template.json",
    "templates/scope-criterion-snapshot-template.json": ".codex/scope-criterion-snapshot-template.json",
    "templates/verification-manifest-template.json": ".codex/verification-manifest-template.json",
    "templates/subagent-task-contract.md": ".codex/subagent-task-contract.md",
    "templates/subagent-spawn-template.md": ".codex/subagent-spawn-template.md",
    "templates/scripts/run_process_verification.sh": "scripts/orchestration/run_process_verification.sh",
    "templates/scripts/run_bounded_node_tests.py": "scripts/orchestration/run_bounded_node_tests.py",
    "templates/scripts/validate_artifact.py": "scripts/orchestration/validate_artifact.py",
    "templates/scripts/lint_stage_sizing.py": "scripts/orchestration/lint_stage_sizing.py",
    "templates/scripts/check_stage_ready.py": "scripts/orchestration/check_stage_ready.py",
    "templates/scripts/run_stage_closeout.py": "scripts/orchestration/run_stage_closeout.py",
    "templates/scripts/verification_evidence.py": "scripts/orchestration/verification_evidence.py",
    "templates/scripts/record_stage_telemetry.py": "scripts/orchestration/record_stage_telemetry.py",
    "templates/scripts/cleanup_stage_workspace.py": "scripts/orchestration/cleanup_stage_workspace.py",
}
DELEGATED_FILES = {
    "templates/scripts/report_child_completion.py": "scripts/orchestration/report_child_completion.py",
    "templates/scripts/review_completion_inbox.py": "scripts/orchestration/review_completion_inbox.py",
}
MANUAL_FILES = {
    "templates/manual-agent-prompt-template.md": ".codex/manual-agent-prompt-template.md",
}
ALLOWED_LAUNCHERS = {"codex_subagents", "manual_user_launch", "none"}
CURRENT_PROFILE = "balanced-v2.20"
CURRENT_PROFILE_VERSION = 20
SAFE_STAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
MANAGED_SECTION_PATHS = (
    "baseline",
    "orchestration_levels",
    "delegation",
    "stage_limits",
    "stage_sizing",
    "verification_policy",
    "evidence",
    "cost_guard",
    "foundation_guard",
    "stage_state",
    "subagent_model_policy",
    "token_efficiency",
    "documentation",
    "knowledge_graph",
    "handoff",
)
AGENTS_TEMPLATE = "templates/project-agents-managed-block.md"
AGENTS_DESTINATION = "AGENTS.md"
AGENTS_BEGIN = "<!-- ORCHESTRATION-BASELINE:BEGIN -->"
AGENTS_END = "<!-- ORCHESTRATION-BASELINE:END -->"
AGENTS_PROVENANCE = "<!-- orchestration-setup: token-efficiency/v1 -->"
TOKEN_EFFICIENCY_DESTINATION = ".codex/orchestrator.toml"
TOKEN_EFFICIENCY_SPAWN_SOURCE = "templates/subagent-spawn-template.md"
TOKEN_EFFICIENCY_SPAWN_DESTINATION = ".codex/subagent-spawn-template.md"
ACTIVE_STAGE_STATUSES = {"planned", "in_progress", "replan-required"}
TERMINAL_STAGE_STATUSES = {"accepted", "closed", "completed"}
ABSENT_HASH = "absent"
STALE_SECTION_KEYS = {
    "delegation": {
        "requires_explicit_user_spawn_request",
        "subagents_preauthorized_for_complex",
    },
    "verification_policy": {
        "default_tier",
        "e2e_triggers",
    },
    "subagent_model_policy": {
        "mechanical_model",
        "mechanical_reasoning_effort",
        "repetitive_model",
        "repetitive_reasoning_effort",
        "read_heavy_model",
        "read_heavy_reasoning_effort",
        "parallel_support_model",
        "parallel_support_reasoning_effort",
        "implementation_model",
        "implementation_reasoning_effort",
        "high_risk_model",
        "high_risk_reasoning_effort",
        "high_reasoning_triggers",
        "high_reasoning_exclusions",
    },
}
REMOVED_SECTION_PATHS = (
    "verification_policy.level_groups",
    "verification_policy.tier_groups",
    "verification_policy.risk_tag_groups",
    "verification_policy.surface_groups",
)
LOCAL_VALUE_KEYS = {
    "delegation": {"launcher"},
    "handoff": {"current_state_max_lines"},
}
EXISTING_SECTION_OVERRIDE_KEYS = {
    "knowledge_graph": {
        "hooks_allowed",
        "git_hooks_allowed",
        "query_first",
        "freshness_check_required",
        "refresh_policy",
    },
}


def discover_legacy_active_pointers(repo: pathlib.Path, contract: dict) -> set[str]:
    candidates: set[str] = set()
    workspace = contract.get("workspace")
    if isinstance(workspace, dict):
        current = workspace.get("current_stage_id")
        if isinstance(current, str) and current.strip() and current not in {"none", "n/a"}:
            candidates.add(current.strip())
    handoff = repo / ".codex" / "handoff.md"
    if handoff.is_file() and not handoff.is_symlink():
        for match in re.finditer(
            r"^\s*(?:[-*+]\s+)?Current stage id:\s*`?([A-Za-z0-9][A-Za-z0-9._-]{0,127})`?\s*$",
            handoff.read_text(encoding="utf-8"),
            re.MULTILINE | re.IGNORECASE,
        ):
            candidates.add(match.group(1))
        for match in re.finditer(
            r"^\s*(?:[-*+]\s+)?Active"
            r"(?:\s+[A-Za-z][A-Za-z0-9_-]*){0,4}"
            r"\s+(?:stage|epic|parent):\s*"
            r"`?([A-Za-z0-9][A-Za-z0-9._-]{0,127})`?[.;]?\s*$",
            handoff.read_text(encoding="utf-8"),
            re.MULTILINE | re.IGNORECASE,
        ):
            candidates.add(match.group(1))
    return candidates


def discover_legacy_active_stages(repo: pathlib.Path, contract: dict) -> list[str]:
    candidates = discover_legacy_active_pointers(repo, contract)
    for artifact in sorted((repo / ".codex" / "stages").glob("*/artifacts/*.md")):
        if artifact.is_symlink():
            continue
        text = artifact.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---\n", 4)
        if end < 0:
            continue
        frontmatter = text[4:end]
        active = re.search(
            r"^milestone_status:\s*(?:in_progress|replan-required)\s*$",
            frontmatter,
            re.MULTILINE,
        )
        stage = re.search(r"^stage_id:\s*([^\s#]+)\s*$", frontmatter, re.MULTILINE)
        if active and stage:
            candidates.add(stage.group(1).strip("`\"'"))
    return sorted(candidates)


def table_at(document: dict, dotted_path: str) -> dict:
    value: object = document
    for part in dotted_path.split("."):
        if not isinstance(value, dict):
            return {}
        value = value.get(part)
    return value if isinstance(value, dict) else {}


def scalar_values(table: dict) -> dict:
    return {key: value for key, value in table.items() if not isinstance(value, dict)}


def toml_value(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    raise SystemExit(f"unsupported TOML value during contract migration: {value!r}")


def replace_or_append_section(text: str, dotted_path: str, values: dict) -> str:
    lines = text.rstrip().splitlines()
    heading_pattern = re.compile(rf"\s*\[{re.escape(dotted_path)}\]\s*")
    start = next((index for index, line in enumerate(lines) if heading_pattern.fullmatch(line)), None)
    replacement = [f"[{dotted_path}]"]
    replacement.extend(f"{key} = {toml_value(value)}" for key, value in values.items())
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(replacement)
    else:
        end = start + 1
        while end < len(lines) and not re.fullmatch(r"\s*\[[^]]+\]\s*", lines[end]):
            end += 1
        if end < len(lines) and replacement and replacement[-1].strip():
            replacement.append("")
        lines[start:end] = replacement
    return "\n".join(lines).rstrip() + "\n"


def remove_section(text: str, dotted_path: str) -> str:
    lines = text.rstrip().splitlines()
    heading_pattern = re.compile(rf"\s*\[{re.escape(dotted_path)}\]\s*")
    start = next(
        (index for index, line in enumerate(lines) if heading_pattern.fullmatch(line)),
        None,
    )
    if start is None:
        return text
    end = start + 1
    while end < len(lines) and not re.fullmatch(r"\s*\[[^]]+\]\s*", lines[end]):
        end += 1
    del lines[start:end]
    while start < len(lines) and start > 0 and not lines[start - 1].strip() and not lines[start].strip():
        del lines[start]
    return "\n".join(lines).rstrip() + "\n"


def ensure_root_role(text: str) -> str:
    lines = text.rstrip().splitlines()
    first_heading = next(
        (index for index, line in enumerate(lines) if re.fullmatch(r"\s*\[[^]]+\]\s*", line)),
        len(lines),
    )
    root_role = re.compile(r'\s*role\s*=\s*"[^"]*"\s*')
    for index in range(first_heading):
        if root_role.fullmatch(lines[index]):
            lines[index] = 'role = "orchestrator-stage"'
            return "\n".join(lines).rstrip() + "\n"
    insert_at = 0
    while insert_at < first_heading and (
        not lines[insert_at].strip() or lines[insert_at].lstrip().startswith("#")
    ):
        insert_at += 1
    lines[insert_at:insert_at] = ['role = "orchestrator-stage"', ""]
    return "\n".join(lines).rstrip() + "\n"


def canonical_contract() -> dict:
    baseline = tomllib.loads(
        (SKILL_DIR / "templates" / "baseline.toml").read_text(encoding="utf-8")
    )
    return {
        "baseline": {
            "profile": baseline.pop("profile"),
            "source_skill": baseline.pop("source_skill"),
        },
        **baseline,
    }


def contract_migration_plan(
    repo: pathlib.Path,
    *,
    legacy_active_stage_id: str | None = None,
) -> tuple[pathlib.Path, str, str, str, bool]:
    path = repo / ".codex" / "orchestrator.toml"
    if not path.is_file() or path.is_symlink():
        raise SystemExit("--migrate-contract requires a regular .codex/orchestrator.toml")
    before = path.read_text(encoding="utf-8")
    contract = tomllib.loads(before)
    baseline = contract.get("baseline")
    profile = baseline.get("profile") if isinstance(baseline, dict) else None
    profile_match = re.fullmatch(r"balanced-v2\.(\d+)", profile or "")
    if (
        profile_match is None
        or int(profile_match.group(1)) > CURRENT_PROFILE_VERSION
        or int(profile_match.group(1)) < 19
    ):
        raise SystemExit(
            f"--migrate-contract supports balanced-v2.19 through "
            f"{CURRENT_PROFILE}; found {profile!r}"
        )
    source_profile = str(profile)
    existing_sizing = contract.get("stage_sizing")
    candidates: set[str] = set()
    if source_profile != CURRENT_PROFILE:
        candidates.update(discover_legacy_active_stages(repo, contract))
    if source_profile != CURRENT_PROFILE and isinstance(existing_sizing, dict):
        existing_legacy = existing_sizing.get("legacy_active_stage_id")
        if isinstance(existing_legacy, str) and existing_legacy.strip():
            candidates.add(existing_legacy.strip())
    if legacy_active_stage_id is not None:
        if SAFE_STAGE_ID.fullmatch(legacy_active_stage_id) is None:
            raise SystemExit("--legacy-active-stage-id must be a safe stage id")
        if legacy_active_stage_id not in candidates:
            discovered = ", ".join(sorted(candidates)) or "none"
            raise SystemExit(
                f"--legacy-active-stage-id {legacy_active_stage_id!r} is not one of "
                f"the discovered candidates: {discovered}"
            )
    elif len(candidates) > 1:
        raise SystemExit(f"ambiguous legacy active stages: {', '.join(sorted(candidates))}")
    current_legacy = (
        existing_sizing.get("legacy_active_stage_id", "")
        if isinstance(existing_sizing, dict)
        else ""
    )
    legacy = (
        legacy_active_stage_id or next(iter(candidates), "")
        if source_profile != CURRENT_PROFILE
        else str(current_legacy)
    )
    canonical = canonical_contract()
    after = ensure_root_role(before)
    for dotted_path in MANAGED_SECTION_PATHS:
        old_values = scalar_values(table_at(contract, dotted_path))
        canonical_values = scalar_values(table_at(canonical, dotted_path))
        merged = dict(old_values)
        override_keys = EXISTING_SECTION_OVERRIDE_KEYS.get(dotted_path)
        if old_values and override_keys is not None:
            merged.update(
                (key, value)
                for key, value in canonical_values.items()
                if key in override_keys
            )
        else:
            merged.update(canonical_values)
        for key in STALE_SECTION_KEYS.get(dotted_path, set()):
            merged.pop(key, None)
        for key in LOCAL_VALUE_KEYS.get(dotted_path, set()):
            if key in old_values:
                merged[key] = old_values[key]
        if dotted_path == "stage_sizing":
            merged["legacy_active_stage_id"] = legacy
        after = replace_or_append_section(after, dotted_path, merged)
    for dotted_path in REMOVED_SECTION_PATHS:
        after = remove_section(after, dotted_path)
    tomllib.loads(after)
    return path, after, legacy, source_profile, after != before


def token_efficiency_contract_plan(repo: pathlib.Path) -> tuple[pathlib.Path, bytes]:
    path = repo / TOKEN_EFFICIENCY_DESTINATION
    if not path.is_file() or path.is_symlink():
        raise SystemExit(
            "--token-efficiency-only requires a regular .codex/orchestrator.toml"
        )
    before = path.read_bytes()
    try:
        text = before.decode("utf-8")
        contract = tomllib.loads(text)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"cannot parse {path}: {exc}") from exc
    canonical = scalar_values(table_at(canonical_contract(), "token_efficiency"))
    existing = contract.get("token_efficiency")
    if existing is not None:
        if not isinstance(existing, dict):
            raise SystemExit(
                "--token-efficiency-only refuses a non-canonical existing "
                "[token_efficiency] section"
            )
        unknown = set(existing) - set(canonical)
        changed = {
            key for key, value in existing.items() if canonical.get(key) != value
        }
        if unknown or changed:
            raise SystemExit(
                "--token-efficiency-only refuses a non-canonical existing "
                "[token_efficiency] section"
            )
        if existing == canonical:
            return path, before
        after = replace_or_append_section(text, "token_efficiency", canonical)
        tomllib.loads(after)
        return path, after.encode("utf-8")
    section = "[token_efficiency]\n" + "\n".join(
        f"{key} = {toml_value(value)}" for key, value in canonical.items()
    ) + "\n"
    if not text:
        after = section
    elif text.endswith("\n\n"):
        after = text + section
    elif text.endswith("\n"):
        after = text + "\n" + section
    else:
        after = text + "\n\n" + section
    tomllib.loads(after)
    return path, after.encode("utf-8")


def launcher_for(repo: pathlib.Path) -> str:
    contract_path = repo / ".codex" / "orchestrator.toml"
    if not contract_path.exists():
        return "codex_subagents"
    try:
        with contract_path.open("rb") as handle:
            contract = tomllib.load(handle)
    except Exception as exc:  # noqa: BLE001 - report malformed target config.
        raise SystemExit(f"cannot parse {contract_path}: {exc}") from exc
    launcher = str((contract.get("delegation") or {}).get("launcher", "")).strip()
    if not launcher:
        return "codex_subagents"
    if launcher not in ALLOWED_LAUNCHERS:
        raise SystemExit(f"unsupported delegation.launcher: {launcher}")
    return launcher


def files_for(launcher: str) -> dict[str, str]:
    files = dict(COMMON_FILES)
    if launcher in {"codex_subagents", "manual_user_launch"}:
        files.update(DELEGATED_FILES)
    if launcher == "manual_user_launch":
        files.update(MANUAL_FILES)
    return files


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git_read(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"Git preflight failed: {detail}")
    return result.stdout.strip()


def git_snapshot(repo: pathlib.Path) -> tuple[str, str]:
    head = git_read(repo, "rev-parse", "HEAD")
    status = git_read(repo, "status", "--porcelain=v1", "--untracked-files=all")
    return head, status


def active_work(repo: pathlib.Path) -> list[str]:
    contract_path = repo / ".codex" / "orchestrator.toml"
    try:
        contract = tomllib.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        contract = {}
    legacy_pointers = discover_legacy_active_pointers(repo, contract)
    findings: list[str] = []
    stage_statuses: dict[str, str] = {}
    for manifest in sorted((repo / ".codex" / "stages").glob("*/stage-manifest.json")):
        if manifest.is_symlink():
            findings.append(f"symlink:{manifest.relative_to(repo)}")
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            findings.append(f"unreadable:{manifest.relative_to(repo)}")
            continue
        status = payload.get("status") if isinstance(payload, dict) else None
        if isinstance(status, str):
            stage_statuses[manifest.parent.name] = status
        if status in ACTIVE_STAGE_STATUSES:
            findings.append(f"active-stage:{payload.get('stage_id', manifest.parent.name)}")
        streams = payload.get("stream_artifacts") if isinstance(payload, dict) else None
        if status in ACTIVE_STAGE_STATUSES and isinstance(streams, list) and streams:
            findings.append(f"child-streams:{manifest.parent.name}")
    findings.extend(
        f"legacy-stage:{item}"
        for item in legacy_pointers
        if stage_statuses.get(item) not in TERMINAL_STAGE_STATUSES
    )
    for events in sorted((repo / ".codex" / "stages").glob("*/events.ndjson")):
        inactive = stage_statuses.get(events.parent.name) in TERMINAL_STAGE_STATUSES
        if not inactive and (
            events.is_symlink() or (events.is_file() and events.stat().st_size)
        ):
            findings.append(f"child-events:{events.parent.name}")
    inbox = contract.get("completion_inbox")
    if isinstance(inbox, dict) and isinstance(inbox.get("events_file"), str):
        events_path = pathlib.Path(inbox["events_file"])
        if inbox.get("scope") == "git_common_dir":
            common = pathlib.Path(git_read(repo, "rev-parse", "--git-common-dir"))
            if not common.is_absolute():
                common = (repo / common).resolve()
            events_path = common / events_path
        else:
            events_path = repo / events_path
        inactive = stage_statuses.get(events_path.parent.name) in TERMINAL_STAGE_STATUSES
        if not inactive and (
            events_path.is_symlink()
            or (events_path.is_file() and events_path.stat().st_size)
        ):
            findings.append("child-events:configured-inbox")
    return sorted(set(findings))


def require_safe_repo(
    raw_repo: pathlib.Path, *, allow_active_stage: bool = False
) -> pathlib.Path:
    if raw_repo.is_symlink():
        raise SystemExit(f"target repo may not be a symlink: {raw_repo}")
    repo = raw_repo.resolve()
    if not repo.is_dir():
        raise SystemExit(f"repo not found: {repo}")
    top = pathlib.Path(git_read(repo, "rev-parse", "--show-toplevel")).resolve()
    if top != repo:
        raise SystemExit(f"target must be the Git worktree root: {repo}")
    if git_read(repo, "rev-parse", "--is-bare-repository") != "false":
        raise SystemExit("target must be a regular Git worktree")
    _, status = git_snapshot(repo)
    if status:
        raise SystemExit("sync requires a clean Git worktree")
    busy = active_work(repo)
    if allow_active_stage:
        busy = [
            item
            for item in busy
            if item.startswith("symlink:") or item.startswith("unreadable:")
        ]
    if busy:
        raise SystemExit(f"sync refuses active or child work: {', '.join(busy)}")
    return repo


def require_safe_destination(repo: pathlib.Path, destination: pathlib.Path) -> None:
    try:
        destination.relative_to(repo)
    except ValueError as exc:
        raise SystemExit(f"destination escapes target repo: {destination}") from exc
    current = destination
    while current != repo:
        if current.is_symlink():
            raise SystemExit(f"destination may not traverse a symlink: {destination}")
        current = current.parent


def managed_agents_text(existing: str, managed: str, *, adopt: bool) -> tuple[str | None, str]:
    begin_count = existing.count(AGENTS_BEGIN)
    end_count = existing.count(AGENTS_END)
    wrapped = f"{AGENTS_BEGIN}\n{managed.rstrip()}\n{AGENTS_END}"
    if not begin_count and not end_count:
        if existing and not adopt:
            return None, "deferred_first_adoption"
        separator = "" if not existing or existing.endswith("\n\n") else "\n"
        return f"{existing}{separator}{wrapped}\n", "adopted" if existing else "created"
    if begin_count != 1 or end_count != 1:
        raise SystemExit("AGENTS.md has duplicate or incomplete managed markers")
    start = existing.index(AGENTS_BEGIN)
    end = existing.index(AGENTS_END, start) + len(AGENTS_END)
    current = existing[start + len(AGENTS_BEGIN) : end - len(AGENTS_END)].strip()
    if current and not current.startswith(AGENTS_PROVENANCE):
        return None, "deferred_custom_overlap"
    after = existing[:start] + wrapped + existing[end:]
    return after, "updated" if after != existing else "current"


def preimage(path: pathlib.Path) -> tuple[str, bytes | None, int | None]:
    if not path.exists():
        return ABSENT_HASH, None, None
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"managed destination must be a regular file: {path}")
    payload = path.read_bytes()
    return sha256_bytes(payload), payload, path.stat().st_mode


def make_entry(repo: pathlib.Path, relative: str, payload: bytes, mode: int) -> dict:
    destination = repo / relative
    require_safe_destination(repo, destination)
    before_hash, before_bytes, before_mode = preimage(destination)
    return {
        "relative": relative,
        "path": destination,
        "before_hash": before_hash,
        "before_bytes": before_bytes,
        "before_mode": before_mode,
        "after_hash": sha256_bytes(payload),
        "after_bytes": payload,
        "after_mode": mode,
    }


def plan_digest(head: str, entries: list[dict]) -> str:
    payload = {
        "head": head,
        "entries": [
            {
                "path": item["relative"],
                "preimage": item["before_hash"],
                "postimage": item["after_hash"],
                "mode": item["after_mode"] & 0o777,
            }
            for item in entries
        ],
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def atomic_replace(path: pathlib.Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=f".{path.name}.", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode & 0o777)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_transaction(repo: pathlib.Path, entries: list[dict], expected_head: str) -> None:
    head, status = git_snapshot(repo)
    if head != expected_head or status:
        raise SystemExit("Git HEAD/status changed after planning; no files written")
    created_dirs: set[pathlib.Path] = set()
    replaced: list[dict] = []
    fail_after_raw = os.environ.get("ORCHESTRATION_SYNC_TEST_FAIL_AFTER", "")
    fail_after = int(fail_after_raw) if fail_after_raw else None
    try:
        for item in entries:
            parent = item["path"].parent
            missing: list[pathlib.Path] = []
            cursor = parent
            while cursor != repo and not cursor.exists():
                missing.append(cursor)
                cursor = cursor.parent
            parent.mkdir(parents=True, exist_ok=True)
            created_dirs.update(missing)
            replaced.append(item)
            atomic_replace(item["path"], item["after_bytes"], item["after_mode"])
            if fail_after is not None and len(replaced) >= fail_after:
                raise OSError("injected transaction failure")
    except BaseException as exc:
        rollback_errors: list[str] = []
        for item in reversed(replaced):
            try:
                if item["before_bytes"] is None:
                    item["path"].unlink(missing_ok=True)
                else:
                    atomic_replace(
                        item["path"], item["before_bytes"], item["before_mode"]
                    )
            except OSError as rollback_exc:
                rollback_errors.append(f"{item['relative']}: {rollback_exc}")
        for directory in sorted(created_dirs, key=lambda value: len(value.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        detail = f"; rollback errors: {', '.join(rollback_errors)}" if rollback_errors else ""
        raise SystemExit(f"sync failed and rolled back all preimages: {exc}{detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=pathlib.Path)
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    parser.add_argument(
        "--migrate-contract",
        action="store_true",
        help="plan/apply a future-only balanced-v2 contract reconciliation to balanced-v2.20",
    )
    parser.add_argument(
        "--legacy-active-stage-id",
        help=(
            "explicitly select one discovered legacy active-stage candidate when "
            "migration evidence is ambiguous"
        ),
    )
    parser.add_argument(
        "--adopt-agents-block",
        action="store_true",
        help="explicitly add the managed block beside existing project AGENTS rules",
    )
    parser.add_argument(
        "--reviewed-plan-hash",
        help="exact plan_hash from a reviewed dry-run; required with --apply",
    )
    parser.add_argument(
        "--token-efficiency-only",
        action="store_true",
        help=(
            "sync only the exact native spawn template and an absent canonical "
            "[token_efficiency] section"
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the deterministic copy plan without writing")
    mode.add_argument("--apply", action="store_true", help="apply an exactly reviewed copy plan")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        args.dry_run = True
    if args.apply and not args.reviewed_plan_hash:
        raise SystemExit("--apply requires --reviewed-plan-hash from a dry-run")
    if args.dry_run and args.reviewed_plan_hash:
        raise SystemExit("--reviewed-plan-hash is only valid with --apply")
    if args.token_efficiency_only and (
        args.force
        or args.migrate_contract
        or args.legacy_active_stage_id
        or args.adopt_agents_block
    ):
        raise SystemExit(
            "--token-efficiency-only cannot be combined with --force, "
            "--migrate-contract, --legacy-active-stage-id, or --adopt-agents-block"
        )
    repo = require_safe_repo(
        args.repo.absolute(),
        allow_active_stage=args.token_efficiency_only and args.dry_run,
    )
    if args.migrate_contract and not args.force:
        raise SystemExit("--migrate-contract requires --force so support files and contract stay aligned")
    if args.legacy_active_stage_id and not args.migrate_contract:
        raise SystemExit("--legacy-active-stage-id requires --migrate-contract")

    if args.token_efficiency_only:
        contract_path, contract_after = token_efficiency_contract_plan(repo)
        spawn_source = SKILL_DIR / TOKEN_EFFICIENCY_SPAWN_SOURCE
        if not spawn_source.is_file() or spawn_source.is_symlink():
            raise SystemExit(f"template missing or unsafe: {spawn_source}")
        entries = []
        contract_before = contract_path.read_bytes()
        if contract_after != contract_before:
            entries.append(
                make_entry(
                    repo,
                    TOKEN_EFFICIENCY_DESTINATION,
                    contract_after,
                    contract_path.stat().st_mode,
                )
            )
        spawn_payload = spawn_source.read_bytes()
        spawn_path = repo / TOKEN_EFFICIENCY_SPAWN_DESTINATION
        if spawn_path.is_symlink():
            raise SystemExit(f"managed destination may not be a symlink: {spawn_path}")
        if spawn_path.exists() and not spawn_path.is_file():
            raise SystemExit(f"managed destination must be a regular file: {spawn_path}")
        spawn_before = spawn_path.read_bytes() if spawn_path.is_file() else None
        if spawn_before != spawn_payload:
            mode_bits = spawn_path.stat().st_mode if spawn_path.exists() else spawn_source.stat().st_mode
            entries.append(
                make_entry(
                    repo,
                    TOKEN_EFFICIENCY_SPAWN_DESTINATION,
                    spawn_payload,
                    mode_bits,
                )
            )
        head, status = git_snapshot(repo)
        if status:
            raise SystemExit("sync requires a clean Git worktree")
        entries.sort(key=lambda item: item["relative"])
        digest = plan_digest(head, entries)
        if args.apply:
            if args.reviewed_plan_hash != digest:
                raise SystemExit(
                    f"reviewed plan hash does not match current HEAD/preimages: expected {digest}"
                )
            apply_transaction(repo, entries, head)
        print(f"mode: {'dry-run' if args.dry_run else 'apply'}")
        print("scope: token-efficiency-only")
        print(f"head: {head}")
        print(f"plan_hash: {digest}")
        print(f"preimages: {len(entries)}")
        for item in entries:
            print(f"@ {item['relative']} {item['before_hash']} -> {item['after_hash']}")
        return 0

    launcher = launcher_for(repo)
    migration = (
        contract_migration_plan(
            repo, legacy_active_stage_id=args.legacy_active_stage_id
        )
        if args.migrate_contract
        else None
    )
    sources = [(SKILL_DIR / src_rel, dst_rel) for src_rel, dst_rel in files_for(launcher).items()]
    missing_templates = [str(src) for src, _ in sources if not src.is_file()]
    if missing_templates:
        raise SystemExit(f"template missing: {', '.join(missing_templates)}")
    agents_template = SKILL_DIR / AGENTS_TEMPLATE
    if not agents_template.is_file() or agents_template.is_symlink():
        raise SystemExit(f"template missing or unsafe: {agents_template}")

    head, status = git_snapshot(repo)
    if status:
        raise SystemExit("sync requires a clean Git worktree")
    entries: list[dict] = []
    copied: list[str] = []
    skipped: list[str] = []
    for src, dst_rel in sources:
        dst = repo / dst_rel
        require_safe_destination(repo, dst)
        if src.is_symlink():
            raise SystemExit(f"template may not be a symlink: {src}")
        if dst.exists() and not args.force:
            if dst.is_symlink() or not dst.is_file():
                raise SystemExit(f"managed destination must be a regular file: {dst}")
            skipped.append(dst_rel)
            continue
        mode_bits = src.stat().st_mode
        if dst.suffix in {".py", ".sh"}:
            mode_bits |= 0o755
        entries.append(make_entry(repo, dst_rel, src.read_bytes(), mode_bits))
        copied.append(dst_rel)

    if migration is not None:
        contract_path, migrated_text, _, _, changed = migration
        if changed:
            relative = contract_path.relative_to(repo).as_posix()
            entries = [item for item in entries if item["relative"] != relative]
            entries.append(make_entry(repo, relative, migrated_text.encode(), contract_path.stat().st_mode))

    agents_path = repo / AGENTS_DESTINATION
    require_safe_destination(repo, agents_path)
    agents_existing = agents_path.read_text(encoding="utf-8") if agents_path.is_file() and not agents_path.is_symlink() else ""
    if agents_path.is_symlink() or (agents_path.exists() and not agents_path.is_file()):
        raise SystemExit(f"managed destination must be a regular file: {agents_path}")
    agents_after, agents_action = managed_agents_text(
        agents_existing,
        agents_template.read_text(encoding="utf-8"),
        adopt=args.adopt_agents_block,
    )
    if agents_after is not None and agents_after != agents_existing:
        mode_bits = agents_path.stat().st_mode if agents_path.exists() else 0o100644
        entries.append(make_entry(repo, AGENTS_DESTINATION, agents_after.encode(), mode_bits))

    entries.sort(key=lambda item: item["relative"])
    digest = plan_digest(head, entries)
    if args.apply:
        if args.reviewed_plan_hash != digest:
            raise SystemExit(
                f"reviewed plan hash does not match current HEAD/preimages: expected {digest}"
            )
        apply_transaction(repo, entries, head)

    print(f"mode: {'dry-run' if args.dry_run else 'apply'}")
    print(f"launcher: {launcher}")
    print(f"head: {head}")
    print(f"plan_hash: {digest}")
    print(f"agents_action: {agents_action}")
    if migration is not None:
        _, _, legacy, source_profile, changed = migration
        if source_profile == CURRENT_PROFILE:
            print(f"contract_profile: {CURRENT_PROFILE} (reconciled)")
        else:
            print(f"contract_profile: {source_profile} -> {CURRENT_PROFILE}")
        print(f"contract_changed: {'yes' if changed else 'no'}")
        print(f"legacy_active_stage_id: {legacy or 'none'}")
    print(f"copied: {len(copied)}")
    for rel in copied:
        print(f"+ {rel}")
    print(f"skipped_existing: {len(skipped)}")
    for rel in skipped:
        print(f"= {rel}")
    print(f"preimages: {len(entries)}")
    for item in entries:
        print(f"@ {item['relative']} {item['before_hash']} -> {item['after_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
