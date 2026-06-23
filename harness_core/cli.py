from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .export_local import ExportLocalError, export_local
from .lockfile import LockSnapshot
from .managed import ManagedInstaller
from .manifest import Component, Manifest
from .secrets import SecretVault, SecretVaultError


DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "harness.manifest.json"
DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "project"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness", description="Portable agent harness bootstrap/update/doctor CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_manifest_flags(subparsers.add_parser("plan", help="Show planned component actions."))
    bootstrap = add_manifest_flags(subparsers.add_parser("bootstrap", help="Install or update managed harness components."))
    bootstrap.add_argument("--profile", default="full", choices=["full"], help="Install profile.")
    bootstrap.add_argument("--lock", default=None, help="Path for lock snapshot.")
    bootstrap.add_argument("--yes", action="store_true", help="Run without interactive confirmation.")
    bootstrap.add_argument("--private", default=None, help="Private overlay repo URL/path.")
    add_manifest_flags(subparsers.add_parser("doctor", help="Check installed component health."))
    update = add_manifest_flags(subparsers.add_parser("update", help="Alias for bootstrap with latest sources."))
    update.add_argument("--profile", default="full", choices=["full"])
    update.add_argument("--lock", default=None)
    update.add_argument("--yes", action="store_true")
    update.add_argument("--private", default=None)
    rollback = subparsers.add_parser("rollback", help="Print rollback guidance for a lock snapshot.")
    rollback.add_argument("--lock", required=True)
    init_project = subparsers.add_parser("init-project", help="Install project-local baseline templates.")
    init_project.add_argument("repo_path")
    init_project.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    init_project.add_argument("--yes", action="store_true")
    export = subparsers.add_parser("export-local", help="Export selected local harness assets into a repo.")
    export.add_argument("--scope", choices=["private", "public"], default="private")
    export.add_argument("--target", required=True)
    export.add_argument("--yes", action="store_true")
    export.add_argument("--json", action="store_true")
    secrets = subparsers.add_parser("secrets", help="Manage encrypted private overlay secrets.")
    secrets_sub = secrets.add_subparsers(dest="secrets_command", required=True)
    secrets_init = secrets_sub.add_parser("init")
    secrets_init.add_argument("--file", default="secrets.enc.json")
    secrets_init.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    secrets_edit = secrets_sub.add_parser("edit")
    secrets_edit.add_argument("--file", default="secrets.enc.json")
    secrets_check = secrets_sub.add_parser("check")
    secrets_check.add_argument("--file", default="secrets.enc.json")

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            return command_plan(args)
        if args.command in {"bootstrap", "update"}:
            return command_bootstrap(args)
        if args.command == "doctor":
            return command_doctor(args)
        if args.command == "rollback":
            return command_rollback(args)
        if args.command == "init-project":
            return command_init_project(args)
        if args.command == "export-local":
            return command_export_local(args)
        if args.command == "secrets":
            return command_secrets(args)
    except (OSError, ValueError, SecretVaultError, ExportLocalError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 1


def add_manifest_flags(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--harness-home", default=None)
    return parser


def load_manifest(args: argparse.Namespace) -> Manifest:
    harness_home = args.harness_home or os.environ.get("HARNESS_HOME") or str(Path.home() / ".agent-harness")
    manifest_path = Path(args.manifest)
    return Manifest.load(args.manifest, env={
        "HARNESS_HOME": harness_home,
        "HARNESS_REPO": str(manifest_path.resolve().parent),
        "CODEX_HOME": os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
        "AGENTS_HOME": os.environ.get("AGENTS_HOME", str(Path.home() / ".agents")),
        "CLAUDE_HOME": os.environ.get("CLAUDE_HOME", os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))),
    })


def state_dir() -> Path:
    return Path(os.environ.get("HARNESS_STATE_DIR", str(Path.home() / ".agent-harness" / "state")))


def component_action(component: Component) -> str:
    if component.type == "copy_tree":
        return "update" if isinstance(component.target, Path) and component.target.exists() else "install"
    if component.type == "git":
        return "update" if isinstance(component.target, Path) and (component.target / ".git").exists() else "install"
    if component.type == "binary":
        return "check" if shutil.which(str(component.target or component.name)) else "install"
    return "check"


def command_plan(args: argparse.Namespace) -> int:
    manifest = load_manifest(args)
    data = {
        "schema_version": 1,
        "components": [
            {
                "name": component.name,
                "type": component.type,
                "target": str(component.target or ""),
                "action": component_action(component),
            }
            for component in manifest.components
        ],
    }
    output(data, args.json)
    return 0


