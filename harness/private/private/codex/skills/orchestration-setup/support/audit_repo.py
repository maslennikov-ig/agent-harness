#!/usr/bin/env python3
"""Audit a repository against the canonical orchestration baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import tomllib
from typing import Any


SUPPORT_DIR = pathlib.Path(__file__).resolve().parent
if str(SUPPORT_DIR) not in sys.path:
    sys.path.insert(0, str(SUPPORT_DIR))

from sync_support_files import (  # noqa: E402 - sibling helper owns the copy plan
    AGENTS_BEGIN,
    AGENTS_END,
    AGENTS_TEMPLATE,
    files_for,
)

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE_SCRIPTS = SKILL_DIR / "templates" / "scripts"
if str(TEMPLATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_SCRIPTS))

from verification_evidence import EvidenceError, load_manifest  # noqa: E402

BASELINE_PATH = SKILL_DIR / "templates" / "baseline.toml"
MANAGED_SCRIPT_PREFIX = "scripts/orchestration/"

CORE_FILES = (
    "AGENTS.md",
    ".codex/orchestrator.toml",
    ".codex/handoff.md",
    ".codex/project-index.md",
)
DELEGATED_FILES = {
    "scripts/orchestration/report_child_completion.py",
    "scripts/orchestration/review_completion_inbox.py",
}
MANUAL_FILE = ".codex/manual-agent-prompt-template.md"
ALLOWED_LAUNCHERS = {"codex_subagents", "manual_user_launch", "none"}
STALE_CONTRACT_FIELDS = (
    "delegation.requires_explicit_user_spawn_request",
    "delegation.subagents_preauthorized_for_complex",
)
COMPATIBLE_LEGACY_PROFILES = {
    "balanced-v2.17",
    "balanced-v2.18",
    "balanced-v2.19",
}
PRE_V219_PROFILES = {"balanced-v2.17", "balanced-v2.18"}
V220_DELEGATION_FIELDS = {
    "delegation.subagents_preauthorized_for_medium_complex",
    "delegation.root_execution_scope",
    "delegation.medium_execution_default",
    "delegation.complex_execution_default",
    "delegation.delegation_gate",
    "delegation.delegation_unavailable_action",
    "delegation.parallel_decomposition_matrix",
    "delegation.parallel_execution_default",
}
CURRENT_EVIDENCE_FIELDS = {
    "verification_policy.reuse_unchanged_evidence",
    "evidence.schema",
    "evidence.manifest_path",
    "evidence.report_dir",
    "evidence.kill_switch_env",
}
NON_EXEMPTABLE_DELEGATION_FIELDS = V220_DELEGATION_FIELDS | {
    "delegation.simple_checks_owner",
    "delegation.independence_alone_sufficient",
    "delegation.parallel_decomposition_matrix",
}
V219_ONLY_FILES = {
    ".codex/stage-manifest-template.json",
    ".codex/scope-preservation-ledger-template.json",
    ".codex/scope-criterion-snapshot-template.json",
    "scripts/orchestration/lint_stage_sizing.py",
}
CURRENT_EVIDENCE_FILES = {
    ".codex/verification-manifest-template.json",
    "scripts/orchestration/verification_evidence.py",
}


def load_toml(path: pathlib.Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def dotted_get(data: dict[str, Any], dotted: str) -> tuple[bool, Any]:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def required_files(baseline: dict[str, Any], launcher: str) -> list[str]:
    files = list((baseline.get("required_files") or {}).get("repo", []))
    if launcher == "none":
        files = [item for item in files if item not in DELEGATED_FILES]
    if launcher == "manual_user_launch":
        files.append(MANUAL_FILE)
    return files


def contract_expectations(baseline: dict[str, Any]) -> dict[str, Any]:
    delegation = baseline.get("delegation") or {}
    stage_limits = baseline.get("stage_limits") or {}
    stage_sizing = baseline.get("stage_sizing") or {}
    verification = baseline.get("verification_policy") or {}
    graph = baseline.get("knowledge_graph") or {}
    handoff = baseline.get("handoff") or {}
    token_efficiency = baseline.get("token_efficiency") or {}
    return {
        "baseline.profile": baseline.get("profile"),
        "baseline.source_skill": baseline.get("source_skill"),
        "delegation.subagents_preauthorized_for_medium_complex": delegation.get(
            "subagents_preauthorized_for_medium_complex"
        ),
        "delegation.root_execution_scope": delegation.get("root_execution_scope"),
        "delegation.medium_execution_default": delegation.get(
            "medium_execution_default"
        ),
        "delegation.complex_execution_default": delegation.get(
            "complex_execution_default"
        ),
        "delegation.simple_checks_owner": delegation.get("simple_checks_owner"),
        "delegation.delegation_gate": delegation.get("delegation_gate"),
        "delegation.delegation_unavailable_action": delegation.get(
            "delegation_unavailable_action"
        ),
        "delegation.independence_alone_sufficient": delegation.get(
            "independence_alone_sufficient"
        ),
        "delegation.parallel_decomposition_matrix": delegation.get(
            "parallel_decomposition_matrix"
        ),
        "delegation.parallel_execution_default": delegation.get(
            "parallel_execution_default"
        ),
        "stage_limits.continuation_lineage": stage_limits.get(
            "continuation_lineage"
        ),
        "stage_limits.cost_anomaly_action": stage_limits.get("cost_anomaly_action"),
        "stage_limits.hard_stop_on_time_or_token_budget": stage_limits.get(
            "hard_stop_on_time_or_token_budget"
        ),
        "stage_sizing.mode": stage_sizing.get("mode"),
        "stage_sizing.manifest_schema": stage_sizing.get("manifest_schema"),
        "stage_sizing.ledger_schema": stage_sizing.get("ledger_schema"),
        "stage_sizing.scope_anchor_schema": stage_sizing.get("scope_anchor_schema"),
        "stage_sizing.one_active_implementation_stage": stage_sizing.get(
            "one_active_implementation_stage"
        ),
        "stage_sizing.parallel_streams_inside_stage": stage_sizing.get(
            "parallel_streams_inside_stage"
        ),
        "stage_sizing.merge_adjacent_when_shared": stage_sizing.get(
            "merge_adjacent_when_shared"
        ),
        "stage_sizing.allowed_split_reasons": stage_sizing.get(
            "allowed_split_reasons"
        ),
        "stage_sizing.scope_preservation_ledger_required_on_replan": stage_sizing.get(
            "scope_preservation_ledger_required_on_replan"
        ),
        "stage_sizing.accepted_history_immutable": stage_sizing.get(
            "accepted_history_immutable"
        ),
        "stage_sizing.migration_scope": stage_sizing.get("migration_scope"),
        "verification_policy.mode": verification.get("mode"),
        "evidence.schema": (baseline.get("evidence") or {}).get("schema"),
        "evidence.manifest_path": (baseline.get("evidence") or {}).get("manifest_path"),
        "evidence.report_dir": (baseline.get("evidence") or {}).get("report_dir"),
        "evidence.kill_switch_env": (baseline.get("evidence") or {}).get(
            "kill_switch_env"
        ),
        "knowledge_graph.query_first": graph.get("query_first"),
        "knowledge_graph.freshness_check_required": graph.get(
            "freshness_check_required"
        ),
        "knowledge_graph.refresh_policy": graph.get("refresh_policy"),
        "handoff.current_state_max_lines": handoff.get("current_state_max_lines"),
        "handoff.hard_limit_lines": handoff.get("hard_limit_lines"),
        **{
            f"token_efficiency.{key}": value
            for key, value in token_efficiency.items()
        },
    }


def managed_agents_region(path: pathlib.Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if text.count(AGENTS_BEGIN) != 1 or text.count(AGENTS_END) != 1:
        return None
    start = text.index(AGENTS_BEGIN) + len(AGENTS_BEGIN)
    end = text.index(AGENTS_END, start)
    return text[start:end].strip()


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drifted_support_scripts(repo: pathlib.Path, launcher: str) -> list[str]:
    """Managed scripts whose content no longer matches the template.

    Contract fields alone made `upgrade_available` untrustworthy: a repository
    can declare the current profile while carrying a support script from an
    older generation, because nothing ever compared file content. Only the
    executable helpers under `scripts/orchestration/` are checked; the `.codex`
    templates are seeds a repository is expected to edit. Absent files are left
    to the `missing_file` check so a single problem is not reported twice.
    """

    drifted = []
    for source_rel, target_rel in files_for(launcher).items():
        if not target_rel.startswith(MANAGED_SCRIPT_PREFIX):
            continue
        source = SKILL_DIR / source_rel
        target = repo / target_rel
        if not source.is_file() or not target.is_file() or target.is_symlink():
            continue
        if digest(source) != digest(target):
            drifted.append(target_rel)
    return sorted(drifted)


def finding(
    severity: str,
    code: str,
    detail: str,
    *,
    field: str | None = None,
) -> dict[str, str]:
    item = {"severity": severity, "code": code, "detail": detail}
    if field:
        item["field"] = field
    return item


def audit(repo: pathlib.Path) -> tuple[str, list[dict[str, str]]]:
    baseline = load_toml(BASELINE_PATH)
    findings: list[dict[str, str]] = []

    if not repo.exists():
        return "uninitialized", [
            finding("error", "repo_missing", str(repo))
        ]

    present_core = [rel for rel in CORE_FILES if (repo / rel).exists()]
    if not present_core:
        return "uninitialized", [
            finding("warning", "core_contract_missing", "no orchestration core files found")
        ]

    contract_path = repo / ".codex" / "orchestrator.toml"
    if not contract_path.exists():
        return "partially_initialized", [
            finding("warning", "contract_missing", str(contract_path))
        ]

    try:
        contract = load_toml(contract_path)
    except Exception as exc:  # noqa: BLE001 - the audit must report malformed TOML.
        return "drifted", [
            finding("error", "contract_parse_failed", str(exc))
        ]

    launcher = str((contract.get("delegation") or {}).get("launcher", "")).strip()
    if not launcher:
        findings.append(
            finding(
                "warning",
                "contract_field_missing",
                "delegation.launcher is required",
                field="delegation.launcher",
            )
        )
        launcher = str((baseline.get("delegation") or {}).get("launcher"))
    elif launcher not in ALLOWED_LAUNCHERS:
        findings.append(
            finding(
                "error",
                "contract_value_mismatch",
                f"unknown launcher {launcher!r}",
                field="delegation.launcher",
            )
        )

    verification_policy = contract.get("verification_policy")
    reuse_enabled = (
        verification_policy.get("reuse_unchanged_evidence")
        if isinstance(verification_policy, dict)
        else None
    )
    if not isinstance(reuse_enabled, bool):
        findings.append(
            finding(
                "warning",
                "contract_field_missing",
                "verification_policy.reuse_unchanged_evidence must be true or false",
                field="verification_policy.reuse_unchanged_evidence",
            )
        )
    elif reuse_enabled:
        manifest_path = repo / ".codex" / "verification-manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            findings.append(
                finding(
                    "error",
                    "reuse_manifest_missing",
                    "reuse is enabled but .codex/verification-manifest.json is not a regular file",
                    field="verification_policy.reuse_unchanged_evidence",
                )
            )
        else:
            try:
                load_manifest(repo, manifest_path)
            except EvidenceError as exc:
                findings.append(
                    finding(
                        "error",
                        "reuse_manifest_invalid",
                        str(exc),
                        field="verification_policy.reuse_unchanged_evidence",
                    )
                )

    actual_profile = (contract.get("baseline") or {}).get("profile")
    compatible_legacy = (
        isinstance(actual_profile, str)
        and actual_profile in COMPATIBLE_LEGACY_PROFILES
    )
    expected_agents = (SKILL_DIR / AGENTS_TEMPLATE).read_text(encoding="utf-8").strip()
    actual_agents = managed_agents_region(repo / "AGENTS.md")
    agents_missing = actual_agents is None
    agents_drifted = actual_agents is not None and actual_agents != expected_agents
    if agents_missing:
        findings.append(
            finding(
                "info" if compatible_legacy else "warning",
                "upgrade_available" if compatible_legacy else "managed_agents_missing",
                "project AGENTS.md lacks the canonical marker-managed token-efficiency block",
                field="AGENTS.md",
            )
        )
    elif agents_drifted:
        findings.append(
            finding(
                "error",
                "managed_agents_drift",
                "project AGENTS.md managed region differs from the canonical source",
                field="AGENTS.md",
            )
        )

    stale_contract_fields = False
    for field_name in STALE_CONTRACT_FIELDS:
        present, _ = dotted_get(contract, field_name)
        if present:
            if (
                compatible_legacy
                and field_name
                == "delegation.subagents_preauthorized_for_complex"
            ):
                findings.append(
                    finding(
                        "info",
                        "upgrade_available",
                        f"{field_name} is replaced by {baseline.get('profile')!r}",
                        field=field_name,
                    )
                )
                continue
            stale_contract_fields = True
            findings.append(
                finding(
                    "error",
                    "stale_contract_field",
                    f"{field_name} must be removed during baseline reconciliation",
                    field=field_name,
                )
            )

    missing_files = [
        rel
        for rel in required_files(baseline, launcher)
        if not (repo / rel).exists()
        and not (actual_profile in PRE_V219_PROFILES and rel in V219_ONLY_FILES)
        and not (
            actual_profile in COMPATIBLE_LEGACY_PROFILES
            and rel in CURRENT_EVIDENCE_FILES
        )
    ]
    for rel in missing_files:
        findings.append(finding("warning", "missing_file", rel))

    raw_exceptions = (contract.get("baseline") or {}).get("exceptions", [])
    exceptions = {
        str(item).strip() for item in raw_exceptions if str(item).strip()
    } if isinstance(raw_exceptions, list) else set()
    used_exceptions: set[str] = set()
    missing_fields = False
    unexcepted_mismatches = False
    upgrade_available = False

    for rel in drifted_support_scripts(repo, launcher):
        upgrade_available = True
        findings.append(
            finding(
                "info",
                "template_drift",
                f"{rel} differs from the {baseline.get('profile')!r} template",
                field=rel,
            )
        )

    for field_name, expected in contract_expectations(baseline).items():
        present, actual = dotted_get(contract, field_name)
        if not present:
            if compatible_legacy and (
                field_name.startswith("stage_sizing.")
                or field_name.startswith("token_efficiency.")
                or field_name in V220_DELEGATION_FIELDS
                or field_name in CURRENT_EVIDENCE_FIELDS
            ):
                upgrade_available = True
                findings.append(
                    finding(
                        "info",
                        "upgrade_available",
                        f"{field_name} is introduced by {baseline.get('profile')!r}",
                        field=field_name,
                    )
                )
                continue
            missing_fields = True
            findings.append(
                finding(
                    "warning",
                    "contract_field_missing",
                    f"{field_name} is required",
                    field=field_name,
                )
            )
            continue
        if field_name == "handoff.current_state_max_lines":
            handoff_ceiling = (baseline.get("handoff") or {}).get("hard_limit_lines")
            if (
                type(actual) is int
                and type(handoff_ceiling) is int
                and 1 <= actual <= handoff_ceiling
            ):
                continue
        if (
            compatible_legacy
            and field_name == "handoff.hard_limit_lines"
            and type(actual) is int
            and type(expected) is int
            and 1 <= actual <= expected
        ):
            upgrade_available = True
            findings.append(
                finding(
                    "info",
                    "upgrade_available",
                    f"{field_name} can be raised from {actual!r} to {expected!r}",
                    field=field_name,
                )
            )
            continue
        if actual == expected:
            continue
        if (
            field_name == "baseline.profile"
            and isinstance(actual, str)
            and actual in COMPATIBLE_LEGACY_PROFILES
        ):
            upgrade_available = True
            findings.append(
                finding(
                    "info",
                    "upgrade_available",
                    f"compatible legacy profile {actual!r}; current profile is {expected!r}",
                    field=field_name,
                )
            )
            continue
        if compatible_legacy and field_name in V220_DELEGATION_FIELDS:
            upgrade_available = True
            findings.append(
                finding(
                    "info",
                    "upgrade_available",
                    f"{field_name} changes from {actual!r} to {expected!r}",
                    field=field_name,
                )
            )
            continue
        if (
            field_name in exceptions
            and field_name not in NON_EXEMPTABLE_DELEGATION_FIELDS
        ):
            used_exceptions.add(field_name)
            findings.append(
                finding(
                    "info",
                    "explicit_exception",
                    f"{field_name}: expected {expected!r}, found {actual!r}",
                    field=field_name,
                )
            )
            continue
        unexcepted_mismatches = True
        findings.append(
            finding(
                "error",
                "contract_value_mismatch",
                f"expected {expected!r}, found {actual!r}",
                field=field_name,
            )
        )

    for field_name in sorted(exceptions - used_exceptions):
        findings.append(
            finding(
                "warning",
                "unused_exception",
                f"{field_name} does not match an active contract deviation",
                field=field_name,
            )
        )

    if (
        missing_files
        or missing_fields
        or (agents_missing and not compatible_legacy)
        or (not isinstance(reuse_enabled, bool) and not compatible_legacy)
    ):
        return "partially_initialized", findings
    if (
        unexcepted_mismatches
        or stale_contract_fields
        or launcher not in ALLOWED_LAUNCHERS
        or any(item["code"] == "reuse_manifest_missing" for item in findings)
        or any(item["code"] == "reuse_manifest_invalid" for item in findings)
        or agents_drifted
    ):
        return "drifted", findings
    if used_exceptions:
        return "aligned_with_exceptions", findings
    if upgrade_available:
        return "upgrade_available", findings
    return "aligned", findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=pathlib.Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    status, findings = audit(repo)
    result = {
        "repo": str(repo),
        "baseline_profile": load_toml(BASELINE_PATH).get("profile"),
        "status": status,
        "drifted_support_files": [
            item["field"]
            for item in findings
            if item["code"] == "template_drift" and item.get("field")
        ],
        "findings": findings,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"status: {status}")
        print(f"baseline: {result['baseline_profile']}")
        for item in findings:
            field = f" [{item['field']}]" if item.get("field") else ""
            print(f"- {item['severity']}: {item['code']}{field}: {item['detail']}")
    return 0 if status in {"aligned", "aligned_with_exceptions", "upgrade_available"} else 1


if __name__ == "__main__":
    sys.exit(main())
