import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExportLocalTests(unittest.TestCase):
    def run_cli(self, *args, env=None):
        return subprocess.run(
            [sys.executable, "-m", "harness_core.cli", *args],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_bootstrap_agent_prompt_is_committed(self):
        prompt = ROOT / "docs" / "prompts" / "bootstrap-agent.md"

        self.assertTrue(prompt.exists())
        text = prompt.read_text(encoding="utf-8")
        self.assertIn("harness plan", text)
        self.assertIn("harness bootstrap --profile full", text)
        self.assertIn("harness doctor", text)
        self.assertIn("--private", text)

    def test_export_local_private_overlay_from_temp_homes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            codex_home = root / "codex"
            agents_home = root / "agents"
            claude_home = root / "claude"
            target = root / "overlay"
            (codex_home / "agents").mkdir(parents=True)
            (agents_home / "skills" / "custom-skill").mkdir(parents=True)
            (claude_home / "agents").mkdir(parents=True)
            (claude_home / "skills" / "personal-skill").mkdir(parents=True)
            (claude_home / "skills" / "orchestration-bridge").mkdir(parents=True)
            (codex_home / "agents" / "private-agent.toml").write_text("name = 'private'\n", encoding="utf-8")
            (agents_home / "skills" / "custom-skill" / "SKILL.md").write_text("# Custom\n", encoding="utf-8")
            (claude_home / "agents" / "claude-agent.md").write_text("# Claude Agent\n", encoding="utf-8")
            (claude_home / "skills" / "personal-skill" / "SKILL.md").write_text("# Personal\n", encoding="utf-8")
            (claude_home / "skills" / "orchestration-bridge" / "plugin.json").write_text("{}\n", encoding="utf-8")
            env = {
                **os.environ,
                "CODEX_HOME": str(codex_home),
                "AGENTS_HOME": str(agents_home),
                "CLAUDE_HOME": str(claude_home),
            }

            result = self.run_cli("export-local", "--scope", "private", "--target", str(target), "--yes", "--json", env=env)

            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["scope"], "private")
            self.assertGreaterEqual(data["copied"], 4)
            self.assertEqual((target / "private" / "codex" / "agents" / "private-agent.toml").read_text(encoding="utf-8"), "name = 'private'\n")
            self.assertEqual((target / "private" / "codex" / "skills" / "custom-skill" / "SKILL.md").read_text(encoding="utf-8"), "# Custom\n")
            self.assertEqual((target / "private" / "claude" / "agents" / "claude-agent.md").read_text(encoding="utf-8"), "# Claude Agent\n")
            self.assertEqual((target / "private" / "claude" / "skills" / "personal-skill" / "SKILL.md").read_text(encoding="utf-8"), "# Personal\n")
            self.assertFalse((target / "private" / "claude" / "skills" / "orchestration-bridge").exists())
            self.assertTrue((target / "overlay.manifest.json").exists())
            manifest = json.loads((target / "overlay.manifest.json").read_text(encoding="utf-8"))
            components = {component["name"]: component for component in manifest["components"]}
            self.assertEqual(
                components["private-claude-skills"],
                {
                    "name": "private-claude-skills",
                    "type": "copy_tree",
                    "source": "${HARNESS_REPO}/private/claude/skills",
                    "target": "${CLAUDE_HOME}/skills",
                },
            )

    def test_private_overlay_template_includes_claude_skills(self):
        manifest = json.loads((ROOT / "templates" / "private-overlay" / "overlay.manifest.json").read_text(encoding="utf-8"))
        components = {component["name"]: component for component in manifest["components"]}
        self.assertEqual(
            components["private-claude-skills"]["source"],
            "${HARNESS_REPO}/private/claude/skills",
        )
        self.assertEqual(
            components["private-claude-skills"]["target"],
            "${CLAUDE_HOME}/skills",
        )

    def test_export_local_upgrades_existing_manifest_without_losing_custom_components(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            claude_home = root / "claude"
            target = root / "overlay"
            (claude_home / "skills" / "personal-skill").mkdir(parents=True)
            (claude_home / "skills" / "personal-skill" / "SKILL.md").write_text("# Personal\n", encoding="utf-8")
            target.mkdir()
            existing = {
                "schema_version": 1,
                "custom_setting": {"preserve": True},
                "components": [
                    {
                        "name": "custom-component",
                        "type": "copy_tree",
                        "source": "${HARNESS_REPO}/custom",
                        "target": "${HARNESS_HOME}/custom",
                    }
                ],
            }
            (target / "overlay.manifest.json").write_text(json.dumps(existing, indent=4) + "\n", encoding="utf-8")
            env = {
                **os.environ,
                "CODEX_HOME": str(root / "codex"),
                "AGENTS_HOME": str(root / "agents"),
                "CLAUDE_HOME": str(claude_home),
            }

            result = self.run_cli("export-local", "--scope", "private", "--target", str(target), "--yes", "--json", env=env)

            self.assertEqual(result.returncode, 0, result.stderr)
            second_result = self.run_cli("export-local", "--scope", "private", "--target", str(target), "--yes", "--json", env=env)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            upgraded = json.loads((target / "overlay.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(upgraded["custom_setting"], {"preserve": True})
            components = {component["name"]: component for component in upgraded["components"]}
            self.assertEqual(
                [component["name"] for component in upgraded["components"]].count("private-claude-skills"),
                1,
            )
            self.assertEqual(components["custom-component"], existing["components"][0])
            self.assertEqual(
                components["private-claude-skills"],
                {
                    "name": "private-claude-skills",
                    "type": "copy_tree",
                    "source": "${HARNESS_REPO}/private/claude/skills",
                    "target": "${CLAUDE_HOME}/skills",
                },
            )

    def test_export_local_rejects_conflicting_managed_component(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "overlay"
            target.mkdir()
            existing = {
                "schema_version": 1,
                "components": [
                    {
                        "name": "private-claude-skills",
                        "type": "copy_tree",
                        "source": "${HARNESS_REPO}/private/claude/skills",
                        "target": "${CLAUDE_HOME}/wrong-target",
                    }
                ],
            }
            manifest = target / "overlay.manifest.json"
            original = json.dumps(existing, indent=2) + "\n"
            manifest.write_text(original, encoding="utf-8")
            env = {
                **os.environ,
                "CODEX_HOME": str(root / "codex"),
                "AGENTS_HOME": str(root / "agents"),
                "CLAUDE_HOME": str(root / "claude"),
            }

            result = self.run_cli("export-local", "--scope", "private", "--target", str(target), "--yes", env=env)

            self.assertEqual(result.returncode, 1)
            self.assertIn("conflicting managed component private-claude-skills", result.stderr)
            self.assertEqual(manifest.read_text(encoding="utf-8"), original)

    def test_export_local_refuses_secret_like_content(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            codex_home = root / "codex"
            agents_home = root / "agents"
            claude_home = root / "claude"
            target = root / "overlay"
            (agents_home / "skills" / "leaky").mkdir(parents=True)
            (agents_home / "skills" / "leaky" / "SKILL.md").write_text("token = 'sk-test-secret-value-1234567890'\n", encoding="utf-8")
            env = {
                **os.environ,
                "CODEX_HOME": str(codex_home),
                "AGENTS_HOME": str(agents_home),
                "CLAUDE_HOME": str(claude_home),
            }

            result = self.run_cli("export-local", "--scope", "private", "--target", str(target), "--yes", env=env)

            self.assertEqual(result.returncode, 1)
            self.assertIn("secret-like content", result.stderr)
            self.assertFalse((target / "private" / "codex" / "skills" / "leaky" / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
