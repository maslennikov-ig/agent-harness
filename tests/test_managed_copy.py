import tempfile
import unittest
from pathlib import Path

from harness_core.managed import ManagedInstaller


class ManagedCopyTests(unittest.TestCase):
    def test_install_tree_updates_managed_files_and_backs_up_existing_changes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "skill.md").write_text("version one\n", encoding="utf-8")
            target.mkdir()
            (target / "skill.md").write_text("local edit\n", encoding="utf-8")
            (target / "unmanaged.md").write_text("keep me\n", encoding="utf-8")

            installer = ManagedInstaller(state_dir=root / ".harness")
            result = installer.install_tree(source, target, component="codex-skills")

            self.assertEqual((target / "skill.md").read_text(encoding="utf-8"), "version one\n")
            self.assertEqual((target / "unmanaged.md").read_text(encoding="utf-8"), "keep me\n")
            self.assertEqual(result.installed, 1)
            self.assertEqual(result.backed_up, 1)

            backups = list((root / ".harness" / "backups").rglob("skill.md"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "local edit\n")

            ownership = installer.load_ownership()
            self.assertEqual(ownership["files"][str(target / "skill.md")]["component"], "codex-skills")

    def test_second_identical_install_is_noop(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "agent.toml").write_text("name = 'agent'\n", encoding="utf-8")

            installer = ManagedInstaller(state_dir=root / ".harness")
            first = installer.install_tree(source, target, component="codex-agents")
            second = installer.install_tree(source, target, component="codex-agents")

            self.assertEqual(first.installed, 1)
            self.assertEqual(second.installed, 0)
            self.assertEqual(second.backed_up, 0)


if __name__ == "__main__":
    unittest.main()
