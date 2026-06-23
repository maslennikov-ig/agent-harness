from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class InstallResult:
    installed: int = 0
    backed_up: int = 0
    skipped: int = 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ManagedInstaller:
    def __init__(self, state_dir: str | Path):
        self.state_dir = Path(state_dir)
        self.ownership_path = self.state_dir / "managed.json"
        self.backup_root = self.state_dir / "backups"

    def load_ownership(self) -> dict:
        if not self.ownership_path.exists():
            return {"schema_version": 1, "files": {}}
        return json.loads(self.ownership_path.read_text(encoding="utf-8"))

    def save_ownership(self, ownership: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.ownership_path.write_text(json.dumps(ownership, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def install_tree(self, source: str | Path, target: str | Path, component: str) -> InstallResult:
        source_path = Path(source)
        target_path = Path(target)
        ownership = self.load_ownership()
        files = ownership.setdefault("files", {})
        installed = 0
        backed_up = 0
        skipped = 0

        for src in sorted(path for path in source_path.rglob("*") if path.is_file()):
            relative = src.relative_to(source_path)
            dst = target_path / relative
            src_hash = _sha256(src)
            if dst.exists() and dst.is_file() and _sha256(dst) == src_hash:
                skipped += 1
                files[str(dst)] = {"component": component, "sha256": src_hash}
                continue
            if dst.exists() and dst.is_file():
                self._backup_file(dst, component)
                backed_up += 1
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            files[str(dst)] = {"component": component, "sha256": src_hash}
            installed += 1

        self.save_ownership(ownership)
        return InstallResult(installed=installed, backed_up=backed_up, skipped=skipped)

    def _backup_file(self, path: Path, component: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.backup_root / component / stamp / path.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        return backup
