import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from harness_core.cli import install_component
from harness_core.managed import ManagedInstaller
from harness_core.manifest import Component

ROOT = Path(__file__).resolve().parents[1]


class CliIntegrationTests(unittest.TestCase):
    def run_cli(self, *args, cwd=None, env=None, input_text=None):
        return subprocess.run(
            [sys.executable, "-m", "harness_core.cli", *args],
            cwd=cwd or ROOT,
            env=env,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_plan_bootstrap_doctor_and_lock_for_local_copy_component(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "assets" / "skills"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            target = root / "home" / "skills"
            manifest = root / "manifest.json"
            lock = root / "lock.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "components": [
                    {
                        "name": "codex-skills",
                        "type": "copy_tree",
                        "source": str(source),
                        "target": str(target),
                        "doctor": [{"type": "path_exists", "path": str(target / "SKILL.md")}],
                    }
                ],
            }), encoding="utf-8")

            plan = self.run_cli("plan", "--manifest", str(manifest), "--json")
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertEqual(json.loads(plan.stdout)["components"][0]["action"], "install")

            bootstrap = self.run_cli("bootstrap", "--manifest", str(manifest), "--lock", str(lock), "--yes")
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "# Skill\n")

            doctor = self.run_cli("doctor", "--manifest", str(manifest), "--json")
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            self.assertEqual(json.loads(doctor.stdout)["components"][0]["status"], "ok")
            self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["components"][0]["status"], "ok")

    def test_bootstrap_runs_install_command_for_missing_binary_component(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bin_dir = root / "bin"
            tool = bin_dir / "demo-tool"
            manifest = root / "manifest.json"
            lock = root / "lock.json"
            installer = (
                "from pathlib import Path; "
                f"path = Path({str(tool)!r}); "
                "path.parent.mkdir(parents=True, exist_ok=True); "
                "path.write_text('#!/usr/bin/env sh\\necho demo-tool 1.2.3\\n', encoding='utf-8'); "
                "path.chmod(0o755)"
            )
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "components": [
                    {
                        "name": "demo-tool",
                        "type": "binary",
                        "target": "demo-tool",
                        "install": [[sys.executable, "-c", installer]],
                        "doctor": [{"type": "command", "command": ["demo-tool", "--version"]}],
                    }
                ],
            }), encoding="utf-8")
            env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

            result = self.run_cli("bootstrap", "--manifest", str(manifest), "--lock", str(lock), "--yes", env=env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(tool.exists())
            self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["components"][0]["status"], "ok")

    def test_managed_block_bootstrap_updates_only_marked_region_and_doctor_checks_it(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "fragment.md"
            target = root / "codex" / "AGENTS.md"
            installer = root / "install_fragment.py"
            manifest = root / "overlay.manifest.json"
            lock = root / "lock.json"
            begin = "<!-- TEST-BLOCK:BEGIN -->"
            end = "<!-- TEST-BLOCK:END -->"
            source.write_text("managed version one\n", encoding="utf-8")
            target.parent.mkdir(parents=True)
            target.write_text("# User rules\n\nKeep this text.\n", encoding="utf-8")
            installer.write_text(textwrap.dedent(f"""\
                #!{sys.executable}
                from pathlib import Path
                import sys

                BEGIN = {begin!r}
                END = {end!r}
                source = Path(sys.argv[1])
                target = Path(sys.argv[2])
                existing = target.read_text(encoding="utf-8") if target.exists() else ""
                block = BEGIN + "\\n" + source.read_text(encoding="utf-8").strip() + "\\n" + END
                if BEGIN in existing and END in existing:
                    prefix, tail = existing.split(BEGIN, 1)
                    _, suffix = tail.split(END, 1)
                    content = prefix.rstrip() + "\\n\\n" + block + suffix.rstrip() + "\\n"
                elif existing.strip():
                    content = existing.rstrip() + "\\n\\n" + block + "\\n"
                else:
                    content = block + "\\n"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                """), encoding="utf-8")
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "components": [
                    {
                        "name": "codex-global",
                        "type": "managed_block",
                        "source": str(source),
                        "target": str(target),
                        "installer": str(installer),
                        "markers": [begin, end],
                    }
                ],
            }), encoding="utf-8")

            before = self.run_cli("doctor", "--manifest", str(manifest), "--json")
            self.assertEqual(before.returncode, 2, before.stderr)
            self.assertIn("missing managed markers", before.stdout)

            first = self.run_cli(
                "bootstrap", "--manifest", str(manifest), "--lock", str(lock), "--yes"
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            installed = target.read_text(encoding="utf-8")
            self.assertIn("# User rules", installed)
            self.assertIn("Keep this text.", installed)
            self.assertIn("managed version one", installed)
            self.assertEqual(installed.count(begin), 1)

            source.write_text("managed version two\n", encoding="utf-8")
            stale = self.run_cli("doctor", "--manifest", str(manifest), "--json")
            self.assertEqual(stale.returncode, 2, stale.stderr)
            self.assertIn("managed block differs from source", stale.stdout)

            second = self.run_cli(
                "bootstrap", "--manifest", str(manifest), "--lock", str(lock), "--yes"
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            updated = target.read_text(encoding="utf-8")
            self.assertIn("# User rules", updated)
            self.assertIn("Keep this text.", updated)
            self.assertIn("managed version two", updated)
            self.assertNotIn("managed version one", updated)
            self.assertEqual(updated.count(begin), 1)

            doctor = self.run_cli("doctor", "--manifest", str(manifest), "--json")
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            self.assertEqual(json.loads(doctor.stdout)["components"][0]["status"], "ok")
            lock_record = json.loads(lock.read_text(encoding="utf-8"))["components"][0]
            self.assertEqual(lock_record["status"], "ok")
            self.assertNotEqual(lock_record["version"], "")

    def test_managed_block_runs_python_installer_without_executable_bit(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "fragment.md"
            installer = root / "install.py"
            target = root / "AGENTS.md"
            source.write_text("managed\n", encoding="utf-8")
            installer.write_text("raise SystemExit(0)\n", encoding="utf-8")
            component = Component(
                name="codex-global",
                type="managed_block",
                source=source,
                target=target,
                installer=installer,
                markers=("<!-- BEGIN -->", "<!-- END -->"),
            )

            with mock.patch("harness_core.cli.subprocess.run") as run:
                install_component(component, ManagedInstaller(root / "state"))

            run.assert_called_once_with(
                [sys.executable, str(installer), str(source), str(target)],
                check=True,
            )

    def test_init_project_writes_baseline_without_global_mutation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            template = root / "project-template"
            repo.mkdir()
            template.mkdir()
            (template / "AGENTS.md").write_text("# Agent Rules\n", encoding="utf-8")
            (template / ".codex").mkdir()
            (template / ".codex" / "orchestrator.toml").write_text("[project]\n", encoding="utf-8")

            result = self.run_cli("init-project", str(repo), "--template", str(template), "--yes")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((repo / "AGENTS.md").read_text(encoding="utf-8"), "# Agent Rules\n")
            self.assertEqual((repo / ".codex" / "orchestrator.toml").read_text(encoding="utf-8"), "[project]\n")
            self.assertFalse((root / ".codex").exists())


    def test_bootstrap_private_overlay_exposes_decrypted_secrets_only_during_run(self):
        from harness_core.secrets import SecretVault

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            public_manifest = root / "public.json"
            lock = root / "lock.json"
            private = root / "private"
            private_assets = private / "private" / "codex" / "agents"
            target = root / "target"
            private_assets.mkdir(parents=True)
            (private_assets / "agent.toml").write_text("name = 'private'\n", encoding="utf-8")
            (private / "overlay.manifest.json").write_text(json.dumps({
                "schema_version": 1,
                "components": [
                    {
                        "name": "private-agents",
                        "type": "copy_tree",
                        "source": "${HARNESS_REPO}/private/codex/agents",
                        "target": str(target),
                        "doctor": [{
                            "type": "command",
                            "command": [
                                sys.executable,
                                "-c",
                                "import os; assert os.environ['PRIVATE_TOKEN'] == 'secret'; assert os.path.exists(os.environ['HARNESS_SECRETS_FILE'])",
                            ],
                        }],
                    }
                ],
            }), encoding="utf-8")
            SecretVault().write_encrypted(private / "secrets.enc.json", {"PRIVATE_TOKEN": "secret"}, passphrase="pw")
            public_manifest.write_text(json.dumps({"schema_version": 1, "components": []}), encoding="utf-8")

            result = self.run_cli(
                "bootstrap",
                "--manifest",
                str(public_manifest),
                "--private",
                str(private),
                "--lock",
                str(lock),
                "--yes",
                input_text="pw\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((target / "agent.toml").read_text(encoding="utf-8"), "name = 'private'\n")
            self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["components"][0]["name"], "private-agents")


if __name__ == "__main__":
    unittest.main()
