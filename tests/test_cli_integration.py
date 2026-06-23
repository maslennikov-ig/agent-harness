import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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