def command_bootstrap(args: argparse.Namespace) -> int:
    manifest = load_manifest(args)
    records = []
    installer = ManagedInstaller(state_dir() / "managed")
    manifests = [manifest]
    decrypted_secrets: Path | None = None
    if getattr(args, "private", None):
        overlay_root = resolve_private_overlay(args.private)
        decrypted_secrets = apply_private_secrets(overlay_root)
        private_manifest = private_overlay_manifest_from_root(overlay_root)
        if private_manifest:
            manifests.append(private_manifest)
    try:
        for active_manifest in manifests:
            for component in active_manifest.components:
                record = install_component(component, installer)
                records.append(record)
        statuses = []
        for active_manifest in manifests:
            statuses.extend(doctor_records(active_manifest))
        status_by_name = {item["name"]: item["status"] for item in statuses}
        for record in records:
            record["status"] = status_by_name.get(record["name"], "unknown")
        lock_path = Path(args.lock) if args.lock else state_dir() / "locks" / "latest-lock.json"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        LockSnapshot.create(records).write(lock_path)
        print(f"Wrote lock snapshot: {lock_path}")
        return 0 if all(record["status"] == "ok" for record in records) else 2
    finally:
        if decrypted_secrets and decrypted_secrets.exists():
            decrypted_secrets.unlink()


def private_overlay_manifest_from_root(overlay_root: Path) -> Manifest | None:
    manifest_path = overlay_root / "overlay.manifest.json"
    if not manifest_path.exists():
        print(f"warning: private overlay manifest not found: {manifest_path}", file=sys.stderr)
        return None
    return Manifest.load(manifest_path, env={
        "HARNESS_REPO": str(overlay_root),
        "HARNESS_HOME": os.environ.get("HARNESS_HOME", str(Path.home() / ".agent-harness")),
        "CODEX_HOME": os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
        "AGENTS_HOME": os.environ.get("AGENTS_HOME", str(Path.home() / ".agents")),
        "CLAUDE_HOME": os.environ.get("CLAUDE_HOME", os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))),
    })


