from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import installer as subject  # noqa: E402


class ReleaseFixture:
    def __init__(self, root: Path) -> None:
        self.root = root

    def add(self, relative: str, content: str = "fixture\n", mode: int = 0o644) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        target.chmod(mode)

    def build(self) -> None:
        for relative in (
            "pyproject.toml",
            "uv.lock",
            "package.json",
            "package-lock.json",
            "scripts/start_console.sh",
            "scripts/node_mcp_env.sh",
        ):
            content = '{"packages":{"":{"engines":{"node":">=18"}}}}\n' if relative == "package-lock.json" else "fixture\n"
            self.add(relative, content, 0o755 if relative.startswith("scripts/") else 0o644)
        self.add(
            "harness/private/private/codex/global/AGENTS.md",
            f"{subject.CODEX_BEGIN}\nmanaged codex\n{subject.CODEX_END}\n",
        )
        self.add("policy/runtime-kernel-v1.md", "shared kernel\n")
        self.add(
            "claude-plugin/orchestration-bridge/templates/global/CLAUDE.md",
            f"{subject.ROUTING_BEGIN}\n@{{{{SHARED_AGENTS_PATH}}}}\n{subject.ROUTING_END}\n",
        )
        self.add("claude-plugin/orchestration-bridge/.claude-plugin/plugin.json", "{}\n")
        self.add("claude-plugin/orchestration-bridge/skills/stage/SKILL.md")
        self.add("claude-plugin/orchestration-bridge/agents/worker.md")
        self.add("harness/private/private/claude/skills/technical-premortem/SKILL.md")
        self.add("harness/core/assets/codex/skills/harness-bootstrap/SKILL.md")
        self.add("harness/core/templates/project/AGENTS.md", "project agents\n")
        self.add(
            "harness/core/templates/project/.codex/orchestrator.toml",
            '[project]\nbaseline = "agent-harness"\n',
        )
        self.add("bin/harness", "#!/bin/sh\n", 0o755)
        self.add("harness/distribution/vendor/superpowers/.claude-plugin/plugin.json", "{}\n")
        self.add("harness/distribution/vendor/superpowers/LICENSE", "MIT\n")
        self.add("harness/distribution/vendor/superpowers/skills/using-superpowers/SKILL.md")
        for name in subject.CODEX_SKILLS:
            self.add(f"harness/private/private/codex/skills/{name}/SKILL.md")
        for index in range(42):
            self.add(f"harness/private/private/codex/agents/agent-{index:02d}.toml")
        self.add("harness/private/private/codex/agents/QUALITY_PACK.md")
        self.refresh_manifest()

    def refresh_manifest(self) -> None:
        files = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.name == subject.MANIFEST_NAME:
                continue
            relative = path.relative_to(self.root).as_posix()
            if (
                any(part in {".venv", "node_modules", "__pycache__"} for part in path.relative_to(self.root).parts)
                or relative.startswith("web/dist/")
            ):
                continue
            files.append(
                {
                    "path": relative,
                    "sha256": subject._file_sha256(path),
                    "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
                }
            )
        (self.root / subject.MANIFEST_NAME).write_text(
            json.dumps({"schema_version": 1, "version": "0.1.0", "files": files}),
            encoding="utf-8",
        )


