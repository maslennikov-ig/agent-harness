"""Bounded, read-only orchestration throughput projection."""

from __future__ import annotations

import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from .telemetry import (
        TELEMETRY_SCHEMA_V3,
        TelemetryValidationError,
        parse_stage_telemetry,
    )
except ImportError:  # Direct file loading in focused contract tests.
    from scripts.orch_panel.telemetry import (  # type: ignore[no-redef]
        TELEMETRY_SCHEMA_V3,
        TelemetryValidationError,
        parse_stage_telemetry,
    )


SCHEMA_VERSION = "orchestration-throughput/v1"
HARD_COMMIT_CAP = 500
GIT_TIMEOUT_SECONDS = 8
STAGE_SCAN_CAP = 500
LEVELS = {"inner_loop", "slice_acceptance", "integration", "release"}
DECISIONS = {"run", "reuse"}
STAGE_SIZING_DIAGNOSTICS = (
    "suspicious_micro_stage",
    "repeated_full_verification_without_material_source_change",
)


class ThroughputUnavailable(RuntimeError):
    """Raised when bounded Git history cannot be read."""


@dataclass(frozen=True)
class Commit:
    oid: str
    subject: str
    paths: tuple[str, ...]

    @property
    def metadata_only(self) -> bool:
        return bool(self.paths) and all(_metadata_path(path) for path in self.paths)

    @property
    def proof_closeout(self) -> bool:
        if not self.metadata_only:
            return False
        subject = self.subject.lower()
        if any(token in subject for token in ("closeout", "evidence", "proof")):
            return True
        return any(_stage_proof_path(path) for path in self.paths)


def _metadata_path(raw_path: str) -> bool:
    path = Path(raw_path)
    if not path.parts:
        return False
    if path.parts[0] in {".beads", ".codex", "docs"}:
        return True
    return path.name.lower() in {
        "agents.md",
        "agent_notes.md",
        "changelog.md",
        "claude.md",
        "contributing.md",
        "readme.md",
    }


def _stage_proof_path(raw_path: str) -> bool:
    parts = Path(raw_path).parts
    if len(parts) < 4 or parts[:2] != (".codex", "stages"):
        return False
    name = parts[-1].lower()
    return name in {"summary.md", "telemetry.json"} or "evidence" in name or "proof" in name


def _bounded_limit(max_commits: int) -> int:
    if isinstance(max_commits, bool) or not isinstance(max_commits, int):
        raise ValueError("max_commits must be an integer")
    return max(1, min(HARD_COMMIT_CAP, max_commits))


def read_git_commits(repo: Path, *, max_commits: int = HARD_COMMIT_CAP) -> list[Commit]:
    """Read at most the hard cap from Git without changing repository state."""
    limit = _bounded_limit(max_commits)
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--max-count={limit}",
                "--no-renames",
                "--format=%x1e%H%x1f%s",
                "--name-only",
            ],
            cwd=str(Path(repo)),
            text=True,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ThroughputUnavailable("bounded git log unavailable") from exc
    if result.returncode != 0:
        raise ThroughputUnavailable("bounded git log unavailable")

    commits: list[Commit] = []
    for raw_record in result.stdout.split("\x1e"):
        lines = raw_record.strip("\n").splitlines()
        if not lines or "\x1f" not in lines[0]:
            continue
        oid, subject = lines[0].split("\x1f", 1)
        paths = tuple(line.strip() for line in lines[1:] if line.strip())
        commits.append(Commit(oid=oid, subject=subject, paths=paths))
    return commits


def count_recent_stage_summaries(repo: Path, commits: Iterable[Commit]) -> int:
    """Count distinct stage summaries represented in the bounded commit window."""
    del repo  # The count comes only from the already-bounded history.
    stage_ids: set[str] = set()
    for commit in commits:
        for raw_path in commit.paths:
            parts = Path(raw_path).parts
            if len(parts) >= 4 and parts[:2] == (".codex", "stages") and parts[-1].lower() == "summary.md":
                stage_ids.add(parts[2])
    return len(stage_ids)