def resolve_private_overlay(source: str) -> Path:
    source_path = Path(source).expanduser()
    if source_path.exists():
        return source_path.resolve()
    target = state_dir() / "private-overlay"
    if (target / ".git").exists():
        subprocess.run(["git", "-C", str(target), "pull", "--ff-only"], check=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", source, str(target)], check=True)
    return target


def apply_private_secrets(overlay_root: Path) -> Path | None:
    secrets_path = overlay_root / "secrets.enc.json"
    if not secrets_path.exists():
        return None
    passphrase = prompt_passphrase(confirm=False)
    payload = SecretVault().read_encrypted(secrets_path, passphrase)
    for key, value in payload.items():
        os.environ[str(key)] = str(value)
    handle = tempfile.NamedTemporaryFile("w", prefix="harness-secrets-", suffix=".json", delete=False)
    temp_path = Path(handle.name)
    try:
        json.dump(payload, handle)
        handle.write("\n")
    finally:
        handle.close()
    try:
        temp_path.chmod(0o600)
    except OSError:
        pass
    os.environ["HARNESS_SECRETS_FILE"] = str(temp_path)
    return temp_path


def install_component(component: Component, installer: ManagedInstaller) -> dict[str, Any]:
    if component.type == "copy_tree":
        if not isinstance(component.source, Path) or not isinstance(component.target, Path):
            raise ValueError(f"{component.name}: copy_tree requires source and target")
        result = installer.install_tree(component.source, component.target, component.name)
        return {
            "name": component.name,
            "type": component.type,
            "target": str(component.target),
            "version": tree_version(component.source),
            "installed": result.installed,
            "backed_up": result.backed_up,
        }
    if component.type == "git":
        if not isinstance(component.target, Path) or not component.source:
            raise ValueError(f"{component.name}: git requires source and target")
        update_git_repo(str(component.source), component.target)
        run_commands(component.install, cwd=component.target)
        return {
            "name": component.name,
            "type": component.type,
            "target": str(component.target),
            "version": git_revision(component.target),
        }
    if component.type == "binary":
        return {
            "name": component.name,
            "type": component.type,
            "target": str(component.target or component.name),
            "version": command_version(str(component.target or component.name)),
        }
    return {"name": component.name, "type": component.type, "target": str(component.target or ""), "version": ""}


def update_git_repo(source: str, target: Path) -> None:
    if (target / ".git").exists():
        subprocess.run(["git", "-C", str(target), "pull", "--ff-only"], check=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", source, str(target)], check=True)


def run_commands(commands: list[list[str]], cwd: Path) -> None:
    for command in commands:
        subprocess.run(command, cwd=str(cwd), check=True)


def command_doctor(args: argparse.Namespace) -> int:
    manifest = load_manifest(args)
    records = doctor_records(manifest)
    output({"schema_version": 1, "components": records}, args.json)
    return 0 if all(record["status"] == "ok" for record in records) else 2


def doctor_records(manifest: Manifest) -> list[dict[str, Any]]:
    return [doctor_component(component) for component in manifest.components]


def doctor_component(component: Component) -> dict[str, Any]:
    checks = component.doctor or []
    failures = []
    for check in checks:
        check_type = check.get("type")
        if check_type == "path_exists" and not Path(str(check.get("path"))).exists():
            failures.append(f"missing path {check.get('path')}")
        elif check_type == "command":
            command = check.get("command") or []
            try:
                subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            except (OSError, subprocess.CalledProcessError) as error:
                failures.append(f"command failed {command}: {error}")
    if not checks:
        if component.type == "copy_tree" and isinstance(component.target, Path) and not component.target.exists():
            failures.append(f"missing target {component.target}")
        if component.type == "git" and isinstance(component.target, Path) and not (component.target / ".git").exists():
            failures.append(f"missing git repo {component.target}")
        if component.type == "binary" and not shutil.which(str(component.target or component.name)):
            failures.append(f"missing binary {component.target or component.name}")
    return {
        "name": component.name,
        "type": component.type,
        "target": str(component.target or ""),
        "status": "warn" if failures else "ok",
        "details": failures,
        "version": component_version(component),
    }


def command_rollback(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.lock).read_text(encoding="utf-8"))
    print("Rollback is manual for v1. Reinstall these locked component versions:")
    for component in data.get("components", []):
        print(f"- {component.get('name')}: {component.get('version')} at {component.get('target')}")
    return 0


def command_init_project(args: argparse.Namespace) -> int:
    repo = Path(args.repo_path)
    template = Path(args.template)
    if not template.exists():
        raise ValueError(f"template not found: {template}")
    installer = ManagedInstaller(repo / ".harness")
    installer.install_tree(template, repo, "project-baseline")
    print(f"Initialized project baseline: {repo}")
    return 0


def command_export_local(args: argparse.Namespace) -> int:
    result = export_local(scope=args.scope, target=args.target, yes=args.yes)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        skipped = ", ".join(result.skipped_sources) if result.skipped_sources else "none"
        print(f"Exported {result.copied} files to {result.target}")
        print(f"Skipped missing sources: {skipped}")
    return 0


def command_secrets(args: argparse.Namespace) -> int:
    vault = SecretVault()
    path = Path(args.file)
    if args.secrets_command == "init":
        payload = parse_key_values(args.set)
        passphrase = prompt_passphrase(confirm=True)
        vault.write_encrypted(path, payload, passphrase)
        print(f"Wrote encrypted secrets: {path}")
        return 0
    if args.secrets_command == "check":
        passphrase = prompt_passphrase(confirm=False)
        vault.read_encrypted(path, passphrase)
        print("Encrypted secrets OK")
        return 0
    if args.secrets_command == "edit":
        passphrase = prompt_passphrase(confirm=False)
        payload = vault.read_encrypted(path, passphrase) if path.exists() else {}
        print(json.dumps(payload, indent=2, sort_keys=True))
        print("Edit mode prints decrypted JSON in v1; redirect to a secure editor workflow before storing production secrets.", file=sys.stderr)
        return 0
    return 1


def parse_key_values(values: list[str]) -> dict[str, str]:
    result = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"expected KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        result[key] = value
    return result


def prompt_passphrase(confirm: bool) -> str:
    first = getpass.getpass("Harness secrets passphrase: ")
    if confirm:
        second = getpass.getpass("Repeat passphrase: ")
        if first != second:
            raise ValueError("passphrases do not match")
    if not first:
        raise ValueError("empty passphrase is not allowed")
    return first


def output(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    for component in data.get("components", []):
        status = component.get("status") or component.get("action")
        print(f"{component.get('name')}: {status} -> {component.get('target')}")


def tree_version(path: Path) -> str:
    if (path / ".git").exists():
        return git_revision(path)
    return "local"


def git_revision(path: Path) -> str:
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def command_version(command: str) -> str:
    binary = shutil.which(command)
    if not binary:
        return "missing"
    result = subprocess.run([binary, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    return (result.stdout or result.stderr).splitlines()[0] if (result.stdout or result.stderr) else "installed"


def component_version(component: Component) -> str:
    if component.type == "git" and isinstance(component.target, Path) and component.target.exists():
        return git_revision(component.target)
    if component.type == "copy_tree" and isinstance(component.source, Path):
        return tree_version(component.source)
    if component.type == "binary":
        return command_version(str(component.target or component.name))
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