class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.release = base / "release"
        self.home = base / "home"
        self.release.mkdir()
        ReleaseFixture(self.release).build()
        self.homes = subject.resolve_homes(self.home, {})

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def installer(self) -> subject.Installer:
        return subject.Installer(self.release, self.homes, env={"PATH": os.environ.get("PATH", "")})

    def test_vite_node_engine_range_is_enforced(self) -> None:
        requirement = "^20.19.0 || >=22.12.0"
        self.assertFalse(subject._node_satisfies((20, 18, 9), requirement))
        self.assertTrue(subject._node_satisfies((20, 19, 0), requirement))
        self.assertFalse(subject._node_satisfies((21, 1, 0), requirement))
        self.assertTrue(subject._node_satisfies((22, 12, 0), requirement))

    def bootstrap(self, installer: subject.Installer | None = None) -> list[Path]:
        selected = installer or self.installer()

        def fake_build() -> None:
            for relative in (".venv/bin/python", "web/dist/index.html"):
                target = self.release / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("built\n", encoding="utf-8")
                if relative == ".venv/bin/python":
                    target.chmod(0o755)
            (self.release / "node_modules").mkdir(exist_ok=True)

        with mock.patch.object(subject, "check_prerequisites", return_value=[]), mock.patch.object(
            selected, "_build_console", side_effect=fake_build
        ):
            return selected.bootstrap()

    def test_prerequisite_failure_has_zero_user_writes(self) -> None:
        installer = self.installer()
        with mock.patch.object(subject, "check_prerequisites", return_value=["required command is missing: claude"]), mock.patch.object(
            installer, "_build_console"
        ) as build:
            with self.assertRaisesRegex(subject.InstallerError, "prerequisite"):
                installer.bootstrap()
        build.assert_not_called()
        self.assertFalse(self.home.exists())

    def test_foreign_same_name_skill_collision_has_zero_user_writes(self) -> None:
        collision = self.home / ".agents/skills/task-router"
        collision.mkdir(parents=True)
        sentinel = collision / "sentinel.txt"
        sentinel.write_text("foreign", encoding="utf-8")
        before = sentinel.read_bytes()
        installer = self.installer()
        with mock.patch.object(subject, "check_prerequisites", return_value=[]), mock.patch.object(
            installer, "_build_console"
        ) as build:
            with self.assertRaisesRegex(subject.InstallerError, "foreign same-name"):
                installer.bootstrap()
        build.assert_not_called()
        self.assertEqual(before, sentinel.read_bytes())
        self.assertFalse(installer.journal_path.exists())

    def test_same_release_is_idempotent(self) -> None:
        installer = self.installer()
        first = self.bootstrap(installer)
        journal = installer.journal_path.read_bytes()
        second = self.bootstrap(installer)
        self.assertTrue(first)
        self.assertEqual([], second)
        self.assertEqual(journal, installer.journal_path.read_bytes())
        codex = (self.home / ".codex/AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(1, codex.count(subject.CODEX_BEGIN))
        self.assertTrue((self.home / ".codex/agents/QUALITY_PACK.md").is_file())
        self.assertEqual(
            str(self.home / ".codex/superpowers/skills"),
            os.readlink(self.home / ".agents/skills/superpowers"),
        )

    def test_update_retires_removed_global_asset_and_preserves_project_files(self) -> None:
        installer = self.installer()
        self.bootstrap(installer)
        project = Path(self.temporary.name) / "kept-project"
        (project / ".git").mkdir(parents=True)
        with mock.patch.object(subject, "check_prerequisites", return_value=[]):
            installer.init_project(project)
        retired_source = self.release / "claude-plugin/orchestration-bridge/agents/worker.md"
        retired_target = self.home / ".agent-harness/plugins/orchestration-bridge/agents/worker.md"
        self.assertTrue(retired_target.is_file())
        retired_source.unlink()
        ReleaseFixture(self.release).refresh_manifest()
        updated = self.installer()
        self.bootstrap(updated)
        self.assertFalse(retired_target.exists())
        self.assertEqual("project agents\n", (project / "AGENTS.md").read_text(encoding="utf-8"))
        with mock.patch.object(subject, "check_prerequisites", return_value=[]):
            self.assertEqual([], updated.doctor())

    @unittest.skipUnless(hasattr(signal, "SIGKILL"), "requires POSIX process signals")
    def test_sigkill_mid_install_leaves_recoverable_transaction_journal(self) -> None:
        code = r'''
import os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import installer
release = Path(sys.argv[2])
home = Path(sys.argv[3])
instance = installer.Installer(release, installer.resolve_homes(home, {}), env={})
installer.check_prerequisites = lambda root: []
instance._build_console = lambda: None
original = instance._write_file
count = 0
def interrupted(path, data, mode):
    global count
    count += 1
    original(path, data, mode)
    if count == 2:
        os.kill(os.getpid(), signal.SIGKILL)
instance._write_file = interrupted
instance.bootstrap()
'''
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(Path(subject.__file__).resolve().parent),
                str(self.release),
                str(self.home),
            ],
            check=False,
        )
        self.assertEqual(-signal.SIGKILL, result.returncode)
        recovery = self.installer()
        journal = json.loads(recovery.journal_path.read_text(encoding="utf-8"))
        self.assertEqual("in_progress", journal["status"])
        recovery.rollback()
        self.assertFalse(recovery.journal_path.exists())
        self.assertEqual(
            [],
            [path for path in self.home.rglob("*") if path.is_file() or path.is_symlink()],
        )

    def test_managed_replacement_preserves_all_bytes_outside_markers(self) -> None:
        shared = self.home / ".agents/AGENTS.md"
        shared.parent.mkdir(parents=True)
        prefix = b"user prefix  \r\n\r\n"
        suffix = b"\r\n\r\n  user suffix\r\n"
        shared.write_bytes(
            prefix
            + subject.KERNEL_BEGIN.encode()
            + b"\r\nold\r\n"
            + subject.KERNEL_END.encode()
            + suffix
        )
        installer = self.installer()
        self.bootstrap(installer)
        installed = shared.read_bytes()
        self.assertTrue(installed.startswith(prefix))
        self.assertTrue(installed.endswith(suffix))
        self.assertIn(b"shared kernel", installed)

    def test_portable_install_does_not_remove_old_unmanaged_user_text(self) -> None:
        old_rule = (
            "- The medium tier keeps one owner and no mandatory intermediate "
            "verification or review. Final task acceptance runs once through closeout; "
            "for the complex tier, direct local execution requires a named reason: "
            "simple/local, orchestrator-only coordination, concrete conflict, no useful "
            "split, or unavailable visible subagents.\n"
        )
        shared = self.home / ".agents/AGENTS.md"
        shared.parent.mkdir(parents=True)
        shared.write_text(old_rule, encoding="utf-8")
        self.bootstrap(self.installer())
        self.assertTrue(shared.read_text(encoding="utf-8").startswith(old_rule))

    def test_bootstrap_rechecks_conflicts_after_build(self) -> None:
        installer = self.installer()
        collision = self.home / ".agents/skills/task-router"

        def concurrent_change() -> None:
            collision.mkdir(parents=True)
            (collision / "user.txt").write_text("arrived during build", encoding="utf-8")

        with mock.patch.object(subject, "check_prerequisites", return_value=[]), mock.patch.object(
            installer, "_build_console", side_effect=concurrent_change
        ):
            with self.assertRaisesRegex(subject.InstallerError, "foreign same-name"):
                installer.bootstrap()
        self.assertEqual(
            "arrived during build",
            (collision / "user.txt").read_text(encoding="utf-8"),
        )
        self.assertFalse(installer.journal_path.exists())
        self.assertFalse((self.home / ".codex/AGENTS.md").exists())

    def test_partial_failure_automatically_restores_all_paths(self) -> None:
        class FailOnceInstaller(subject.Installer):
            writes = 0
            failed = False

            def _write_file(self, path: Path, data: bytes, mode: int) -> None:
                self.writes += 1
                if self.writes == 5 and not self.failed:
                    self.failed = True
                    raise OSError("injected write failure")
                super()._write_file(path, data, mode)

        installer = FailOnceInstaller(self.release, self.homes, env={})
        with mock.patch.object(subject, "check_prerequisites", return_value=[]), mock.patch.object(
            installer, "_build_console"
        ):
            with self.assertRaisesRegex(OSError, "injected"):
                installer.bootstrap()
        self.assertEqual([], [path for path in self.home.rglob("*") if path.is_file() or path.is_symlink()])
        self.assertFalse(installer.journal_path.exists())

    def test_explicit_rollback_restores_managed_file_and_keeps_user_sentinel(self) -> None:
        shared = self.home / ".agents/AGENTS.md"
        shared.parent.mkdir(parents=True)
        shared.write_text("user rule\n", encoding="utf-8")
        installer = self.installer()
        self.bootstrap(installer)
        sentinel = self.home / ".agents/skills/user-sentinel.txt"
        sentinel.write_text("keep me", encoding="utf-8")
        restored = installer.rollback()
        self.assertIn(shared, restored)
        self.assertEqual("user rule\n", shared.read_text(encoding="utf-8"))
        self.assertEqual("keep me", sentinel.read_text(encoding="utf-8"))
        self.assertFalse(installer.journal_path.exists())

    def test_project_conflict_is_reported_before_any_project_write(self) -> None:
        installer = self.installer()
        self.bootstrap(installer)
        project = Path(self.temporary.name) / "project"
        (project / ".git").mkdir(parents=True)
        agents = project / "AGENTS.md"
        agents.write_text("project-owned rules\n", encoding="utf-8")
        with mock.patch.object(subject, "check_prerequisites", return_value=[]):
            with self.assertRaisesRegex(subject.InstallerError, "merge the harness baseline"):
                installer.init_project(project)
        self.assertEqual("project-owned rules\n", agents.read_text(encoding="utf-8"))
        self.assertFalse((project / "CLAUDE.md").exists())
        self.assertFalse((project / ".codex/orchestrator.toml").exists())

    def test_doctor_detects_release_artifact_tampering(self) -> None:
        installer = self.installer()
        self.bootstrap(installer)
        (self.release / "policy/runtime-kernel-v1.md").write_text("tampered\n", encoding="utf-8")
        failures = installer.doctor()
        self.assertTrue(any("SHA-256 mismatch" in failure for failure in failures))

    def test_doctor_detects_unlisted_release_file(self) -> None:
        installer = self.installer()
        self.bootstrap(installer)
        (self.release / ".npmrc").write_text("unexpected=true\n", encoding="utf-8")
        failures = installer.doctor()
        self.assertTrue(any("unlisted file in release: .npmrc" in failure for failure in failures))

    def test_public_git_clone_metadata_is_local_only(self) -> None:
        manifest = subject.load_manifest(self.release)
        subprocess.run(["git", "init", str(self.release)], check=True, capture_output=True)
        subject.verify_release(self.release, manifest)
        nested = self.release / "harness" / ".git"
        nested.mkdir()
        with self.assertRaisesRegex(subject.InstallerError, "nested Git metadata"):
            subject.verify_release(self.release, manifest)
        nested.rmdir()
        metadata = self.release / ".git"
        outside = self.release.parent / "git-metadata"
        metadata.rename(outside)
        metadata.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(subject.InstallerError, "unlisted symlink"):
            subject.verify_release(self.release, manifest)

    def test_generated_release_root_symlinks_are_rejected(self) -> None:
        outside = Path(self.temporary.name) / "outside-generated"
        outside.mkdir()
        manifest = subject.load_manifest(self.release)
        for relative in (".venv", "node_modules", "state", "web/dist"):
            with self.subTest(relative=relative):
                candidate = self.release / relative
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(subject.InstallerError, "unlisted symlink"):
                    subject.verify_release(self.release, manifest)
                candidate.unlink()

    def test_extra_file_in_owned_plugin_blocks_doctor_and_update(self) -> None:
        installer = self.installer()
        self.bootstrap(installer)
        extra = self.home / ".agent-harness/plugins/superpowers/hooks/hooks.json"
        extra.parent.mkdir(parents=True)
        extra.write_text('{"hooks": []}\n', encoding="utf-8")
        with mock.patch.object(subject, "check_prerequisites", return_value=[]):
            failures = installer.doctor()
            with self.assertRaisesRegex(subject.InstallerError, "undeclared file or directory"):
                installer.bootstrap(update=True)
        with mock.patch.object(subject.shutil, "which", return_value="/usr/bin/claude"), mock.patch.object(
            subject.os, "execvpe"
        ) as execute:
            with self.assertRaisesRegex(subject.InstallerError, "undeclared file or directory"):
                installer.launch_claude([])
        execute.assert_not_called()
        self.assertTrue(any("undeclared file or directory" in failure for failure in failures))
        self.assertEqual('{"hooks": []}\n', extra.read_text(encoding="utf-8"))

    def test_doctor_detects_missing_console_build_outputs_without_rebuilding(self) -> None:
        installer = self.installer()
        self.bootstrap(installer)
        (self.release / "web/dist/index.html").unlink()
        with mock.patch.object(subject, "check_prerequisites", return_value=[]), mock.patch.object(
            installer, "_build_console"
        ) as build:
            failures = installer.doctor()
        build.assert_not_called()
        self.assertTrue(any("built frontend is missing" in failure for failure in failures))

    def test_doctor_rejects_truncated_and_project_only_journals(self) -> None:
        installer = self.installer()
        self.bootstrap(installer)
        journal = json.loads(installer.journal_path.read_text(encoding="utf-8"))
        journal["entries"] = []
        journal["declared_paths"] = []
        installer.journal_path.write_text(json.dumps(journal), encoding="utf-8")
        with mock.patch.object(subject, "check_prerequisites", return_value=[]):
            failures = installer.doctor()
        self.assertTrue(any("does not declare required paths" in failure for failure in failures))

        other_home = Path(self.temporary.name) / "project-only-home"
        project_installer = subject.Installer(
            self.release, subject.resolve_homes(other_home, {}), env={}
        )
        project = Path(self.temporary.name) / "project-only"
        (project / ".git").mkdir(parents=True)
        with mock.patch.object(subject, "check_prerequisites", return_value=[]):
            project_installer.init_project(project)
            failures = project_installer.doctor()
        self.assertTrue(any("does not declare required paths" in failure for failure in failures))
        self.assertTrue(any("required installed path is missing" in failure for failure in failures))

    def test_home_override_rejects_symlink_escape(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        self.home.mkdir()
        (self.home / ".agents").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(subject.InstallerError, "escapes the selected home"):
            subject.resolve_homes(self.home, {})

    def test_harness_claude_forwards_both_pinned_plugins(self) -> None:
        installer = self.installer()
        self.bootstrap(installer)
        with mock.patch.object(subject.shutil, "which", return_value="/usr/bin/claude"), mock.patch.object(
            subject.os, "execvpe", side_effect=RuntimeError("exec intercepted")
        ) as execute:
            with self.assertRaisesRegex(RuntimeError, "intercepted"):
                installer.launch_claude(["--", "--print", "hello"])
        arguments = execute.call_args.args[1]
        self.assertEqual("/usr/bin/claude", arguments[0])
        self.assertEqual(2, arguments.count("--plugin-dir"))
        self.assertIn(str(self.home / ".agent-harness/plugins/orchestration-bridge"), arguments)
        self.assertIn(str(self.home / ".agent-harness/plugins/superpowers"), arguments)
        self.assertEqual(["--print", "hello"], arguments[-2:])

    def test_modified_installed_file_blocks_rollback_without_writes(self) -> None:
        installer = self.installer()
        self.bootstrap(installer)
        target = self.home / ".agents/AGENTS.md"
        target.write_text(target.read_text(encoding="utf-8") + "later user edit\n", encoding="utf-8")
        with self.assertRaisesRegex(subject.InstallerError, "modified after installation"):
            installer.rollback()
        self.assertIn("later user edit", target.read_text(encoding="utf-8"))
        self.assertTrue(installer.journal_path.exists())

    def test_rollback_rejects_untrusted_schema_and_backup_path_before_writes(self) -> None:
        shared = self.home / ".agents/AGENTS.md"
        shared.parent.mkdir(parents=True)
        shared.write_text("user rule\n", encoding="utf-8")
        installer = self.installer()
        self.bootstrap(installer)
        installed = shared.read_bytes()
        journal = json.loads(installer.journal_path.read_text(encoding="utf-8"))
        shared_entry = next(item for item in journal["entries"] if item["path"] == str(shared))
        outside = Path(self.temporary.name) / "outside-backup"
        outside.write_text("user rule\n", encoding="utf-8")
        shared_entry["before"]["backup"] = str(outside)
        installer.journal_path.write_text(json.dumps(journal), encoding="utf-8")
        with self.assertRaisesRegex(subject.InstallerError, "backup escapes state/backups"):
            installer.rollback()
        self.assertEqual(installed, shared.read_bytes())
        self.assertEqual("user rule\n", outside.read_text(encoding="utf-8"))

    def test_partial_explicit_rollback_keeps_recoverable_journal(self) -> None:
        shared = self.home / ".agents/AGENTS.md"
        shared.parent.mkdir(parents=True)
        shared.write_text("user rule\n", encoding="utf-8")
        installer = self.installer()
        self.bootstrap(installer)
        original_write = installer._write_file
        failed = False

        def fail_once(path: Path, data: bytes, mode: int) -> None:
            nonlocal failed
            if path == shared and not failed:
                failed = True
                raise OSError("injected rollback failure")
            original_write(path, data, mode)

        with mock.patch.object(installer, "_write_file", side_effect=fail_once):
            with self.assertRaisesRegex(subject.InstallerError, "recoverable journal was retained"):
                installer.rollback()
        self.assertTrue(installer.journal_path.exists())
        journal = json.loads(installer.journal_path.read_text(encoding="utf-8"))
        self.assertEqual("rollback_in_progress", journal["status"])
        installer.rollback()
        self.assertEqual("user rule\n", shared.read_text(encoding="utf-8"))
        self.assertFalse(installer.journal_path.exists())

    @unittest.skipUnless(hasattr(signal, "SIGKILL"), "requires POSIX process signals")
    def test_sigkill_mid_explicit_rollback_can_resume(self) -> None:
        shared = self.home / ".agents/AGENTS.md"
        shared.parent.mkdir(parents=True)
        shared.write_text("user rule\n", encoding="utf-8")
        installer = self.installer()
        self.bootstrap(installer)
        sentinel = self.home / ".agents/skills/user-sentinel.txt"
        sentinel.write_text("keep me", encoding="utf-8")
        code = r'''
import os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import installer
instance = installer.Installer(
    Path(sys.argv[2]), installer.resolve_homes(Path(sys.argv[3]), {}), env={}
)
original = instance._write_file
count = 0
def interrupted(path, data, mode):
    global count
    count += 1
    original(path, data, mode)
    if count == 2:
        os.kill(os.getpid(), signal.SIGKILL)
instance._write_file = interrupted
instance.rollback()
'''
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(Path(subject.__file__).resolve().parent),
                str(self.release),
                str(self.home),
            ],
            check=False,
        )
        self.assertEqual(-signal.SIGKILL, result.returncode)
        journal = json.loads(installer.journal_path.read_text(encoding="utf-8"))
        self.assertEqual("rollback_in_progress", journal["status"])
        with mock.patch.object(subject, "check_prerequisites", return_value=[]):
            self.assertTrue(any("unfinished" in failure for failure in installer.doctor()))
        installer.rollback()
        self.assertEqual("user rule\n", shared.read_text(encoding="utf-8"))
        self.assertEqual("keep me", sentinel.read_text(encoding="utf-8"))
        self.assertFalse(installer.journal_path.exists())


if __name__ == "__main__":
    unittest.main()
