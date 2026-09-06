#!/usr/bin/env python3
"""Measure stable before/after token-efficiency proxies without live model calls."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys


SETUP_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = SETUP_ROOT.parents[5]
REL_SETUP = SETUP_ROOT.relative_to(REPO_ROOT).as_posix()
REL_ORCHESTRATOR = (
    SETUP_ROOT.parent / "orchestrator-stage"
).relative_to(REPO_ROOT).as_posix()


def from_ref(ref: str, relative: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or f"cannot read {relative} at {ref}")
    return result.stdout


def section(text: str, start: str, end: str) -> str:
    try:
        return text.split(start, 1)[1].split(end, 1)[0].strip()
    except IndexError as exc:
        raise SystemExit(f"measurement anchors missing: {start!r} / {end!r}") from exc


def size(text: str) -> int:
    return len(text.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="af281b1")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    skill_rel = f"{REL_SETUP}/SKILL.md"
    spawn_rel = f"{REL_SETUP}/templates/subagent-spawn-template.md"
    delegation_rel = f"{REL_ORCHESTRATOR}/references/delegation-and-isolation.md"
    before_skill = from_ref(args.base_ref, skill_rel)
    before_spawn = from_ref(args.base_ref, spawn_rel)
    before_delegation = from_ref(args.base_ref, delegation_rel)
    after_block = (SETUP_ROOT / "templates/project-agents-managed-block.md").read_text(
        encoding="utf-8"
    ).strip()
    after_spawn = (SETUP_ROOT / "templates/subagent-spawn-template.md").read_text(
        encoding="utf-8"
    )
    after_delegation = (
        SETUP_ROOT.parent / "orchestrator-stage/references/delegation-and-isolation.md"
    ).read_text(encoding="utf-8")
    before_agents_proxy = section(
        before_skill,
        "New or reconciled repos should carry only a compact local reminder:",
        "`.codex/orchestrator.toml` should stay thin and machine-readable:",
    )
    before_none = before_delegation.count('fork_turns="none"') + before_spawn.count(
        'fork_turns="none"'
    )
    after_none = after_delegation.count('fork_turns="none"') + after_spawn.count(
        'fork_turns="none"'
    )
    result = {
        "base_ref": args.base_ref,
        "proxies": {
            "managed_agents_bytes": {
                "before": size(before_agents_proxy),
                "after": size(after_block),
                "delta": size(after_block) - size(before_agents_proxy),
                "basis": "previous setup reminder versus canonical managed project block",
            },
            "spawn_prompt_bytes": {
                "before": size(before_spawn),
                "after": size(after_spawn),
                "delta": size(after_spawn) - size(before_spawn),
                "basis": "canonical same-session spawn template",
            },
            "inherited_context_default": {
                "before": "implicit_all" if before_none == 0 else "explicit_none",
                "after": "explicit_none" if after_none else "implicit_all",
                "before_explicit_none_occurrences": before_none,
                "after_explicit_none_occurrences": after_none,
                "basis": "selected spawn/delegation sources; zero transcript bytes assumed only for explicit none",
            },
        },
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for name, metric in result["proxies"].items():
            print(f"{name}: {metric}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