def _safe_v3_documents(repo: Path) -> list[dict[str, Any]]:
    stage_root = Path(repo) / ".codex" / "stages"
    if stage_root.is_symlink() or not stage_root.is_dir():
        return []
    try:
        root = stage_root.resolve()
        entries = sorted(stage_root.iterdir(), key=lambda path: path.name)[:STAGE_SCAN_CAP]
    except (OSError, RuntimeError):
        return []
    documents: list[dict[str, Any]] = []
    for stage_dir in entries:
        if stage_dir.is_symlink() or not stage_dir.is_dir():
            continue
        sidecar = stage_dir / "telemetry.json"
        if sidecar.is_symlink() or not sidecar.is_file():
            continue
        try:
            if stage_dir.resolve().parent != root or sidecar.resolve().parent != stage_dir.resolve():
                continue
            document = parse_stage_telemetry(sidecar, stage_id=stage_dir.name)
        except (OSError, RuntimeError, TelemetryValidationError):
            continue
        if document.get("schema_version") == TELEMETRY_SCHEMA_V3:
            documents.append(document)
    return documents


def telemetry_projection(repo: Path) -> dict[str, Any]:
    """Project only explicit v3 observations; absent history stays unavailable."""
    documents = _safe_v3_documents(repo)
    if not documents:
        return {
            "available": False,
            "level_distribution": {},
            "verification_decisions": {},
            "reuse_count": None,
            "repeated_verification_count": None,
            "bookkeeping_write_count": None,
            "stage_sizing_diagnostics": [],
            "anomalies": [],
        }
    levels = Counter(
        value for document in documents
        if (value := document.get("orchestration_level")) in LEVELS
    )
    decisions = Counter(
        value for document in documents
        if (value := document.get("verification_decision")) in DECISIONS
    )

    def reported_sum(field: str) -> int | None:
        values = [
            value for document in documents
            if isinstance((value := document.get(field)), int) and not isinstance(value, bool) and value >= 0
        ]
        return sum(values) if values else None

    anomaly_codes = {
        anomaly
        for document in documents
        for anomaly in document.get("anomalies", [])
        if isinstance(anomaly, str)
    }
    repeated_count = reported_sum("repeated_verification_count")
    stage_sizing_diagnostics = sorted(
        anomaly_codes.intersection(STAGE_SIZING_DIAGNOSTICS)
    )
    return {
        "available": True,
        "level_distribution": dict(sorted(levels.items())),
        "verification_decisions": dict(sorted(decisions.items())),
        "reuse_count": reported_sum("reuse_count"),
        "repeated_verification_count": repeated_count,
        "bookkeeping_write_count": reported_sum("bookkeeping_write_count"),
        "stage_sizing_diagnostics": stage_sizing_diagnostics,
        "anomalies": sorted(anomaly_codes),
    }


def classify_counts(
    repo: Path,
    *,
    product_commits: int | None,
    orchestration_commits: int | None,
    proof_commits: int | None,
    stage_count: int | None,
    additional_anomalies: Iterable[str] = (),
) -> dict[str, Any]:
    """Classify observed counts into read-only replan signals."""
    anomalies = set(additional_anomalies)
    if None not in (product_commits, orchestration_commits, proof_commits):
        assert product_commits is not None
        assert orchestration_commits is not None
        assert proof_commits is not None
        if orchestration_commits + proof_commits > product_commits:
            anomalies.add("orchestration_commits_exceed_product")
    if product_commits is not None and stage_count is not None:
        if stage_count > max(3, product_commits):
            anomalies.add("stage_count_spike")
    overhead = None
    stage_density = None
    if product_commits is not None and product_commits > 0:
        if orchestration_commits is not None and proof_commits is not None:
            overhead = round((orchestration_commits + proof_commits) / product_commits, 3)
        if stage_count is not None:
            stage_density = round(stage_count / product_commits, 3)
    return {
        "repo": Path(repo).name,
        "repo_path": str(Path(repo)),
        "available": True,
        "classification": "observed",
        "product_commits": product_commits,
        "orchestration_commits": orchestration_commits,
        "proof_commits": proof_commits,
        "stage_count": stage_count,
        "orchestration_to_product_ratio": overhead,
        "stage_density": stage_density,
        "anomalies": sorted(anomalies),
        "action": "replan_required" if anomalies else "none",
        "warnings": [],
    }


