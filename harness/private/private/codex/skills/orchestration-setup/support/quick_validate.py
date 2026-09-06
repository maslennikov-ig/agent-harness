#!/usr/bin/env python3
"""Quick validation for restored orchestration skill files."""

from __future__ import annotations

import json
import pathlib
import py_compile
import subprocess
import sys
import tempfile
import textwrap
import tomllib

from audit_token_efficiency import audit_canonical


ROOT = pathlib.Path(__file__).resolve().parents[2]


def check_skill(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise AssertionError(f"missing frontmatter: {path}")


def write_runtime_fixture(repo: pathlib.Path, counter: pathlib.Path) -> pathlib.Path:
    verification_command = (
        "python3 -c \"from pathlib import Path; "
        "assert Path('src/app.py').is_file()\""
    )
    stage = repo / ".codex" / "stages" / "stage-a"
    artifacts = stage / "artifacts"
    artifacts.mkdir(parents=True)
    (stage / "summary.md").write_text(
        "# Stage A\n\n"
        "docs-reviewed: no-change-needed - fixture-only behavior\n"
        "project-index: reviewed-no-change\n",
        encoding="utf-8",
    )
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "generated").mkdir()
    (repo / "generated" / "out.txt").write_text("artifact\n", encoding="utf-8")
    artifact = artifacts / "stream-a.md"
    artifact.write_text(
        textwrap.dedent(
            """
            ---
            schema_version: orchestration-artifact/v2
            task_id: stream-a
            stage_id: stage-a
            orchestration_level: release
            status: returned
            accepted_by_orchestrator: no
            risk_level: low
            changed_files:
              - src/app.py
            ---
            # Summary
            Fixture.
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (repo / ".codex" / "orchestrator.toml").write_text(
        textwrap.dedent(
            f"""
            role = "orchestrator-stage"

            [baseline]
            profile = "balanced-v2.18"
            source_skill = "orchestration-setup"

            [orchestration_levels]
            default = "slice_acceptance"
            stage_levels = ["slice_acceptance", "integration", "release"]

            [workspace]
            current_stage_id = "stage-a"

            [artifacts]
            current_stage_summary = ".codex/stages/stage-a/summary.md"

            [delegation]
            launcher = "none"

            [completion_inbox]
            scope = "repo_root"
            events_file = ".codex/stages/stage-a/events.ndjson"
            review_state_file = ".codex/stages/stage-a/reviewed.json"

            [verification]
            release_commands = [{json.dumps(verification_command)}]

            [verification_policy]
            mode = "explicit"
            default_level = "slice_acceptance"
            reuse_unchanged_evidence = true

            [evidence]
            schema = "verification-evidence/v2"
            manifest_path = ".codex/verification-manifest.json"
            report_dir = "orchestration-evidence/v2"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (repo / ".codex" / "verification-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "verification-manifest/v2",
                "producer": "orchestration-setup",
                "required_steps": ["release"],
                "steps": [
                    {
                        "id": "release",
                        "command": verification_command,
                        "cwd": ".",
                        "inputs": ["src/app.py"],
                        "lockfiles": [],
                        "tools": [{"name": "python", "executable": "python3"}],
                        "environment": [],
                        "dependencies": [],
                        "external": False,
                        "inputs_complete": True,
                        "cache": {
                            "eligible": True,
                            "reason": "reads only the declared fixture source",
                        },
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    return artifact


def run_fixture_command(script: pathlib.Path, repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def check_proportional_runtime_regressions(setup_root: pathlib.Path) -> None:
    scripts = setup_root / "templates" / "scripts"
    closeout = scripts / "run_stage_closeout.py"
    reporter = scripts / "report_child_completion.py"
    reviewer = scripts / "review_completion_inbox.py"
    stage_ready = scripts / "check_stage_ready.py"

    with tempfile.TemporaryDirectory() as raw_tmp:
        repo = pathlib.Path(raw_tmp) / "repo"
        repo.mkdir()
        counter = pathlib.Path(raw_tmp) / "counter.txt"
        artifact = write_runtime_fixture(repo, counter)
        release = run_fixture_command(
            closeout,
            repo,
            "--stage",
            "stage-a",
            "--level",
            "release",
            "--dry-run",
        )
        if release.returncode != 0:
            raise AssertionError(f"release routing fixture failed: {release.stderr}")
        if "src/app.py" not in release.stdout:
            raise AssertionError("release did not select configured release_commands")

        mismatch = run_fixture_command(
            reporter,
            repo,
            "--task",
            "stream-b",
            "--stage",
            "stage-a",
            "--artifact",
            str(artifact),
            "--status",
            "returned",
            "--verify",
            "passed",
            "--clean",
            "no",
        )
        if mismatch.returncode == 0:
            raise AssertionError("reporter accepted mismatched artifact task identity")

        artifact.unlink()
        (repo / ".codex" / "handoff.md").write_text(
            "Next stage id: stage-a-extra\n## Explicit defers\n- none\n",
            encoding="utf-8",
        )
        ready = run_fixture_command(stage_ready, repo, "stage-a")
        if ready.returncode == 0:
            raise AssertionError("stage-ready accepted a handoff substring mismatch")

    with tempfile.TemporaryDirectory() as raw_tmp:
        repo = pathlib.Path(raw_tmp) / "repo"
        repo.mkdir()
        counter = pathlib.Path(raw_tmp) / "counter.txt"
        artifact = write_runtime_fixture(repo, counter)
        args = ("--stage", "stage-a", "--level", "release")
        first = run_fixture_command(closeout, repo, *args)
        if first.returncode != 0:
            raise AssertionError(f"first evidence closeout failed: {first.stderr}")
        second = run_fixture_command(closeout, repo, *args, "--reuse")
        if second.returncode != 0:
            raise AssertionError(f"evidence reuse closeout failed: {second.stderr}")
        receipt = repo / ".codex" / "stages" / "stage-a" / "acceptance-receipt.json"
        if not receipt.is_file():
            raise AssertionError("closeout did not record acceptance receipt")
        receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
        common = pathlib.Path(
            subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                cwd=repo,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
        )
        if not common.is_absolute():
            common = repo / common
        report = json.loads(
            (common / receipt_payload["report_path"]).read_text(encoding="utf-8")
        )
        if report["steps"][0]["disposition"] != "cached":
            raise AssertionError("unchanged verification evidence did not produce a cache hit")

        (repo / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        changed = run_fixture_command(closeout, repo, *args, "--reuse")
        if changed.returncode != 0:
            raise AssertionError(f"source mutation closeout failed: {changed.stderr}")
        changed_receipt = json.loads(receipt.read_text(encoding="utf-8"))
        changed_report = json.loads(
            (common / changed_receipt["report_path"]).read_text(encoding="utf-8")
        )
        if changed_report["steps"][0]["disposition"] != "executed":
            raise AssertionError("source mutation inherited stale closeout success")

        event = {
            "event_id": "pending",
            "task_id": "stream-a",
            "stage_id": "stage-a",
            "status": "returned",
            "verify": "passed",
            "artifact_path": str(artifact.relative_to(repo)),
        }
        (repo / ".codex" / "stages" / "stage-a" / "events.ndjson").write_text(
            json.dumps(event) + "\n", encoding="utf-8"
        )
        pending = run_fixture_command(closeout, repo, *args, "--reuse")
        if pending.returncode == 0:
            raise AssertionError("pending completion event did not block cached closeout")

        review = run_fixture_command(reviewer, repo, "--json")
        if review.returncode != 0:
            raise AssertionError(f"reviewer rejected an exact pending event: {review.stderr}")
        payload = json.loads(review.stdout)
        if len(payload.get("pending", [])) != 1:
            raise AssertionError("reviewer did not expose the exact pending event")

        event["task_id"] = "stream-b"
        (repo / ".codex" / "stages" / "stage-a" / "events.ndjson").write_text(
            json.dumps(event) + "\n", encoding="utf-8"
        )
        mismatched_review = run_fixture_command(reviewer, repo, "--json")
        if mismatched_review.returncode == 0:
            raise AssertionError("reviewer accepted event/artifact task mismatch")


def main() -> int:
    for skill in ROOT.glob("*/SKILL.md"):
        check_skill(skill)

    setup_root = ROOT / "orchestration-setup"
    baseline = setup_root / "templates" / "baseline.toml"
    with baseline.open("rb") as fh:
        baseline_data = tomllib.load(fh)

    expected_profile = baseline_data.get("profile")
    if expected_profile != "balanced-v2.20":
        raise AssertionError(f"unexpected baseline profile: {expected_profile!r}")

    levels = baseline_data.get("orchestration_levels") or {}
    if levels.get("default") != "slice_acceptance":
        raise AssertionError("baseline orchestration default must be slice_acceptance")
    if levels.get("stage_levels") != ["slice_acceptance", "integration", "release"]:
        raise AssertionError("baseline stage levels are stale")

    handoff = baseline_data.get("handoff") or {}
    if handoff.get("current_state_max_lines") != 200 or handoff.get("hard_limit_lines") != 500:
        raise AssertionError("baseline handoff target must be 200 with a 500-line ceiling")

    skill_text = (setup_root / "SKILL.md").read_text(encoding="utf-8")
    verifier_text = (setup_root / "templates" / "scripts" / "run_process_verification.sh").read_text(
        encoding="utf-8"
    )
    if expected_profile not in skill_text or expected_profile not in verifier_text:
        raise AssertionError("baseline profile is not consistent across SKILL.md and verifier")

    delegation = baseline_data.get("delegation") or {}
    expected_delegation = {
        "subagents_preauthorized_for_medium_complex": True,
        "root_execution_scope": "holds_context",
        "medium_execution_default": "root_or_delegated_by_benefit",
        "complex_execution_default": "root_or_delegated_by_benefit",
        "simple_checks_owner": "orchestrator",
        "delegation_gate": "concrete_benefit",
        "delegation_unavailable_action": "continue_locally",
        "independence_alone_sufficient": False,
        "parallel_decomposition_matrix": "optional",
        "parallel_execution_default": "parallel_when_beneficial",
        "sequential_requires_reason": False,
    }
    actual_delegation = {key: delegation.get(key) for key in expected_delegation}
    if actual_delegation != expected_delegation:
        raise AssertionError(f"baseline delegation policy is stale: {actual_delegation!r}")
    if "subagents_preauthorized_for_complex" in delegation:
        raise AssertionError("baseline contains stale subagents_preauthorized_for_complex")
    if delegation.get("parallel_decomposition_matrix") != "optional":
        raise AssertionError("baseline PDM is optional; it is not a required step")
    if delegation.get("max_concurrent_subagents") != 4:
        raise AssertionError("baseline max_concurrent_subagents must be 4")
    if delegation.get("max_parallel_write_streams") != 3:
        raise AssertionError("baseline max_parallel_write_streams must be 3")
    if delegation.get("critical_path_priority") is not True:
        raise AssertionError("baseline must prioritize the critical path")
    if "requires_explicit_user_spawn_request" in delegation:
        raise AssertionError("baseline contains stale requires_explicit_user_spawn_request")

    stage_limits = baseline_data.get("stage_limits") or {}
    expected_stage_limits = {
        "epic_scope": "roadmap_only",
        "stage_unit": "cohesive_vertical_slice",
        "automatic_advance_after_acceptance": True,
        "replan_on_material_boundary": True,
        "cost_anomaly_action": "replan_not_stop",
        "hard_stop_on_time_or_token_budget": False,
        "continuation_lineage": "selected_beads_goal",
        "max_correction_loops": 2,
        "p0_p1_block_acceptance": True,
    }
    if {key: stage_limits.get(key) for key in expected_stage_limits} != expected_stage_limits:
        raise AssertionError("baseline stage limits do not enforce adaptive continuation")

    stage_sizing = baseline_data.get("stage_sizing") or {}
    expected_stage_sizing = {
        "mode": "cohesive_vertical_slice",
        "manifest_schema": "orchestration-stage/v1",
        "ledger_schema": "scope-preservation-ledger/v1",
        "scope_anchor_schema": "scope-criterion-snapshot/v1",
        "one_active_implementation_stage": True,
        "parallel_streams_inside_stage": True,
        "merge_adjacent_when_shared": [
            "acceptance_owner",
            "subsystem",
            "risk_model",
            "test_environment",
            "rollback_boundary",
            "acceptance_proof",
        ],
        "allowed_split_reasons": [
            "unresolved_public_ownership_or_public_contract",
            "hard_dependency",
            "independent_rollback_or_migration_boundary",
            "distinct_security_or_compliance_risk",
            "external_authorization",
        ],
        "scope_preservation_ledger_required_on_replan": True,
        "accepted_history_immutable": True,
        "migration_scope": "future_work_only",
    }
    if {key: stage_sizing.get(key) for key in expected_stage_sizing} != expected_stage_sizing:
        raise AssertionError("baseline stage sizing contract is stale")

    knowledge_graph = baseline_data.get("knowledge_graph") or {}
    expected_graph_policy = {
        "query_first": True,
        "freshness_check_required": True,
        "refresh_policy": "accepted_relevant_integration_or_release_boundary",
    }
    if {key: knowledge_graph.get(key) for key in expected_graph_policy} != expected_graph_policy:
        raise AssertionError("baseline knowledge graph activation policy is stale")

    verification_policy = baseline_data.get("verification_policy") or {}
    if verification_policy.get("mode") != "explicit":
        raise AssertionError("baseline verification policy must be explicit")
    if verification_policy.get("default_level") != "slice_acceptance":
        raise AssertionError("baseline verification default level must be slice_acceptance")
    removed_selectors = {
        "default_tier",
        "level_groups",
        "tier_groups",
        "risk_tag_groups",
        "surface_groups",
        "e2e_triggers",
    }
    if removed_selectors.intersection(verification_policy):
        raise AssertionError("baseline verification policy still defines selectors")

    model_policy = baseline_data.get("subagent_model_policy") or {}
    expected_model_policy = {
        "root_model": "gpt-6-astra",
        "root_execution": "may_keep_highest_critical_complex_context_coupled",
        "default_model": "inherit_orchestrator",
        "default_reasoning_effort": "inherit_orchestrator",
        "reasoning_policy": "directional_starters",
        "mechanical_model_starter": "gpt-5.6-luna",
        "mechanical_reasoning_starter": "low",
        "simpler_model_starter": "gpt-5.6-terra",
        "simpler_reasoning_starter": "medium",
        "complex_delegation_model_starter": "gpt-5.6-sol",
        "complex_delegation_reasoning_starter": "high",
        "fallback_model": "inherit_orchestrator",
        "fallback_reasoning_effort": "inherit_orchestrator",
        "model_override_requires_current_user_authorization": False,
        "record_spawn_decision_fields": [
            "role",
            "model",
            "reasoning_effort",
            "rationale",
        ],
        "record_model_reasoning_rationale": True,
        "unavailable_capability_action": "closest_supported_or_role_configured_or_keep_with_astra",
    }
    if {key: model_policy.get(key) for key in expected_model_policy} != expected_model_policy:
        raise AssertionError("baseline subagent model policy is stale")
    stale_model_keys = {
        "implementation_model",
        "high_risk_model",
        "high_reasoning_triggers",
        "high_reasoning_exclusions",
    }
    if stale_model_keys.intersection(model_policy):
        raise AssertionError("baseline contains stale rigid model routing keys")

    token_findings = audit_canonical(setup_root, setup_root.parent / "orchestrator-stage")
    if token_findings:
        details = "; ".join(
            f"{item['code']}: {item['detail']}" for item in token_findings
        )
        raise AssertionError(f"token-efficiency audit failed: {details}")

    for template_name in ("subagent-task-contract.md", "subagent-spawn-template.md"):
        template_text = (setup_root / "templates" / template_name).read_text(encoding="utf-8")
        if "Context7 / first-party" in template_text or "Documentation: Context7" in template_text:
            raise AssertionError(f"{template_name} contains stale Context7-primary wording")

    for script in (setup_root / "support").glob("*.py"):
        py_compile.compile(str(script), doraise=True)
    for script in (setup_root / "templates" / "scripts").glob("*.py"):
        py_compile.compile(str(script), doraise=True)
    for script in (setup_root / "templates" / "scripts").glob("*.sh"):
        subprocess.run(["bash", "-n", str(script)], check=True)

    check_proportional_runtime_regressions(setup_root)

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
