import json
import tempfile
import unittest
from pathlib import Path

from harness_core.manifest import Manifest, ManifestError
from harness_core.lockfile import LockSnapshot


class ManifestLockTests(unittest.TestCase):
    def test_manifest_loads_components_and_expands_paths(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = root / "harness.manifest.json"
            manifest_path.write_text(json.dumps({
                "schema_version": 1,
                "components": [
                    {
                        "name": "console",
                        "type": "git",
                        "source": "https://example.invalid/console.git",
                        "target": "${HARNESS_HOME}/components/console",
                        "install": ["./scripts/install.sh"],
                        "doctor": [{"type": "command", "command": ["python3", "--version"]}],
                    }
                ],
            }), encoding="utf-8")

            manifest = Manifest.load(manifest_path, env={"HARNESS_HOME": str(root)})

            self.assertEqual(manifest.schema_version, 1)
            self.assertEqual(manifest.components[0].name, "console")
            self.assertEqual(manifest.components[0].target, root / "components" / "console")
            self.assertEqual(manifest.components[0].install, [["./scripts/install.sh"]])

    def test_manifest_expands_managed_block_paths_and_markers(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = root / "overlay.manifest.json"
            manifest_path.write_text(json.dumps({
                "schema_version": 1,
                "components": [
                    {
                        "name": "codex-global",
                        "type": "managed_block",
                        "source": "${HARNESS_REPO}/fragment.md",
                        "target": "${CODEX_HOME}/AGENTS.md",
                        "installer": "${HARNESS_REPO}/install.py",
                        "markers": ["<!-- BEGIN -->", "<!-- END -->"],
                    }
                ],
            }), encoding="utf-8")

            manifest = Manifest.load(
                manifest_path,
                env={"HARNESS_REPO": str(root), "CODEX_HOME": str(root / "codex")},
            )
            component = manifest.components[0]

            self.assertEqual(component.source, root / "fragment.md")
            self.assertEqual(component.target, root / "codex" / "AGENTS.md")
            self.assertEqual(component.installer, root / "install.py")
            self.assertEqual(component.markers, ("<!-- BEGIN -->", "<!-- END -->"))

    def test_manifest_rejects_unknown_component_type(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = Path(raw) / "manifest.json"
            manifest_path.write_text(json.dumps({
                "schema_version": 1,
                "components": [{"name": "mystery", "type": "silently-skipped"}],
            }), encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "unsupported component type"):
                Manifest.load(manifest_path)

    def test_lock_snapshot_records_installed_versions(self):
        snapshot = LockSnapshot.create([
            {
                "name": "console",
                "type": "git",
                "target": "/tmp/console",
                "version": "abc123",
                "status": "ok",
            },
            {
                "name": "bd",
                "type": "binary",
                "target": "bd",
                "version": "1.0.4",
                "status": "ok",
            },
        ])

        data = snapshot.to_dict()

        self.assertEqual(data["schema_version"], 1)
        self.assertEqual([item["name"] for item in data["components"]], ["console", "bd"])
        self.assertEqual(data["components"][0]["version"], "abc123")
        self.assertIn("created_at", data)


if __name__ == "__main__":
    unittest.main()