def _unavailable_repo(repo: Path) -> dict[str, Any]:
    return {
        "repo": Path(repo).name,
        "repo_path": str(Path(repo)),
        "available": False,
        "classification": "unavailable",
        "product_commits": None,
        "orchestration_commits": None,
        "proof_commits": None,
        "stage_count": None,
        "orchestration_to_product_ratio": None,
        "stage_density": None,
        "anomalies": [],
        "action": "none",
        "telemetry": telemetry_projection(repo),
        "warnings": [{"kind": "git_unavailable"}],
    }


def repository_throughput(repo: Path, *, max_commits: int = HARD_COMMIT_CAP) -> dict[str, Any]:
    """Return a bounded observed projection, or an unavailable row on Git failure."""
    repo = Path(repo)
    try:
        commits = read_git_commits(repo, max_commits=max_commits)
    except (ThroughputUnavailable, ValueError):
        return _unavailable_repo(repo)
    product = sum(not commit.metadata_only for commit in commits)
    orchestration = sum(commit.metadata_only and not commit.proof_closeout for commit in commits)
    proof = sum(commit.proof_closeout for commit in commits)
    stages = count_recent_stage_summaries(repo, commits)
    telemetry = telemetry_projection(repo)
    row = classify_counts(
        repo,
        product_commits=product,
        orchestration_commits=orchestration,
        proof_commits=proof,
        stage_count=stages,
        additional_anomalies=telemetry["anomalies"],
    )
    row["telemetry"] = telemetry
    return row


def _sum_reported(rows: Iterable[dict[str, Any]], field: str) -> int | None:
    values = [row[field] for row in rows if row["available"] and row[field] is not None]
    return sum(values) if values else None


def throughput_payload(repos: Iterable[Path]) -> dict[str, Any]:
    """Return a stable multi-repository payload without mutating source truth."""
    repo_paths = sorted({Path(repo).resolve() for repo in repos}, key=lambda path: (path.name.lower(), str(path)))
    rows = [repository_throughput(repo) for repo in repo_paths]
    warnings = [
        {"repo": row["repo"], **warning}
        for row in rows
        for warning in row["warnings"]
    ]
    level_distribution: Counter[str] = Counter()
    verification_decisions: Counter[str] = Counter()
    anomaly_codes: Counter[str] = Counter()
    reuse_values: list[int] = []
    for row in rows:
        level_distribution.update(row["telemetry"]["level_distribution"])
        verification_decisions.update(row["telemetry"]["verification_decisions"])
        anomaly_codes.update(row["anomalies"])
        reuse_count = row["telemetry"]["reuse_count"]
        if reuse_count is not None:
            reuse_values.append(reuse_count)
    available_rows = [row for row in rows if row["available"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": int(time.time()),
        "repos": rows,
        "totals": {
            "repo_count": len(rows),
            "available_repo_count": len(available_rows),
            "unavailable_repo_count": len(rows) - len(available_rows),
            "product_commits": _sum_reported(rows, "product_commits"),
            "orchestration_commits": _sum_reported(rows, "orchestration_commits"),
            "proof_commits": _sum_reported(rows, "proof_commits"),
            "stage_count": _sum_reported(rows, "stage_count"),
            "level_distribution": dict(sorted(level_distribution.items())),
            "verification_decisions": dict(sorted(verification_decisions.items())),
            "reuse_count": sum(reuse_values) if reuse_values else None,
            "anomaly_codes": dict(sorted(anomaly_codes.items())),
        },
        "warnings": warnings,
    }
