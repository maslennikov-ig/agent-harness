"""Read-only stage telemetry payloads for the orchestration console."""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


METRIC_KEYS = (
    "worker_wall_seconds",
    "queue_seconds",
    "review_rounds",
    "p0_findings",
    "p1_findings",
    "integration_seconds",
    "rebase_seconds",
)
TELEMETRY_SCHEMA_V1 = "stage-telemetry/v1"
TELEMETRY_SCHEMA_V2 = "stage-telemetry/v2"
TELEMETRY_SCHEMA_V3 = "stage-telemetry/v3"
TELEMETRY_SCHEMA_VERSION = TELEMETRY_SCHEMA_V3
SUPPORTED_TELEMETRY_SCHEMAS = {
    TELEMETRY_SCHEMA_V1,
    TELEMETRY_SCHEMA_V2,
    TELEMETRY_SCHEMA_V3,
}
STAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
VERIFICATION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")
RFC3339_UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
STAGE_STATUSES = {"planned", "in_progress", "blocked", "accepted", "closed"}
COVERAGE_VALUES = {"complete", "partial", "unavailable"}
TOP_LEVEL_KEYS_V1 = {
    "schema_version",
    "stage_id",
    "updated_at",
    "status",
    "metrics",
    "verification",
    "coverage",
}
TOP_LEVEL_KEYS_V2 = TOP_LEVEL_KEYS_V1 | {"delegation"}
V3_FIELDS = {
    "orchestration_level",
    "source_digest",
    "verification_fingerprint",
    "verification_decision",
    "reuse_count",
    "stage_count_window",
    "product_commit_count",
    "orchestration_commit_count",
    "proof_commit_count",
    "repeated_verification_count",
    "bookkeeping_write_count",
    "anomalies",
    "replan_status",
}
TOP_LEVEL_KEYS_V3 = TOP_LEVEL_KEYS_V2 | V3_FIELDS
METRICS_KEYS = {
    "worker_wall_seconds",
    "queue_seconds",
    "review_rounds",
    "findings",
    "integration_seconds",
    "rebase_seconds",
}
FINDING_KEYS = {"p0", "p1"}
COVERAGE_KEYS = {"worker_wall", "queue", "verification", "review", "integration", "rebase"}
DELEGATION_KEYS = {
    "decision",
    "subagent_count",
    "reasons",
    "agent_wall_seconds",
    "coordination_seconds",
}
DELEGATION_DECISIONS = {"local", "worker", "parallel"}
DELEGATION_REASONS = {
    "parallel_latency",
    "context_isolation",
    "specialist_capability",
    "write_isolation",
}
ORCHESTRATION_LEVELS = {
    "inner_loop",
    "slice_acceptance",
    "integration",
    "release",
}
VERIFICATION_DECISIONS = {"run", "reuse"}
REPLAN_STATUSES = {"none", "replan_required"}
SIGNAL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


class TelemetryValidationError(ValueError):
    """Raised when a sidecar is not an exact supported stage telemetry document."""

    def __init__(self, message: str, *, code: str = "invalid_schema") -> None:
        super().__init__(message)
        self.code = code


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TelemetryValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TelemetryValidationError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        missing = ", ".join(sorted(expected - actual))
        unknown = ", ".join(sorted(actual - expected))
        parts = [
            f"missing: {missing}" if missing else "",
            f"unknown: {unknown}" if unknown else "",
        ]
        detail = "; ".join(part for part in parts if part)
        raise TelemetryValidationError(f"{label} has invalid keys ({detail})")
    return value


