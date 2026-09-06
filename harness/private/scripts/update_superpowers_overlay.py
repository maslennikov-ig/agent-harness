#!/usr/bin/env python3
"""Update Superpowers while preserving the local bounded-TDD contract."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "private/superpowers/bounded-tdd.patch"
def default_repo() -> Path:
    """Where the Superpowers checkout actually is on this machine.

    `SUPERPOWERS_ROOT` wins. A git checkout is preferred next, because the tests
    that reapply the overlay patch need the upstream history: the marketplace
    plugin under `$CLAUDE_HOME` has the files but no `.git`, so pointing at it
    turned three tests into permanent skips. The plugin is still the fallback
    for the checks that only read content, and the historical
    `$CODEX_HOME/superpowers` is tried last.
    """
    explicit = os.environ.get("SUPERPOWERS_ROOT")
    if explicit:
        return Path(explicit)
    workspace = Path(os.environ.get("CODEX_WORKSPACE", Path.home() / "code"))
    for candidate in (workspace / "superpowers", Path.home() / "code" / "superpowers"):
        if (candidate / ".git").exists():
            return candidate
    claude_home = Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude"))
    plugin = claude_home / "skills" / "superpowers"
    if (plugin / "skills").is_dir():
        return plugin
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "superpowers"


DEFAULT_REPO = default_repo()
DEFAULT_CLAUDE_HOME = Path(
    os.environ.get("CLAUDE_HOME", Path.home() / ".claude")
)
CLAUDE_PLUGIN_KEY = "superpowers@skills-dir"
CLAUDE_OFFICIAL_PLUGIN_KEY = "superpowers@claude-plugins-official"
CLAUDE_INSTALLED_PLUGINS = "plugins/installed_plugins.json"

TARGETS = (
    "skills/brainstorming/SKILL.md",
    "skills/dispatching-parallel-agents/SKILL.md",
    "skills/executing-plans/SKILL.md",
    "skills/finishing-a-development-branch/SKILL.md",
    "skills/requesting-code-review/SKILL.md",
    "skills/subagent-driven-development/SKILL.md",
    "skills/systematic-debugging/SKILL.md",
    "skills/test-driven-development/SKILL.md",
    "skills/using-git-worktrees/SKILL.md",
    "skills/using-superpowers/SKILL.md",
    "skills/using-superpowers/references/codex-tools.md",
    "skills/verification-before-completion/SKILL.md",
    "skills/subagent-driven-development/implementer-prompt.md",
    "skills/subagent-driven-development/re-review-prompt.md",
    "skills/subagent-driven-development/task-reviewer-prompt.md",
    "skills/writing-plans/SKILL.md",
    "skills/writing-skills/SKILL.md",
    "skills/writing-skills/testing-skills-with-subagents.md",
    "tests/policy/test-bounded-tdd-workflow.sh",
)

REQUIRED = {
    "skills/test-driven-development/SKILL.md": (
        "The focused red-green loop is a development instrument.",
        "does not trigger an affected package, broad suite, reviewer, or closeout",
    ),
    "skills/verification-before-completion/SKILL.md": (
        "Matching passing evidence may be reused",
        "risk-selected final acceptance",
    ),
    "skills/systematic-debugging/SKILL.md": (
        "Use a focused diagnostic when it unblocks implementation.",
    ),
    "skills/subagent-driven-development/implementer-prompt.md": (
        "Final acceptance is root-owned unless this task is the assigned final verification stream.",
    ),
    "skills/writing-plans/SKILL.md": ("one cohesive acceptance boundary",),
    "skills/writing-skills/SKILL.md": (
        "Do not require authenticated model calls when a deterministic contract test",
    ),
    "skills/brainstorming/SKILL.md": ("Two independent gates",),
    "skills/subagent-driven-development/SKILL.md": (
        "Root executes work it already holds the context for.",
        "continue locally; unavailable subagents never block.",
        "Worker completion does not trigger a task review, package suite, closeout, or",
        "scripts/sdd-workspace PLAN_FILE",
        "only when the final risk-selected review actually runs.",
    ),
    "skills/requesting-code-review/SKILL.md": (
        "routine task, worker return, or local correction does not create a review gate.",
    ),
    "skills/executing-plans/SKILL.md": (
        "Do not run per-task acceptance, review, package suites, closeout, or",
    ),
    "skills/finishing-a-development-branch/SKILL.md": (
        "unconditionally run the full suite because this skill was loaded.",
    ),
    "skills/dispatching-parallel-agents/SKILL.md": (
        "Independence is necessary, not sufficient.",
        "Run one root-owned risk-selected acceptance set after integration",
        "Run the full suite only at epic/release",
    ),
    "skills/subagent-driven-development/task-reviewer-prompt.md": (
        "It is not a per-worker or per-plan-checkbox gate.",
    ),
    "skills/subagent-driven-development/re-review-prompt.md": (
        "This is not a routine re-review step.",
    ),
    "skills/writing-skills/testing-skills-with-subagents.md": (
        "deterministic wording corrections use",
    ),
    "skills/using-superpowers/SKILL.md": (
        "Invoke a skill when the user names it or its trigger clearly matches.",
    ),
    "skills/using-superpowers/references/codex-tools.md": (
        "Routine task completion does not wait for a per-task reviewer.",
    ),
    "skills/using-git-worktrees/SKILL.md": (
        "Safe, reversible worktree creation does not need duplicate confirmation.",
        "Do not run a full suite merely because a worktree was created.",
    ),
    "tests/policy/test-bounded-tdd-workflow.sh": (
        "Static overlay drift guard only.",
    ),
}

FORBIDDEN = {
    "skills/test-driven-development/SKILL.md": (
        "After a localized fix, rerun the changed invariant and affected slice",
    ),
    "skills/verification-before-completion/SKILL.md": (
        "If you haven't run the verification command in this message",
        "Execute the FULL command (fresh, complete)",
    ),
    "skills/subagent-driven-development/implementer-prompt.md": (
        "full suite once before committing",
    ),
    "skills/writing-plans/SKILL.md": (
        "Each step is one action (2-5 minutes)",
    ),
    "skills/brainstorming/SKILL.md": (
        "This applies to EVERY project regardless of perceived simplicity.",
    ),
    "skills/subagent-driven-development/SKILL.md": (
        "Review after each task",
        "Keep ordinary medium work",
        "Default to the current owner for simple and ordinary medium",
        "Keep the combined correctness/improvement review local by default",
    ),
    "skills/requesting-code-review/SKILL.md": ("Review early, review often.",),
    "skills/using-superpowers/SKILL.md": (
        "even a 1% chance a skill might apply",
    ),
    "skills/using-superpowers/references/codex-tools.md": (
        "Keep each implementer subagent open until its task's review passes",
    ),
    "skills/using-git-worktrees/SKILL.md": (
        "Would you like me to set up an isolated worktree?",
        "Run tests to ensure workspace starts clean:",
        "Then run setup and baseline tests in place.",
    ),
    "skills/dispatching-parallel-agents/SKILL.md": (
        "description: Use when facing 2+ independent tasks",
        "3. **Run full suite**",
        "4. **Spot check**",
    ),
}


class UpdateError(RuntimeError):
    """A recoverable, user-facing update failure."""


def run(
    repo: Path,
    *args: str,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args],
        cwd=repo,
        text=True,
        capture_output=capture,
        check=check,
    )


def output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())


def policy_errors(repo: Path) -> list[str]:
    errors: list[str] = []
    for relative, markers in REQUIRED.items():
        path = repo / relative
        if not path.is_file():
            errors.append(f"missing file: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(f"missing marker in {relative}: {marker}")
    for relative, markers in FORBIDDEN.items():
        path = repo / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker in text:
                errors.append(f"obsolete marker in {relative}: {marker}")
    return errors


def validate_repo(repo: Path) -> None:
    if not PATCH.is_file():
        raise UpdateError(f"overlay patch is missing: {PATCH}")
    result = run(repo, "git", "rev-parse", "--is-inside-work-tree", check=False)
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise UpdateError(f"not a Git worktree: {repo}")


def require_clean(repo: Path) -> None:
    status = run(repo, "git", "status", "--porcelain").stdout.strip()
    if status:
        raise UpdateError(
            "Superpowers worktree is not clean; commit or preserve its changes before updating."
        )


def validate_contract(repo: Path) -> None:
    errors = policy_errors(repo)
    if errors:
        raise UpdateError("bounded-TDD contract mismatch:\n- " + "\n- ".join(errors))
    result = run(
        repo,
        "bash",
        "tests/policy/test-bounded-tdd-workflow.sh",
        check=False,
    )
    if result.returncode:
        raise UpdateError(
            "bounded-TDD contract test failed:\n" + (output(result) or "no output")
        )


def detected_claude_home(repo: Path) -> Path | None:
    override = os.environ.get("SUPERPOWERS_CLAUDE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if repo != DEFAULT_REPO.expanduser().resolve():
        return None
    return DEFAULT_CLAUDE_HOME.expanduser().resolve()


def package_version(repo: Path) -> str:
    path = repo / "package.json"
    if not path.is_file():
        raise UpdateError(f"Superpowers package metadata is missing: {path}")
    version = json.loads(path.read_text(encoding="utf-8")).get("version")
    if not isinstance(version, str) or not version:
        raise UpdateError(f"Superpowers version is missing: {path}")
    return version


def claude_distribution_path(claude_home: Path) -> Path:
    return claude_home / "skills" / "superpowers"


def claude_settings(claude_home: Path) -> tuple[Path, dict[str, object]]:
    path = claude_home / "settings.json"
    if not path.exists():
        return path, {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise UpdateError(f"Claude settings must be a JSON object: {path}")
    return path, data


def write_json_atomic(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def official_plugin_installed(claude_home: Path) -> bool:
    """True when Claude's plugin registry still lists the official plugin.

    Claude Code resolves plugin names from the registry, so a registered
    official plugin takes precedence over the skills-dir copy even when it is
    disabled, and the skills-dir copy is silently not loaded.
    """
    registry = claude_home / CLAUDE_INSTALLED_PLUGINS
    if not registry.is_file():
        return False
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        plugins = data if isinstance(data, dict) else {}
    return bool(plugins.get(CLAUDE_OFFICIAL_PLUGIN_KEY))


def distribution_errors(source: Path, claude_home: Path) -> list[str]:
    errors: list[str] = []
    if official_plugin_installed(claude_home):
        errors.append(
            f"official Claude plugin is still installed: {CLAUDE_OFFICIAL_PLUGIN_KEY}; "
            f"Claude Code loads it in preference to {CLAUDE_PLUGIN_KEY} even when "
            f"disabled; run `claude plugin uninstall {CLAUDE_OFFICIAL_PLUGIN_KEY}`"
        )
    target = claude_distribution_path(claude_home)
    manifest = target / ".claude-plugin/plugin.json"
    if not manifest.is_file():
        errors.append(f"missing Claude skills-dir manifest: {manifest}")
    else:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("name") != "superpowers":
            errors.append("Claude skills-dir manifest name must be superpowers")
        if data.get("version") != package_version(source):
            errors.append(
                "Claude skills-dir version does not match the local checkout"
            )

    if (target / "hooks").exists():
        errors.append("Claude skills-dir distribution must not contain hooks")

    source_skills = source / "skills"
    target_skills = target / "skills"
    source_files = {
        path.relative_to(source_skills)
        for path in source_skills.rglob("*")
        if path.is_file()
    }
    target_files = (
        {
            path.relative_to(target_skills)
            for path in target_skills.rglob("*")
            if path.is_file()
        }
        if target_skills.is_dir()
        else set()
    )
    if source_files != target_files:
        errors.append("Claude skills-dir file set does not match the local checkout")
    else:
        for relative in sorted(source_files):
            if (source_skills / relative).read_bytes() != (
                target_skills / relative
            ).read_bytes():
                errors.append(f"Claude skills-dir drift: skills/{relative}")

    _, settings = claude_settings(claude_home)
    enabled = settings.get("enabledPlugins", {})
    if not isinstance(enabled, dict):
        errors.append("Claude enabledPlugins must be a JSON object")
    else:
        if enabled.get(CLAUDE_PLUGIN_KEY) is not True:
            errors.append(f"Claude plugin is not enabled: {CLAUDE_PLUGIN_KEY}")
        if enabled.get(CLAUDE_OFFICIAL_PLUGIN_KEY, False) is not False:
            errors.append(
                f"official Claude plugin is not disabled: {CLAUDE_OFFICIAL_PLUGIN_KEY}"
            )
    return errors


def validate_claude_distribution(source: Path, claude_home: Path) -> None:
    errors = distribution_errors(source, claude_home)
    if errors:
        raise UpdateError(
            "hookless Claude distribution mismatch:\n- " + "\n- ".join(errors)
        )


def install_claude_distribution(source: Path, claude_home: Path) -> None:
    validate_contract(source)
    skills_root = claude_home / "skills"
    target = claude_distribution_path(claude_home)
    skills_root.mkdir(parents=True, exist_ok=True)

    staging = Path(
        tempfile.mkdtemp(prefix=".superpowers-staging-", dir=skills_root)
    )
    backup = Path(
        tempfile.mkdtemp(prefix=".superpowers-backup-", dir=skills_root)
    )
    backup.rmdir()
    settings_path, settings = claude_settings(claude_home)
    old_settings = settings_path.read_bytes() if settings_path.exists() else None
    replaced_existing = False
    installed_new = False
    try:
        (staging / ".claude-plugin").mkdir(parents=True)
        shutil.copy2(
            source / ".claude-plugin/plugin.json",
            staging / ".claude-plugin/plugin.json",
        )
        shutil.copy2(source / "package.json", staging / "package.json")
        shutil.copytree(source / "skills", staging / "skills", symlinks=True)

        if target.exists() or target.is_symlink():
            target.replace(backup)
            replaced_existing = True
        staging.replace(target)
        installed_new = True

        enabled = settings.setdefault("enabledPlugins", {})
        if not isinstance(enabled, dict):
            raise UpdateError(
                f"Claude enabledPlugins must be a JSON object: {settings_path}"
            )
        enabled[CLAUDE_OFFICIAL_PLUGIN_KEY] = False
        enabled[CLAUDE_PLUGIN_KEY] = True
        write_json_atomic(settings_path, settings)
        validate_claude_distribution(source, claude_home)
    except Exception:
        if installed_new and (target.exists() or target.is_symlink()):
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        if replaced_existing and backup.exists():
            backup.replace(target)
        if old_settings is None:
            if settings_path.exists():
                settings_path.unlink()
        else:
            settings_path.write_bytes(old_settings)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists():
            shutil.rmtree(backup)


def current_head(repo: Path) -> str:
    result = run(repo, "git", "rev-parse", "HEAD", check=False)
    head = result.stdout.strip()
    if result.returncode or not head:
        raise UpdateError(f"cannot read HEAD in {repo}:\n{output(result) or 'no output'}")
    return head


def restore_overlay_state(repo: Path, head: str) -> None:
    """Put HEAD, the index, and the worktree back exactly as they were.

    Reversing the same patch is not the inverse of applying it. `--3way` stages
    what it writes and may fall back to a direct application, so a plain
    `git apply --reverse` can leave the index staged, the worktree dirty, or
    both — and its return code used to be discarded, so nobody found out.
    Resetting to the commit recorded before the apply is the actual inverse,
    and it is only safe because `apply_overlay` proves the worktree is clean
    first. Whether it worked is then checked rather than assumed.
    """

    problems: list[str] = []
    reset = run(repo, "git", "reset", "--hard", head, check=False)
    if reset.returncode:
        problems.append(output(reset) or "git reset --hard failed")
    # A patch that adds files leaves them behind once they are unstaged.
    clean = run(repo, "git", "clean", "-fdq", check=False)
    if clean.returncode:
        problems.append(output(clean) or "git clean failed")
    restored = run(repo, "git", "rev-parse", "HEAD", check=False)
    if restored.returncode or restored.stdout.strip() != head:
        problems.append(
            f"HEAD is {restored.stdout.strip() or 'unreadable'}, expected {head}"
        )
    status = run(repo, "git", "status", "--porcelain", check=False)
    if status.returncode:
        problems.append(output(status) or "git status failed")
    elif status.stdout.strip():
        problems.append("worktree is not clean after recovery:\n" + status.stdout.strip())
    if problems:
        raise UpdateError(
            f"could not restore {repo} to {head}; resolve this by hand before "
            "updating again:\n- " + "\n- ".join(problems)
        )


def fail_after_restore(repo: Path, head: str, failure: UpdateError) -> None:
    """Always raise: the original failure, or both failures when recovery broke too."""
    try:
        restore_overlay_state(repo, head)
    except UpdateError as recovery:
        raise UpdateError(f"{failure}\n\nautomatic recovery also failed:\n{recovery}") from failure
    raise failure


def apply_overlay(repo: Path) -> None:
    # Recovery resets to this commit, so the tree must be clean before the apply
    # and the commit must be known before anything writes to the worktree.
    require_clean(repo)
    head = current_head(repo)
    preflight = run(
        repo,
        "git",
        "apply",
        "--3way",
        "--check",
        str(PATCH),
        check=False,
    )
    if preflight.returncode:
        raise UpdateError(
            "overlay no longer applies cleanly; inspect upstream drift and update the "
            f"versioned patch.\n{output(preflight)}"
        )
    applied = run(
        repo,
        "git",
        "apply",
        "--3way",
        str(PATCH),
        check=False,
    )
    if applied.returncode:
        # `--check` passing does not promise the apply left nothing behind.
        fail_after_restore(
            repo, head, UpdateError("overlay application failed:\n" + output(applied))
        )
    try:
        validate_contract(repo)
    except UpdateError as exc:
        fail_after_restore(repo, head, exc)


def unique_backup_ref(repo: Path) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    base = f"backup/superpowers-overlay-{stamp}"
    candidate = base
    suffix = 2
    while run(
        repo,
        "git",
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/heads/{candidate}",
        check=False,
    ).returncode == 0:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def update(repo: Path, upstream: str) -> None:
    require_clean(repo)
    remote = upstream.split("/", 1)[0]
    fetched = run(repo, "git", "fetch", remote, check=False)
    if fetched.returncode:
        raise UpdateError(f"fetch failed for {remote}:\n{output(fetched)}")
    if run(repo, "git", "rev-parse", "--verify", upstream, check=False).returncode:
        raise UpdateError(f"upstream ref is unavailable after fetch: {upstream}")

    backup = unique_backup_ref(repo)
    run(repo, "git", "branch", backup, "HEAD")
    rebased = run(repo, "git", "rebase", upstream, check=False)
    if rebased.returncode:
        run(repo, "git", "rebase", "--abort", check=False)
        raise UpdateError(
            f"rebase conflicted; original state is preserved at {backup}.\n"
            f"{output(rebased)}"
        )

    if policy_errors(repo):
        apply_overlay(repo)
        run(repo, "git", "add", "--", *TARGETS)
        committed = run(
            repo,
            "git",
            "commit",
            "-m",
            "local: apply bounded TDD overlay",
            check=False,
        )
        if committed.returncode:
            raise UpdateError(
                f"overlay applied but commit failed; recoverable backup: {backup}.\n"
                f"{output(committed)}"
            )
    else:
        validate_contract(repo)

    print(f"Superpowers overlay is current; backup: {backup}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--claude-home", type=Path)
    parser.add_argument("--upstream", default="origin/main")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.expanduser().resolve()
    try:
        validate_repo(repo)
        claude_home = (
            args.claude_home.expanduser().resolve()
            if args.claude_home
            else detected_claude_home(repo)
        )
        if args.check:
            validate_contract(repo)
            if claude_home:
                validate_claude_distribution(repo, claude_home)
            print("Superpowers bounded-TDD contract: ok")
        elif args.apply_only:
            require_clean(repo)
            if policy_errors(repo):
                apply_overlay(repo)
                print("Superpowers bounded-TDD overlay applied")
            else:
                validate_contract(repo)
                print("Superpowers bounded-TDD overlay already present")
            if claude_home:
                install_claude_distribution(repo, claude_home)
                print(
                    "Claude hookless Superpowers distribution: "
                    f"{claude_distribution_path(claude_home)}"
                )
        else:
            update(repo, args.upstream)
            if claude_home:
                install_claude_distribution(repo, claude_home)
                print(
                    "Claude hookless Superpowers distribution: "
                    f"{claude_distribution_path(claude_home)}"
                )
    except (OSError, subprocess.SubprocessError, UpdateError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
