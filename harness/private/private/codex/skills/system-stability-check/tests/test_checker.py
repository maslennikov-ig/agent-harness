from __future__ import annotations

import importlib.util
import io
import json
import sys
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_system_stability.py"
SPEC = importlib.util.spec_from_file_location("stability_checker", SCRIPT)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class StabilityCheckerTests(unittest.TestCase):
    @staticmethod
    def base_report() -> dict[str, object]:
        return {
            "processes": {},
            "config": {"duplicate_mcp_plugin_sources": []},
            "memory": {"available_gib": 18.0, "swap_used_pct": 0.0},
            "disk": {},
            "caches": {},
            "latency": [],
            "collector_errors": [],
        }

    def test_warns_for_observed_process_and_config_pressure(self) -> None:
        report = {
            "processes": {
                "lazyweb": {"count": 78, "rss_mib": 4189.4, "max_etime_seconds": 90000},
                "node-test": {"count": 2, "rss_mib": 900, "max_etime_seconds": 172800},
                "codex-app-server": {"count": 1, "rss_mib": 5000, "max_etime_seconds": 430000},
            },
            "config": {"duplicate_mcp_plugin_sources": ["lazyweb"]},
            "memory": {"available_gib": 18.0, "swap_used_pct": 46.0},
            "disk": {},
            "caches": {},
            "latency": [],
        }

        warnings = checker.build_warnings(report)

        self.assertTrue(any("lazyweb" in item and "process" in item for item in warnings))
        self.assertTrue(any("node test" in item and "stale" in item for item in warnings))
        self.assertTrue(any("app-server" in item for item in warnings))
        self.assertTrue(any("duplicate MCP/plugin source" in item for item in warnings))

    def test_redacts_bearer_and_authorization_tokens(self) -> None:
        value = (
            "Authorization: Bearer secret-value --header Bearer another-secret "
            "--api-key=third-secret OPENAI_API_KEY=fourth-secret "
            '"SUPABASE_ACCESS_TOKEN": "fifth-secret" '
            "GITHUB_TOKEN=sixth-secret --token=seventh-secret --token eighth-secret "
            '\"NPM_TOKEN\": \"ninth-secret\"'
        )
        redacted = checker.redact(value)
        for secret in (
            "secret-value",
            "another-secret",
            "third-secret",
            "fourth-secret",
            "fifth-secret",
            "sixth-secret",
            "seventh-secret",
            "eighth-secret",
            "ninth-secret",
        ):
            self.assertNotIn(secret, redacted)

    def test_config_search_redacts_before_storage_and_uses_one_scan(self) -> None:
        output = (
            "/tmp/config.toml:1:sequential-thinking Authorization: Bearer hidden UNRECOGNIZED_CREDENTIAL=opaque\n"
            "/tmp/mcp.json:2:@supabase/mcp OPENAI_API_KEY=also-hidden\n"
        )
        fake = SimpleNamespace(returncode=0, stdout=output, stderr="")
        with patch.object(checker, "run", return_value=fake) as mocked:
            result = checker.config_search(Path("/tmp"), Path("/tmp"))

        self.assertEqual(1, mocked.call_count)
        self.assertNotIn("hidden", repr(result))
        self.assertNotIn("opaque", repr(result))
        self.assertIn("<matched", repr(result))
        self.assertTrue(result["sequential-thinking"])
        self.assertTrue(result["@supabase/mcp"])

    def test_code_mode_batching_guidance_reports_single_global_copy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / "agents").mkdir()
            compact_guidance = (
                "- In Code Mode, batch independent `functions.exec` calls per bounded "
                "stage in one call: keep dependent or conflicting work sequential.\n"
            )
            (home / "AGENTS.md").write_text(
                compact_guidance,
                encoding="utf-8",
            )
            (home / "agents" / "reviewer.toml").write_text(
                'developer_instructions = "Review the assigned diff."\n',
                encoding="utf-8",
            )

            report = checker.code_mode_batching_guidance_report(home)

        self.assertEqual("pass", report["status"])
        self.assertEqual(1, report["global_occurrences"])
        self.assertEqual([], report["custom_agent_duplicates"])

    def test_code_mode_batching_guidance_ignores_rule_without_bounded_stage(self) -> None:
        similar_but_not_managed = (
            "In Code Mode, batch independent functions.exec calls in one call; "
            "keep dependencies sequential."
        )

        self.assertEqual(
            0,
            checker.code_mode_batching_guidance_count(similar_but_not_managed),
        )

    def test_code_mode_batching_guidance_ignores_negated_rule(self) -> None:
        negated = (
            "In Code Mode, do not batch independent `functions.exec` calls per "
            "bounded stage in one call: keep dependencies sequential."
        )

        self.assertEqual(0, checker.code_mode_batching_guidance_count(negated))

    def test_code_mode_batching_guidance_ignores_unrelated_separated_phrases(self) -> None:
        unrelated = (
            "In Code Mode, batch independent functions.exec calls when useful. "
            "A bounded stage is documented elsewhere. "
            "Keep dependencies sequential for database writes."
        )

        self.assertEqual(0, checker.code_mode_batching_guidance_count(unrelated))

    def test_code_mode_batching_guidance_warns_when_missing_or_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / "agents").mkdir()
            (home / "AGENTS.md").write_text("# Global\n", encoding="utf-8")
            (home / "agents" / "reviewer.toml").write_text(
                "In Code Mode, batch independent functions.exec calls in one bounded stage with "
                "Promise.allSettled or Promise.all; keep dependencies sequential.",
                encoding="utf-8",
            )

            report = checker.code_mode_batching_guidance_report(home)

        self.assertEqual("warn", report["status"])
        self.assertEqual(0, report["global_occurrences"])
        self.assertEqual(["reviewer.toml"], report["custom_agent_duplicates"])
        stability = self.base_report()
        stability["code_mode_batching"] = report
        self.assertTrue(
            any(
                "Code Mode batching guidance" in item
                for item in checker.build_warnings(stability)
            )
        )

    def test_process_classification_covers_common_tests_and_generic_mcp(self) -> None:
        cases = {
            "/usr/bin/node --test tests/a.js": "node-test",
            "/usr/bin/node node_modules/vitest/vitest.mjs run": "vitest",
            "/usr/bin/node node_modules/jest/bin/jest.js": "jest",
            "npx @vendor/new-mcp-server": "other-mcp",
            "/tmp/magic/report.py": None,
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(expected, checker.classify_process(command))

    def test_process_report_tracks_duplicate_groups_inside_one_session(self) -> None:
        output = "\n".join(
            (
                "100 1 100 42 1024 120 0.0 npm exec lazyweb mcp",
                "101 100 100 42 2048 119 0.0 node lazyweb mcp",
                "200 1 200 42 1024 60 0.0 npm exec lazyweb mcp",
                "201 200 200 42 2048 59 0.0 node lazyweb mcp",
            )
        )
        completed = SimpleNamespace(returncode=0, stdout=output, stderr="")
        with patch.object(checker, "bounded_run", return_value=completed):
            report = checker.process_report([])

        lazyweb = report["lazyweb"]
        self.assertEqual(2, lazyweb["process_group_count"])
        self.assertEqual(1, lazyweb["session_count"])
        self.assertEqual(2, lazyweb["recent_process_group_count"])

    def test_warns_for_many_recent_mcp_groups_in_one_session(self) -> None:
        report = self.base_report()
        report["processes"] = {
            "lazyweb": {
                "count": 24,
                "rss_mib": 1800.0,
                "max_etime_seconds": 600,
                "process_group_count": 8,
                "session_count": 1,
                "recent_process_group_count": 8,
            }
        }

        warnings = checker.build_warnings(report)

        joined = "\n".join(warnings)
        self.assertIn("same session", joined)
        self.assertIn("8 recent", joined)

    def test_warnings_cover_unknown_mcp_stale_runners_heavy_servers_and_latency(self) -> None:
        report = {
            "processes": {
                "other-mcp": {"count": 20, "rss_mib": 4096, "max_etime_seconds": 100},
                "vitest": {"count": 1, "rss_mib": 200, "max_etime_seconds": 21601},
                "next-server": {"count": 1, "rss_mib": 5000, "max_etime_seconds": 100},
            },
            "config": {"duplicate_mcp_plugin_sources": []},
            "memory": {"available_gib": 18.0, "swap_used_pct": 0.0},
            "disk": {},
            "caches": {},
            "latency": [
                {"command": "node -v", "avg_ms": 5000, "returncodes": [0, 0]},
                {"command": "git -C /tmp status --short", "avg_ms": 5000, "returncodes": [0, 0]},
            ],
            "collector_errors": ["process scan timed out"],
        }

        warnings = checker.build_warnings(report)
        joined = "\n".join(warnings)
        for marker in ("other-mcp", "stale vitest", "next-server", "node startup", "git status", "incomplete"):
            self.assertIn(marker, joined)

    def test_disabled_mcp_is_not_reported_as_active_or_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / "config.toml").write_text(
                '[mcp_servers.lazyweb]\nenabled = false\ncommand = "lazyweb"\n'
                '[plugins."lazyweb@lazyweb"]\nenabled = true\n',
                encoding="utf-8",
            )
            result = checker.codex_config_report(home)

        self.assertNotIn("lazyweb", result["mcp_servers"])
        self.assertIn("lazyweb", result["disabled_mcp_servers"])
        self.assertEqual([], result["duplicate_mcp_plugin_sources"])

    def test_failed_process_collection_is_explicit(self) -> None:
        errors: list[str] = []
        failed = SimpleNamespace(returncode=124, stdout="", stderr="timed out")
        with patch.object(checker, "run", return_value=failed):
            self.assertEqual({}, checker.process_report(errors))
        self.assertTrue(any("process scan" in item for item in errors))

    def test_optional_cache_timeout_is_a_note_not_a_health_error(self) -> None:
        errors: list[str] = []
        notes: list[str] = []
        failed = SimpleNamespace(returncode=124, stdout="", stderr="timed out")
        with tempfile.TemporaryDirectory() as raw, patch.object(checker, "bounded_run", return_value=failed):
            value = checker.du_path(Path(raw), errors=errors, notes=notes)
        self.assertEqual("unavailable", value)
        self.assertEqual([], errors)
        self.assertTrue(any("cache size scan" in item for item in notes))

    def test_latency_timeout_is_a_required_collection_error(self) -> None:
        errors: list[str] = []
        failed = SimpleNamespace(returncode=124, stdout="", stderr="timed out")
        with (
            patch.object(checker, "choose_git_workspace", return_value=Path("/tmp")),
            patch.object(checker, "bounded_run", return_value=failed),
        ):
            checker.latency_report(Path("/tmp"), errors)
        self.assertTrue(any("latency check timed out" in item for item in errors))

    def test_invalid_codex_config_is_an_explicit_collection_error(self) -> None:
        errors: list[str] = []
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / "config.toml").write_text("[broken\n", encoding="utf-8")
            result = checker.codex_config_report(home, errors)
        self.assertTrue(result["exists"])
        self.assertIn("parse_error", result)
        self.assertTrue(any("Codex config parse failed" in item for item in errors))

    def test_timeout_output_is_normalized_to_text_for_json_safety(self) -> None:
        timeout = subprocess.TimeoutExpired(["tool"], 1, output=b"partial")
        with patch.object(checker.subprocess, "run", side_effect=timeout):
            result = checker.run(["tool"], timeout=1)
        self.assertIsInstance(result.stdout, str)
        self.assertEqual("partial", result.stdout)

    def test_harness_latency_report_runs_full_machine_contract(self) -> None:
        payload = {
            "schema_version": "orchestration-latency/v1",
            "build_id": "abc123",
            "status": "pass",
            "quick": False,
            "elapsed_ms": 8200.0,
            "budget_ms": 12000,
            "checks": [
                {
                    "name": name,
                    "status": "pass",
                    "elapsed_ms": 900.0,
                    "budget_ms": 5000,
                    "detail": {"repo_count": 30},
                    "error": None,
                }
                for name in checker.HARNESS_BENCHMARK_CHECKS
            ],
        }
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        errors: list[str] = []
        notes: list[str] = []

        with (
            patch.object(checker.shutil, "which", return_value="/usr/local/bin/orch-prompts"),
            patch.object(checker, "bounded_run", return_value=completed) as mocked,
        ):
            result = checker.harness_latency_report(errors, notes)

        self.assertEqual("pass", result["status"])
        self.assertFalse(result["quick"])
        self.assertEqual(checker.HARNESS_BENCHMARK_CHECKS, {item["name"] for item in result["checks"]})
        self.assertEqual([], errors)
        self.assertEqual([], notes)
        command = mocked.call_args.args[0]
        self.assertEqual(
            ["/usr/local/bin/orch-prompts", "benchmark", "--json"],
            command,
        )
        self.assertEqual(20.0, mocked.call_args.kwargs["timeout"])

    def test_bounded_test_runner_health_executes_a_synthetic_node_test(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        errors: list[str] = []
        notes: list[str] = []
        with tempfile.TemporaryDirectory() as raw:
            runner = Path(raw) / "run_bounded_node_tests.py"
            runner.write_text("# fixture\n", encoding="utf-8")
            with patch.object(checker, "bounded_run", return_value=completed) as mocked:
                report = checker.bounded_test_runner_report(errors, notes, runner_path=runner)

        self.assertEqual("pass", report["status"])
        self.assertEqual([], errors)
        command = mocked.call_args.args[0]
        self.assertEqual(sys.executable, command[0])
        self.assertEqual(str(runner), command[1])
        self.assertIn("--node-timeout-ms", command)
        self.assertIn("--wall-timeout-seconds", command)

    def test_bounded_test_runner_failure_is_required_stability_evidence(self) -> None:
        failed = SimpleNamespace(returncode=125, stdout="", stderr="surviving process-group members")
        errors: list[str] = []
        notes: list[str] = []
        with tempfile.TemporaryDirectory() as raw:
            runner = Path(raw) / "run_bounded_node_tests.py"
            runner.write_text("# fixture\n", encoding="utf-8")
            with patch.object(checker, "bounded_run", return_value=failed):
                report = checker.bounded_test_runner_report(errors, notes, runner_path=runner)

        self.assertEqual("error", report["status"])
        self.assertTrue(any("bounded Node test runner" in item for item in errors))

    def test_harness_latency_warning_names_slow_checks(self) -> None:
        report = self.base_report()
        report["harness_latency"] = {
            "available": True,
            "status": "warn",
            "elapsed_ms": 14100.0,
            "budget_ms": 12000,
            "checks": [
                {
                    "name": "tails",
                    "status": "warn",
                    "elapsed_ms": 6100.0,
                    "budget_ms": 5000,
                    "error": None,
                },
                {
                    "name": "panel_server",
                    "status": "warn",
                    "elapsed_ms": 10.0,
                    "budget_ms": 250,
                    "error": "panel server is offline or runs a stale build",
                },
            ],
        }

        warnings = checker.build_warnings(report)

        joined = "\n".join(warnings)
        self.assertIn("Harness latency benchmark", joined)
        self.assertIn("tails", joined)
        self.assertIn("panel_server", joined)

    def test_missing_harness_runner_is_an_optional_note(self) -> None:
        errors: list[str] = []
        notes: list[str] = []
        with patch.object(checker.shutil, "which", return_value=None):
            result = checker.harness_latency_report(errors, notes)

        self.assertFalse(result["available"])
        self.assertEqual("unavailable", result["status"])
        self.assertEqual([], errors)
        self.assertTrue(any("orch-prompts" in item for item in notes))

    def test_invalid_harness_contract_is_required_evidence_error(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout='{"schema_version":"wrong"}', stderr="")
        errors: list[str] = []
        notes: list[str] = []
        with (
            patch.object(checker.shutil, "which", return_value="/usr/local/bin/orch-prompts"),
            patch.object(checker, "bounded_run", return_value=completed),
        ):
            result = checker.harness_latency_report(errors, notes)

        self.assertEqual("error", result["status"])
        self.assertTrue(any("contract" in item for item in errors))

    def test_harness_contract_requires_all_full_benchmark_checks(self) -> None:
        payload = {
            "schema_version": "orchestration-latency/v1",
            "build_id": "abc123",
            "status": "pass",
            "quick": False,
            "elapsed_ms": 100.0,
            "budget_ms": 12000,
            "checks": [
                {
                    "name": "prompt_compose",
                    "status": "pass",
                    "elapsed_ms": 10.0,
                    "budget_ms": 250,
                    "detail": {},
                    "error": None,
                }
            ],
        }
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        errors: list[str] = []
        with (
            patch.object(checker.shutil, "which", return_value="/usr/local/bin/orch-prompts"),
            patch.object(checker, "bounded_run", return_value=completed),
        ):
            result = checker.harness_latency_report(errors, [])

        self.assertEqual("error", result["status"])
        self.assertTrue(any("contract" in item for item in errors))

    def test_human_report_prints_harness_latency_section(self) -> None:
        report = self.base_report()
        report.update(
            {
                "host": "test-host",
                "codex_home": "/tmp/codex",
                "workspace": "/tmp/workspace",
                "harness_latency": {
                    "available": True,
                    "build_id": "abc123",
                    "status": "pass",
                    "elapsed_ms": 8200.0,
                    "budget_ms": 12000,
                    "checks": [],
                },
                "config_search": {},
                "code_mode_batching": {
                    "status": "pass",
                    "global_occurrences": 1,
                    "custom_agent_duplicates": [],
                },
                "collector_notes": [],
                "warnings": [],
            }
        )
        output = io.StringIO()

        with redirect_stdout(output):
            checker.print_human(report)

        self.assertIn("Harness latency:", output.getvalue())
        self.assertIn("8200.0 ms / 12000 ms", output.getvalue())
        self.assertIn("Code Mode batching guidance:", output.getvalue())
        self.assertIn("global_occurrences=1", output.getvalue())


if __name__ == "__main__":
    unittest.main()