def _nullable_duration(value: Any, label: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise TelemetryValidationError(f"{label} must be a non-negative finite number or null")


def _nullable_count(value: Any, label: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetryValidationError(f"{label} must be a non-negative integer or null")


def _validate_updated_at(value: Any) -> None:
    if not isinstance(value, str) or not RFC3339_UTC_PATTERN.fullmatch(value):
        raise TelemetryValidationError("updated_at must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as exc:
        raise TelemetryValidationError("updated_at must be an RFC3339 UTC timestamp") from exc
    if parsed.tzinfo is None:
        raise TelemetryValidationError("updated_at must include a UTC timezone")


def _validate_metrics(value: Any) -> None:
    metrics = _exact_keys(value, METRICS_KEYS, "metrics")
    _nullable_duration(metrics["worker_wall_seconds"], "metrics.worker_wall_seconds")
    _nullable_duration(metrics["queue_seconds"], "metrics.queue_seconds")
    _nullable_count(metrics["review_rounds"], "metrics.review_rounds")
    _nullable_duration(metrics["integration_seconds"], "metrics.integration_seconds")
    _nullable_duration(metrics["rebase_seconds"], "metrics.rebase_seconds")
    findings = _exact_keys(metrics["findings"], FINDING_KEYS, "metrics.findings")
    _nullable_count(findings["p0"], "metrics.findings.p0")
    _nullable_count(findings["p1"], "metrics.findings.p1")


def _validate_verification(value: Any) -> None:
    if not isinstance(value, dict):
        raise TelemetryValidationError("verification must be an object")
    for name, duration in value.items():
        if not isinstance(name, str) or not VERIFICATION_NAME_PATTERN.fullmatch(name):
            raise TelemetryValidationError("verification names must be short printable identifiers")
        _nullable_duration(duration, f"verification.{name}")


def _validate_coverage(value: Any) -> None:
    coverage = _exact_keys(value, COVERAGE_KEYS, "coverage")
    for key, status in coverage.items():
        if not isinstance(status, str) or status not in COVERAGE_VALUES:
            raise TelemetryValidationError(f"coverage.{key} must be complete, partial, or unavailable")


def empty_delegation() -> dict[str, Any]:
    """Return the stable v1 compatibility shape without inventing observations."""
    return {
        "decision": None,
        "subagent_count": None,
        "reasons": [],
        "agent_wall_seconds": None,
        "coordination_seconds": None,
    }


def _validate_delegation(value: Any) -> None:
    delegation = _exact_keys(value, DELEGATION_KEYS, "delegation")
    decision = delegation["decision"]
    if decision is not None and (not isinstance(decision, str) or decision not in DELEGATION_DECISIONS):
        raise TelemetryValidationError("delegation.decision must be local, worker, parallel, or null")
    _nullable_count(delegation["subagent_count"], "delegation.subagent_count")
    reasons = delegation["reasons"]
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) or reason not in DELEGATION_REASONS for reason in reasons
    ):
        raise TelemetryValidationError("delegation.reasons contains an unsupported reason")
    if len(reasons) != len(set(reasons)):
        raise TelemetryValidationError("delegation.reasons must not contain duplicates")
    _nullable_duration(delegation["agent_wall_seconds"], "delegation.agent_wall_seconds")
    _nullable_duration(delegation["coordination_seconds"], "delegation.coordination_seconds")


def _nullable_signal(value: Any, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not SIGNAL_PATTERN.fullmatch(value):
        raise TelemetryValidationError(f"{label} must be a short signal identifier or null")


def _validate_v3(value: dict[str, Any]) -> None:
    level = value["orchestration_level"]
    if level is not None and level not in ORCHESTRATION_LEVELS:
        raise TelemetryValidationError(
            "orchestration_level must be inner_loop, slice_acceptance, integration, release, or null"
        )
    _nullable_signal(value["source_digest"], "source_digest")
    _nullable_signal(value["verification_fingerprint"], "verification_fingerprint")
    decision = value["verification_decision"]
    if decision is not None and decision not in VERIFICATION_DECISIONS:
        raise TelemetryValidationError("verification_decision must be run, reuse, or null")
    for field in (
        "reuse_count",
        "stage_count_window",
        "product_commit_count",
        "orchestration_commit_count",
        "proof_commit_count",
        "repeated_verification_count",
        "bookkeeping_write_count",
    ):
        _nullable_count(value[field], field)
    anomalies = value["anomalies"]
    if not isinstance(anomalies, list) or any(
        not isinstance(anomaly, str) or not SIGNAL_PATTERN.fullmatch(anomaly)
        for anomaly in anomalies
    ):
        raise TelemetryValidationError("anomalies must be a list of short signal identifiers")
    if len(anomalies) != len(set(anomalies)):
        raise TelemetryValidationError("anomalies must not contain duplicates")
    replan_status = value["replan_status"]
    if replan_status is not None and replan_status not in REPLAN_STATUSES:
        raise TelemetryValidationError("replan_status must be none, replan_required, or null")


def empty_totals() -> dict[str, Any]:
    """Return the stable empty aggregate contract without treating null as zero."""
    return {key: None for key in METRIC_KEYS} | {
        "verification_seconds": {},
        "subagent_count": None,
        "agent_wall_seconds": None,
        "coordination_seconds": None,
        "delegation_decisions": {},
        "delegation_reasons": {},
    }


def _reject_json_constant(value: str) -> None:
    raise TelemetryValidationError(f"invalid JSON value: {value}")


def parse_stage_telemetry(path: Path, *, stage_id: str) -> dict[str, Any]:
    """Read a strict v1/v2/v3 sidecar without inferring missing observations."""
    if not isinstance(stage_id, str) or not STAGE_ID_PATTERN.fullmatch(stage_id):
        raise TelemetryValidationError("stage id is not a supported telemetry directory name")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryValidationError("telemetry sidecar is not valid JSON", code="malformed_json") from exc
    if not isinstance(payload, dict):
        raise TelemetryValidationError("telemetry must be an object")
    schema_version = payload.get("schema_version")
    if schema_version not in SUPPORTED_TELEMETRY_SCHEMAS:
        raise TelemetryValidationError("unsupported stage telemetry schema", code="unsupported_schema")
    if schema_version == TELEMETRY_SCHEMA_V3 and set(payload) == TOP_LEVEL_KEYS_V1:
        # Preserve the legacy warning classification for a v1 document that only
        # relabels itself as a future schema instead of implementing that schema.
        raise TelemetryValidationError("unsupported stage telemetry schema", code="unsupported_schema")
    expected_keys = {
        TELEMETRY_SCHEMA_V1: TOP_LEVEL_KEYS_V1,
        TELEMETRY_SCHEMA_V2: TOP_LEVEL_KEYS_V2,
        TELEMETRY_SCHEMA_V3: TOP_LEVEL_KEYS_V3,
    }[schema_version]
    document = _exact_keys(payload, expected_keys, "telemetry")
    if document["stage_id"] != stage_id:
        raise TelemetryValidationError("stage telemetry sidecar does not match its stage directory")
    _validate_updated_at(document["updated_at"])
    if not isinstance(document["status"], str) or document["status"] not in STAGE_STATUSES:
        raise TelemetryValidationError("status is not supported by stage telemetry")
    _validate_metrics(document["metrics"])
    _validate_verification(document["verification"])
    _validate_coverage(document["coverage"])
    if schema_version in {TELEMETRY_SCHEMA_V2, TELEMETRY_SCHEMA_V3}:
        _validate_delegation(document["delegation"])
    if schema_version == TELEMETRY_SCHEMA_V3:
        _validate_v3(document)
    return payload


def _contained(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _repo_identity(repo: Path) -> str:
    """Use the Git common directory where available to avoid duplicate worktrees."""
    resolved = repo.resolve()
    git = resolved / ".git"
    if git.is_dir():
        return str(git.resolve())
    if not git.is_file():
        return str(resolved)
    try:
        line = git.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return str(resolved)
    if not line.startswith("gitdir: "):
        return str(resolved)
    raw_git_dir = Path(line.removeprefix("gitdir: ").strip())
    git_dir = raw_git_dir if raw_git_dir.is_absolute() else (resolved / raw_git_dir)
    try:
        git_dir = git_dir.resolve()
    except (OSError, RuntimeError):
        return str(resolved)
    common_dir_file = git_dir / "commondir"
    if common_dir_file.is_file():
        try:
            common_raw = common_dir_file.read_text(encoding="utf-8", errors="replace").strip()
            if common_raw:
                common_dir = Path(common_raw)
                return str((common_dir if common_dir.is_absolute() else git_dir / common_dir).resolve())
        except (OSError, RuntimeError):
            pass
    if git_dir.parent.name == "worktrees":
        return str(git_dir.parent.parent)
    return str(git_dir)


def _unique_repos(repos: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for repo in repos:
        try:
            resolved = Path(repo).resolve()
        except (OSError, RuntimeError):
            continue
        if not resolved.is_dir():
            continue
        identity = _repo_identity(resolved)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(resolved)
    return sorted(result, key=lambda path: (path.name.lower(), str(path)))


def _warning(repo: Path, stage_id: str, kind: str) -> dict[str, str]:
    return {"repo": repo.name, "stage_id": stage_id, "kind": kind}


def discover_stage_sidecars(repo: Path) -> tuple[list[tuple[str, Path]], list[dict[str, str]]]:
    """Discover only direct non-symlink `<stage>/telemetry.json` children."""
    stage_root = repo / ".codex" / "stages"
    if not stage_root.exists():
        return [], []
    if stage_root.is_symlink() or not stage_root.is_dir():
        return [], [_warning(repo, "stages", "unsafe_path")]
    try:
        resolved_root = stage_root.resolve()
    except (OSError, RuntimeError):
        return [], [_warning(repo, "stages", "unsafe_path")]
    if not _contained(resolved_root, repo.resolve()):
        return [], [_warning(repo, "stages", "unsafe_path")]

    sidecars: list[tuple[str, Path]] = []
    warnings: list[dict[str, str]] = []
    try:
        entries = sorted(stage_root.iterdir(), key=lambda path: path.name)
    except (OSError, RuntimeError):
        return [], [_warning(repo, "stages", "unreadable_path")]
    for stage_dir in entries:
        stage_id = stage_dir.name
        if stage_dir.is_symlink():
            warnings.append(_warning(repo, stage_id, "unsafe_path"))
            continue
        if not stage_dir.is_dir():
            continue
        try:
            resolved_stage = stage_dir.resolve()
        except (OSError, RuntimeError):
            warnings.append(_warning(repo, stage_id, "unsafe_path"))
            continue
        if resolved_stage.parent != resolved_root:
            warnings.append(_warning(repo, stage_id, "unsafe_path"))
            continue
        sidecar = stage_dir / "telemetry.json"
        if not sidecar.exists():
            continue
        if sidecar.is_symlink() or not sidecar.is_file():
            warnings.append(_warning(repo, stage_id, "unsafe_path"))
            continue
        try:
            resolved_sidecar = sidecar.resolve()
        except (OSError, RuntimeError):
            warnings.append(_warning(repo, stage_id, "unsafe_path"))
            continue
        if resolved_sidecar.parent != resolved_stage:
            warnings.append(_warning(repo, stage_id, "unsafe_path"))
            continue
        sidecars.append((stage_id, resolved_sidecar))
    return sidecars, warnings


def _sum_reported(values: Iterable[int | float | None]) -> int | float | None:
    reported = [value for value in values if value is not None]
    return sum(reported) if reported else None


def _stage_record(repo: Path, document: dict[str, Any]) -> dict[str, Any]:
    record = {
        "repo": repo.name,
        "repo_path": str(repo),
        "schema_version": document["schema_version"],
        "stage_id": document["stage_id"],
        "updated_at": document["updated_at"],
        "status": document["status"],
        "metrics": document["metrics"],
        "verification": document["verification"],
        "coverage": document["coverage"],
        "delegation": document.get("delegation", empty_delegation()),
    }
    if document["schema_version"] == TELEMETRY_SCHEMA_V3:
        record.update({field: document[field] for field in V3_FIELDS})
    return record


def aggregate_stage_telemetry(stages: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Sum only explicit measurements; a missing measurement remains null."""
    stage_items = list(stages)
    totals: dict[str, Any] = {}
    for metric in (
        "worker_wall_seconds",
        "queue_seconds",
        "review_rounds",
        "integration_seconds",
        "rebase_seconds",
    ):
        totals[metric] = _sum_reported(item["metrics"][metric] for item in stage_items)
    totals["p0_findings"] = _sum_reported(item["metrics"]["findings"]["p0"] for item in stage_items)
    totals["p1_findings"] = _sum_reported(item["metrics"]["findings"]["p1"] for item in stage_items)
    verification_names = sorted({name for item in stage_items for name in item["verification"]})
    totals["verification_seconds"] = {
        name: _sum_reported(item["verification"].get(name) for item in stage_items)
        for name in verification_names
    }
    totals["subagent_count"] = _sum_reported(
        item["delegation"]["subagent_count"] for item in stage_items
    )
    totals["agent_wall_seconds"] = _sum_reported(
        item["delegation"]["agent_wall_seconds"] for item in stage_items
    )
    totals["coordination_seconds"] = _sum_reported(
        item["delegation"]["coordination_seconds"] for item in stage_items
    )
    decisions = Counter(
        item["delegation"]["decision"]
        for item in stage_items
        if item["delegation"]["decision"] is not None
    )
    reasons = Counter(
        reason
        for item in stage_items
        for reason in item["delegation"]["reasons"]
    )
    totals["delegation_decisions"] = dict(sorted(decisions.items()))
    totals["delegation_reasons"] = dict(sorted(reasons.items()))
    v3_items = [item for item in stage_items if item["schema_version"] == TELEMETRY_SCHEMA_V3]
    if v3_items:
        levels = Counter(
            item["orchestration_level"]
            for item in v3_items
            if item["orchestration_level"] is not None
        )
        verification_decisions = Counter(
            item["verification_decision"]
            for item in v3_items
            if item["verification_decision"] is not None
        )
        anomaly_codes = Counter(
            anomaly for item in v3_items for anomaly in item["anomalies"]
        )
        totals["orchestration_levels"] = dict(sorted(levels.items()))
        totals["verification_decisions"] = dict(sorted(verification_decisions.items()))
        totals["reuse_count"] = _sum_reported(item["reuse_count"] for item in v3_items)
        totals["anomaly_codes"] = dict(sorted(anomaly_codes.items()))
    return totals


def stage_telemetry_payload(repos: Iterable[Path]) -> dict[str, Any]:
    """Read safe sidecars and return a stable empty payload when none are usable."""
    repo_paths = _unique_repos(repos)
    records: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    sidecar_count = 0
    for repo in repo_paths:
        sidecars, discovery_warnings = discover_stage_sidecars(repo)
        warnings.extend(discovery_warnings)
        sidecar_count += len(sidecars)
        for stage_id, path in sidecars:
            try:
                document = parse_stage_telemetry(path, stage_id=stage_id)
            except TelemetryValidationError as exc:
                warnings.append(_warning(repo, stage_id, exc.code))
                continue
            records.append(_stage_record(repo, document))
    records.sort(key=lambda item: (item["repo"].lower(), item["stage_id"]))
    warnings.sort(key=lambda item: (item["repo"].lower(), item["stage_id"], item["kind"]))
    repo_rows = [
        {
            "repo": repo.name,
            "repo_path": str(repo),
            "stage_count": sum(1 for item in records if item["repo_path"] == str(repo)),
        }
        for repo in repo_paths
        if any(item["repo_path"] == str(repo) for item in records)
    ]
    available = bool(records)
    unavailable_reason: str | None = None
    if not available:
        unavailable_reason = (
            "No stage telemetry sidecars found."
            if sidecar_count == 0 and not warnings
            else "No valid stage telemetry sidecars found."
        )
    return {
        "available": available,
        "unavailable_reason": unavailable_reason,
        "generated_at": int(time.time()),
        "repo_count": len(repo_paths),
        "sidecar_count": sidecar_count,
        "stage_count": len(records),
        "repos": repo_rows,
        "stages": records,
        "totals": aggregate_stage_telemetry(records) if records else empty_totals(),
        "warnings": warnings,
    }
