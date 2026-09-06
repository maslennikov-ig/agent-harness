#!/usr/bin/env python3
"""Install the harness-owned Codex global guidance without erasing user text.

`overlay.manifest.json` used to declare `private/codex/global` as a `copy_tree`
onto `$CODEX_HOME`, which overwrites a user-owned `AGENTS.md` wholesale with no
backup and no way back. The Claude side already merges a marker-delimited block
and keeps the surrounding text; this is the Codex equivalent.

First install is deliberately not silent: when the target has no managed markers
and is not empty, the merge refuses unless `--adopt` is passed, because appending
the block next to pre-existing rules creates two competing rule sets.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path


BEGIN = "<!-- CODEX-GLOBAL:BEGIN -->"
END = "<!-- CODEX-GLOBAL:END -->"
BACKUP_SUFFIX = ".harness-backup"
LEGACY_TWO_GATE_RULE = re.compile(
    r"(?m)^- User interaction runs on two independent gates\..*"
    r"(?:\n  [^\n]*)*\n?"
)


class AdoptionRequired(RuntimeError):
    """The target holds unmanaged text that a blind append would duplicate."""


def merge(existing: str, managed: str, *, adopt: bool = False) -> str:
    managed = f"{BEGIN}\n{managed.strip()}\n{END}"
    if BEGIN in existing and END in existing:
        prefix, tail = existing.split(BEGIN, 1)
        _, suffix = tail.split(END, 1)
        return prefix.rstrip() + "\n\n" + managed + suffix.rstrip() + "\n"
    if not existing.strip():
        return managed + "\n"
    if not adopt:
        raise AdoptionRequired(
            "target has unmanaged content and no CODEX-GLOBAL markers; "
            "re-run with --adopt after reconciling the overlap by hand"
        )
    legacy = LEGACY_TWO_GATE_RULE.search(existing)
    if legacy:
        prefix = existing[: legacy.start()].rstrip()
        suffix = existing[legacy.end() :].strip()
        return "\n\n".join(
            part for part in (prefix, managed, suffix) if part
        ) + "\n"
    return existing.rstrip() + "\n\n" + managed + "\n"


def backup_path(target: Path) -> Path:
    return target.with_name(target.name + BACKUP_SUFFIX)


def write_atomic(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        Path(tmp_name).replace(target)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def install(source: Path, target: Path, *, adopt: bool = False) -> Path | None:
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    content = merge(existing, source.read_text(encoding="utf-8"), adopt=adopt)
    saved: Path | None = None
    if target.exists():
        saved = backup_path(target)
        shutil.copy2(target, saved)
    write_atomic(target, content)
    return saved


def rollback(target: Path) -> Path:
    saved = backup_path(target)
    if not saved.is_file():
        raise FileNotFoundError(f"no backup to roll back to: {saved}")
    shutil.copy2(saved, target)
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--adopt",
        action="store_true",
        help="allow the first install to append next to existing unmanaged text",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="restore the target from its harness backup and exit",
    )
    args = parser.parse_args(argv)

    if args.rollback:
        restored = rollback(args.target)
        print(f"install_codex_global: restored {args.target} from {restored}")
        return 0
    if args.source is None:
        parser.error("source is required unless --rollback is used")
    try:
        saved = install(args.source, args.target, adopt=args.adopt)
    except AdoptionRequired as error:
        print(f"install_codex_global: {error}", file=sys.stderr)
        return 2
    note = f" (backup: {saved})" if saved else ""
    print(f"install_codex_global: wrote managed block to {args.target}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
