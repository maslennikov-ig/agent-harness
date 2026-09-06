import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "orchestration_panel.py"
SPEC = importlib.util.spec_from_file_location("public_orchestration_panel", MODULE_PATH)
panel = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = panel
SPEC.loader.exec_module(panel)


class PublicConsoleInventoryTests(unittest.TestCase):
    def test_wrapper_plugins_are_separate_from_native_claude_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            console = temp / "console"
            harness_home = temp / "harness-home"
            console.mkdir()
            (console / "release-manifest.json").write_text("{}\n", encoding="utf-8")

            for name, skills, agents in (
                ("orchestration-bridge", ("stage",), ("worker",)),
                ("superpowers", ("brainstorming", "verification"), ()),
            ):
                plugin = harness_home / "plugins" / name
                manifest = plugin / ".claude-plugin" / "plugin.json"
                manifest.parent.mkdir(parents=True)
                manifest.write_text(
                    json.dumps({"name": name, "version": "1.0.0"}),
                    encoding="utf-8",
                )
                for skill in skills:
                    path = plugin / "skills" / skill / "SKILL.md"
                    path.parent.mkdir(parents=True)
                    path.write_text(f"---\nname: {skill}\ndescription: Test\n---\n", encoding="utf-8")
                for agent in agents:
                    path = plugin / "agents" / f"{agent}.md"
                    path.parent.mkdir(parents=True)
                    path.write_text(f"---\nname: {agent}\ndescription: Test\n---\n", encoding="utf-8")

            old_console = panel.CONSOLE_DIR
            old_binary = panel.claude_binary
            old_harness_home = os.environ.get("HARNESS_HOME")
            panel.CONSOLE_DIR = console
            panel.claude_binary = lambda: None
            os.environ["HARNESS_HOME"] = str(harness_home)
            try:
                summary = panel.build_claude_plugins_summary()
            finally:
                panel.CONSOLE_DIR = old_console
                panel.claude_binary = old_binary
                if old_harness_home is None:
                    os.environ.pop("HARNESS_HOME", None)
                else:
                    os.environ["HARNESS_HOME"] = old_harness_home

        self.assertEqual(summary["items"], [])
        self.assertEqual(summary["inventory_scope"], "native-claude-plugin-registry")
        self.assertEqual(summary["wrapper"]["installed_count"], 2)
        self.assertEqual(summary["wrapper"]["skills"], 3)
        self.assertEqual(summary["wrapper"]["agents"], 1)
        self.assertFalse(summary["wrapper"]["runtime_load_verified"])
        self.assertEqual(summary["wrapper"]["plain_claude_registration"], "not-claimed")


if __name__ == "__main__":
    unittest.main()
