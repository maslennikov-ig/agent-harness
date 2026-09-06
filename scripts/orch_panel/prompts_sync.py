"""Fragment sync/drift checker for orchestration prompt cards.

Repeated blocks in `prompts/*.md` are wrapped inline as
`<!-- fragment:<name> -->` ... `<!-- /fragment:<name> -->`. The canonical
text for each block lives in `prompts/fragments/<name>.md`. Prompt cards stay
self-contained (the full text is kept inline); this module verifies that every
wrapped copy still matches its canonical fragment and can re-expand drifted
copies from canon.

CLI:
    python3 scripts/orch_panel/prompts_sync.py --check   # exit 1 if drifted
    python3 scripts/orch_panel/prompts_sync.py --write   # re-expand from canon
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "prompts"
FRAGMENTS_DIR = PROMPTS_DIR / "fragments"

NAME = r"[a-z0-9][a-z0-9-]*"
BLOCK_RE = re.compile(
    r"<!-- fragment:(" + NAME + r") -->\n(.*?)\n<!-- /fragment:\1 -->",
    re.DOTALL,
)
OPEN_RE = re.compile(r"<!-- fragment:(" + NAME + r") -->")
CLOSE_RE = re.compile(r"<!-- /fragment:(" + NAME + r") -->")


def load_fragments(fragments_dir: Path = FRAGMENTS_DIR) -> dict[str, str]:
    """Return canonical fragment text keyed by name (trailing newline stripped)."""
    fragments: dict[str, str] = {}
    for path in sorted(fragments_dir.glob("*.md")):
        fragments[path.stem] = path.read_text(encoding="utf-8").rstrip("\n")
    return fragments


def prompt_files(prompts_dir: Path = PROMPTS_DIR) -> list[Path]:
    """Prompt cards that may carry fragment markers, including launchers."""
    launchers_dir = prompts_dir / "launchers"
    launchers = launchers_dir.rglob("*.md") if launchers_dir.is_dir() else ()
    return sorted([*prompts_dir.glob("*.md"), *launchers])


def check(prompts_dir: Path = PROMPTS_DIR, fragments_dir: Path = FRAGMENTS_DIR) -> list[str]:
    """Return human-readable problems for drifted, unknown, or malformed markers."""
    fragments = load_fragments(fragments_dir)
    problems: list[str] = []
    for path in prompt_files(prompts_dir):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(prompts_dir.parent)
        blocks = BLOCK_RE.findall(text)
        opens = OPEN_RE.findall(text)
        closes = CLOSE_RE.findall(text)
        if len(blocks) != len(opens) or len(blocks) != len(closes):
            problems.append(f"{rel}: malformed or mismatched fragment markers")
            continue
        for name, inner in blocks:
            if name not in fragments:
                problems.append(f"{rel}: unknown fragment '{name}' (no prompts/fragments/{name}.md)")
            elif inner != fragments[name]:
                problems.append(f"{rel}: fragment '{name}' drifted from canonical text")
    return problems


def _expand(text: str, fragments: dict[str, str]) -> tuple[str, bool]:
    changed = False

    def repl(match: "re.Match[str]") -> str:
        nonlocal changed
        name, inner = match.group(1), match.group(2)
        canonical = fragments.get(name)
        if canonical is None or canonical == inner:
            return match.group(0)
        changed = True
        return f"<!-- fragment:{name} -->\n{canonical}\n<!-- /fragment:{name} -->"

    return BLOCK_RE.sub(repl, text), changed


def write(prompts_dir: Path = PROMPTS_DIR, fragments_dir: Path = FRAGMENTS_DIR) -> list[Path]:
    """Re-expand every wrapped copy from canon. Return the files rewritten."""
    fragments = load_fragments(fragments_dir)
    rewritten: list[Path] = []
    for path in prompt_files(prompts_dir):
        text = path.read_text(encoding="utf-8")
        new_text, changed = _expand(text, fragments)
        if changed:
            path.write_text(new_text, encoding="utf-8")
            rewritten.append(path)
    return rewritten


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync inline prompt fragments with their canonical files.")
    parser.add_argument("--prompts-dir", type=Path, default=PROMPTS_DIR)
    parser.add_argument("--fragments-dir", type=Path, default=FRAGMENTS_DIR)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="report drifted/unknown fragments, exit 1 if any")
    group.add_argument("--write", action="store_true", help="re-expand wrapped copies from canonical files")
    args = parser.parse_args(argv)

    if args.check:
        problems = check(args.prompts_dir, args.fragments_dir)
        for problem in problems:
            print(problem)
        if problems:
            print(f"prompts-sync: {len(problems)} problem(s) found", file=sys.stderr)
            return 1
        print("prompts-sync: all fragments in sync")
        return 0

    rewritten = write(args.prompts_dir, args.fragments_dir)
    for path in rewritten:
        print(f"rewrote {path.relative_to(args.prompts_dir.parent)}")
    print(f"prompts-sync: re-expanded {len(rewritten)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
