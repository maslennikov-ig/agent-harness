#!/usr/bin/env python3
"""Deterministically audit canonical and installed token-efficiency surfaces."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tomllib
from typing import Any


SETUP_ROOT = pathlib.Path(__file__).resolve().parents[1]
ORCHESTRATOR_ROOT = SETUP_ROOT.parent / "orchestrator-stage"
BEGIN = "<!-- ORCHESTRATION-BASELINE:BEGIN -->"
END = "<!-- ORCHESTRATION-BASELINE:END -->"
CHECKS = (
    "fork_default",
    "reasoned_override",
    "four_fields",
    "duplicate_rules",
    "bounded_output",
    "broad_verification",
    "throughput_policy",
    "model_routing",
    "managed_agents",
)


def finding(check: str, code: str, detail: str) -> dict[str, str]:
    return {"check": check, "code": code, "detail": detail}


def fenced_fields(text: str) -> list[str]:
    try:
        body = text.split("```md\n", 1)[1].split("\n```", 1)[0]
    except IndexError:
        return []
    return [line.split(":", 1)[0].strip() for line in body.splitlines() if ":" in line]


def managed_region(text: str) -> str | None:
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        return None
    start = text.index(BEGIN) + len(BEGIN)
    end = text.index(END, start)
    return text[start:end].strip()


def load_baseline(setup_root: pathlib.Path) -> dict[str, Any]:
    return tomllib.loads(
        (setup_root / "templates/baseline.toml").read_text(encoding="utf-8")
    )


def audit_canonical(
    setup_root: pathlib.Path = SETUP_ROOT,
    orchestrator_root: pathlib.Path = ORCHESTRATOR_ROOT,
) -> list[dict[str, str]]:
    baseline = load_baseline(setup_root)
    token = baseline.get("token_efficiency")
    findings: list[dict[str, str]] = []
    if not isinstance(token, dict):
        return [finding("fork_default", "token_contract_missing", "missing [token_efficiency]")]

    delegation = (
        orchestrator_root / "references/delegation-and-isolation.md"
    ).read_text(encoding="utf-8")
    verification = (
        orchestrator_root / "references/verification-routing.md"
    ).read_text(encoding="utf-8")
    spawn = (setup_root / "templates/subagent-spawn-template.md").read_text(
        encoding="utf-8"
    )
    task_contract = (setup_root / "templates/subagent-task-contract.md").read_text(
        encoding="utf-8"
    )
    agents = (setup_root / "templates/project-agents-managed-block.md").read_text(
        encoding="utf-8"
    )

    if token.get("native_fork_turns_default") != "none" or 'fork_turns="none"' not in delegation:
        findings.append(finding("fork_default", "fork_default_drift", "native fork default must be explicit none"))
    if token.get("hard_token_cap") is not False:
        findings.append(finding("fork_default", "hard_cap_enabled", "token-efficiency defaults may not be hard caps"))

    override_expected = {
        "non_none_fork_override_enabled": True,
        "non_none_fork_override_requires_rationale": True,
        "non_none_fork_override_context_sources": [
            "nearest_agents",
            "selected_beads_goal",
            "exact_existing_reference",
        ],
    }
    if {key: token.get(key) for key in override_expected} != override_expected:
        findings.append(finding("reasoned_override", "override_contract_drift", "non-none override contract is stale"))
    normalized = " ".join(delegation.split())
    for phrase in ("task-specific rationale", "nearest `AGENTS.md`", "selected Beads goal", "exact existing reference"):
        if phrase not in normalized:
            findings.append(finding("reasoned_override", "override_guidance_missing", phrase))

    expected_fields = ["Goal", "Write zone", "Verification", "Stop"]
    if token.get("native_prompt_fields") != ["goal", "write_zone", "verification", "stop"]:
        findings.append(finding("four_fields", "prompt_field_contract_drift", "machine field list is stale"))
    if fenced_fields(spawn) != expected_fields:
        findings.append(finding("four_fields", "spawn_template_fields_drift", repr(fenced_fields(spawn))))

    duplicate_carriers = delegation + "\n" + spawn + "\n" + task_contract
    if duplicate_carriers.count("Coalesce routine progress updates") != 1:
        findings.append(finding("duplicate_rules", "progress_rule_duplicate", "progress rule must have one detailed owner"))
    if duplicate_carriers.count("bounded summarized tool output") != 1:
        findings.append(finding("duplicate_rules", "output_rule_duplicate", "output rule must have one detailed owner"))

    output_expected = {
        "routine_updates": "coalesce",
        "tool_output_default": "bounded_summary",
        "truncation_signal_required": True,
        "tool_output_expansion_requires_rationale": True,
    }
    if {key: token.get(key) for key in output_expected} != output_expected:
        findings.append(finding("bounded_output", "output_contract_drift", "bounded output contract is stale"))
    for phrase in ("truncation signal", "platform heartbeat", "material artifacts"):
        if phrase not in delegation:
            findings.append(finding("bounded_output", "output_guidance_missing", phrase))

    verification_expected = {
        "worker_verification": "optional_diagnostic",
        "final_acceptance_owner": "root",
        "full_suite_boundary": "epic_or_release",
        "parallelism_gate": "material_benefit",
    }
    if {key: token.get(key) for key in verification_expected} != verification_expected:
        findings.append(finding("broad_verification", "verification_contract_drift", "verification ownership is stale"))
    if verification.count("Full configured suite") != 1:
        findings.append(finding("broad_verification", "broad_verification_duplicate", "verification reference must own one broad-suite rule"))

    throughput_expected = {
        "authority_memory": "exact_stage_non_default",
        "readiness_preflight": "boundary_identity_once",
        "operational_retry": "one_corrected_then_replan",
        "final_evidence_reuse": "policy_matching_v2",
        "candidate_build_identity": "stable_source",
    }
    if {key: token.get(key) for key in throughput_expected} != throughput_expected:
        findings.append(finding("throughput_policy", "throughput_contract_drift", "throughput defaults are stale"))
    autonomy = (
        orchestrator_root / "references/autonomy-and-approvals.md"
    ).read_text(encoding="utf-8")
    for phrase in (
        "Remember only non-default authority",
        "one content-free readiness preflight",
    ):
        if phrase not in autonomy:
            findings.append(finding("throughput_policy", "throughput_guidance_missing", phrase))
    for phrase in (
        "Never repeat a failed operational attempt",
        "Automatically use matching v2 evidence",
        "one immutable candidate build",
    ):
        if phrase not in (orchestrator_root / "references/acceptance-evidence.md").read_text(encoding="utf-8"):
            findings.append(finding("throughput_policy", "throughput_guidance_missing", phrase))

    model_policy = baseline.get("subagent_model_policy") or {}
    model_keys = (
        "root_model",
        "mechanical_model_starter",
        "simpler_model_starter",
        "complex_delegation_model_starter",
    )
    models = [model_policy.get(key) for key in model_keys]
    if any(not isinstance(model, str) or model not in delegation for model in models):
        findings.append(finding("model_routing", "model_routing_drift", "delegation reference must render baseline model routes"))
    if any(isinstance(model, str) and model in agents for model in set(models)):
        findings.append(finding("model_routing", "model_routing_duplicate", "project AGENTS must point to, not copy, model routes"))
    for phrase in (
        "The root runs on `gpt-6-astra`",
        "starting directions rather than quotas",
        "simpler implementation, exploration, or support",
        "complex delegated implementation, integration, or analysis",
        "closest supported option or keep the stream with Astra",
        "record that actual configured effort",
    ):
        if phrase not in normalized:
            findings.append(finding("model_routing", "model_routing_guidance_missing", phrase))

    if not agents.isascii() or len(agents.encode("utf-8")) > 1600:
        findings.append(finding("managed_agents", "managed_agents_not_compact_english", "managed block must be ASCII and <=1600 bytes"))
    if BEGIN in agents or END in agents or not agents.startswith("<!-- orchestration-setup:"):
        findings.append(finding("managed_agents", "managed_agents_source_unsafe", "template must be marker-free and provenance-tagged"))
    return findings


def audit_repo(repo: pathlib.Path, setup_root: pathlib.Path = SETUP_ROOT) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    baseline = load_baseline(setup_root)
    contract_path = repo / ".codex/orchestrator.toml"
    try:
        contract = tomllib.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return [finding("installed_repo", "installed_contract_missing", str(exc))]
    if contract.get("token_efficiency") != baseline.get("token_efficiency"):
        findings.append(finding("installed_repo", "installed_contract_drift", "repo token contract differs from baseline"))

    agents_path = repo / "AGENTS.md"
    expected_agents = (setup_root / "templates/project-agents-managed-block.md").read_text(
        encoding="utf-8"
    ).strip()
    try:
        region = managed_region(agents_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        region = None
    if region != expected_agents:
        findings.append(finding("installed_repo", "installed_agents_drift", "managed AGENTS region differs from baseline"))

    spawn_path = repo / ".codex/subagent-spawn-template.md"
    expected_spawn = (setup_root / "templates/subagent-spawn-template.md").read_bytes()
    try:
        actual_spawn = spawn_path.read_bytes()
    except OSError:
        actual_spawn = b""
    if actual_spawn != expected_spawn or fenced_fields(actual_spawn.decode("utf-8", "replace")) != ["Goal", "Write zone", "Verification", "Stop"]:
        findings.append(finding("installed_repo", "installed_prompt_drift", "installed spawn template differs from canonical four-field source"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=pathlib.Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    findings = audit_canonical()
    if args.repo:
        findings.extend(audit_repo(args.repo.resolve()))
    result = {
        "status": "aligned" if not findings else "drifted",
        "checks": list(CHECKS),
        "findings": findings,
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"status: {result['status']}")
        for item in findings:
            print(f"- {item['code']}: {item['detail']}")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
