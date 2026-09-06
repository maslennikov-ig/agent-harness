#!/usr/bin/env python3
"""Smoke-check the portable orchestration console files."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "prompts" / "manifest.json"
PANEL = ROOT / "scripts" / "orchestration_panel.py"
# `.venv` is a generated, machine-local runtime tree: uv writes absolute paths
# into its activate scripts, so the portability scan must not read it.
SKIP_DIRS = {
    ".beads",
    ".codex",
    ".git",
    ".playwright-cli",
    ".venv",
    "dist",
    "node_modules",
    "state",
    "stitch",
    "test-results",
    "__pycache__",
}
TEXT_SUFFIXES = {
    "",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".txt",
    ".yml",
}
FORBIDDEN_PUBLIC_PATTERNS = [
    re.compile(r"/home/[A-Za-z0-9_.-]+(?:/|(?=[\"'\s]))"),
    re.compile(r"/mnt/c/Users/[A-Za-z0-9_.-]+(?:/|(?=[\"'\s]))"),
]
CLAUDE_COMMON_MARKER = "Claude common overlay"
CLAUDE_FABLE_MARKER = "Claude profile overlay: Fable 5.1"
CLAUDE_OPUS_MARKER = "Claude profile overlay: Opus 5"
CLAUDE_OVERLAY_MARKERS = [CLAUDE_COMMON_MARKER, CLAUDE_FABLE_MARKER, CLAUDE_OPUS_MARKER]
CODEX_COMMON_MARKER = "Codex common overlay"
CODEX_ASTRA_MARKER = "Codex profile overlay: GPT-6 Astra"
CODEX_OVERLAY_MARKERS = [CODEX_COMMON_MARKER, CODEX_ASTRA_MARKER]
ALL_OVERLAY_MARKERS = CLAUDE_OVERLAY_MARKERS + CODEX_OVERLAY_MARKERS
EXPECTED_PROFILE_OVERLAYS = {
    "fable-5.1": ["profiles/claude-fable.md"],
    "opus-5": ["profiles/claude-opus-5.md"],
    "gpt-6-astra": ["profiles/codex-gpt-6-astra.md"],
}
FORBIDDEN_REASONING_PATTERNS = [
    ("explain your reasoning", re.compile(r"\bexplain\s+your\s+reasoning\b", re.IGNORECASE)),
    ("show your reasoning", re.compile(r"\bshow\s+your\s+reasoning\b", re.IGNORECASE)),
    ("think step by step", re.compile(r"\bthink\s+step\s+by\s+step\b", re.IGNORECASE)),
    ("chain-of-thought", re.compile(r"\bchain[-\s]?of[-\s]?thought\b", re.IGNORECASE)),
    ("покажи ход мыслей", re.compile(r"покажи\s+(?:свой\s+)?ход\s+мысл", re.IGNORECASE)),
    ("покажи рассуждения", re.compile(r"покажи[^\n]{0,80}рассуждени", re.IGNORECASE)),
    ("ход рассуждений", re.compile(r"ход\s+рассуждени", re.IGNORECASE)),
]


def fail(message: str) -> None:
    print(f"validate_console: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_panel_module():
    spec = importlib.util.spec_from_file_location("orchestration_panel", PANEL)
    if spec is None or spec.loader is None:
        fail(f"cannot load {PANEL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prompt_supports_runtime(item: dict, runtime: str) -> bool:
    runtimes = item.get("runtimes") or []
    return "shared" in runtimes or runtime in runtimes


def overlay_files(profile: dict) -> list[str]:
    overlays = profile.get("overlays")
    if isinstance(overlays, list):
        return [str(item).strip() for item in overlays if str(item).strip()]
    file_name = str(profile.get("file") or "").strip()
    return [file_name] if file_name else []


def assert_overlay_state(
    payload: dict,
    runtime: str,
    profile_id: str | None,
    required_markers: list[str],
    forbidden_markers: list[str],
) -> None:
    active_profile = payload.get("active_profile")
    if profile_id is None:
        if active_profile is not None:
            fail(f"{runtime} payload unexpectedly selected profile: {active_profile!r}")
    elif (active_profile or {}).get("id") != profile_id:
        fail(f"{runtime}/{profile_id} profile not selected")

    prompts = payload.get("prompts") or []
    if not isinstance(prompts, list) or not prompts:
        fail(f"{runtime}/{profile_id or 'none'} payload has no prompts")

    checked_supported = 0
    for item in prompts:
        text = str(item.get("text") or "")
        prompt_id = str(item.get("id") or "")
        if profile_id is None:
            if item.get("profile") is not None:
                fail(f"{runtime} prompt {prompt_id} unexpectedly has profile metadata")
            for marker in ALL_OVERLAY_MARKERS:
                if marker in text:
                    fail(f"{runtime} prompt {prompt_id} unexpectedly contains overlay {marker!r}")
            continue

        if prompt_supports_runtime(item, runtime):
            checked_supported += 1
            for marker in required_markers:
                if marker not in text:
                    fail(f"{runtime}/{profile_id} prompt {prompt_id} missing overlay {marker!r}")
            for marker in forbidden_markers:
                if marker in text:
                    fail(f"{runtime}/{profile_id} prompt {prompt_id} has forbidden overlay {marker!r}")
        else:
            for marker in ALL_OVERLAY_MARKERS:
                if marker in text:
                    fail(f"{runtime}/{profile_id} prompt {prompt_id} should not contain overlay {marker!r}")

    if profile_id is not None and checked_supported == 0:
        fail(f"{runtime}/{profile_id} had no runtime-supported prompts to check")


def validate_prompt_hygiene() -> None:
    prompt_paths = sorted((ROOT / "prompts").rglob("*.md"))
    for path in prompt_paths:
        relative = path.relative_to(ROOT)
        data = path.read_bytes()
        if b"\r\n" in data:
            fail(f"CRLF found in {relative}")
        text = data.decode("utf-8", errors="replace")
        for label, pattern in FORBIDDEN_REASONING_PATTERNS:
            if pattern.search(text):
                fail(f"forbidden reasoning-extraction phrase {label!r} found in {relative}")

    for path in sorted((ROOT / "prompts").glob("claude-*.md")):
        text = path.read_text(encoding="utf-8")
        if "Claude model guidance:" in text:
            fail(f"duplicated Claude model guidance remains in {path.relative_to(ROOT)}")


def validate_rule_ownership() -> None:
    """One owner per semantic rule, plus cross-runtime kernel containment."""

    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    from orch_panel import context_policy as policy

    audit = policy.audit_rule_ownership()
    for rule_id, paths in sorted(audit["unowned_occurrences"].items()):
        fail(f"semantic rule {rule_id} also appears in unowned files: {paths}")
    for label in ("duplicate_rule_ids", "invalid_rules", "hash_drift", "source_drift"):
        if audit[label]:
            fail(f"semantic ownership {label}: {audit[label]}")
    for rule_id, reason in sorted(audit["uncovered"].items()):
        fail(f"semantic rule {rule_id} is uncovered: {reason}")
    if not audit["ok"]:
        fail("semantic ownership audit failed")

    # The character budgets say how much context the harness spends. This says
    # how much it demands, which is the number the operator feels on every
    # task. Printed rather than gated: it is a direction, not a threshold.
    counts = audit["gate_counts"]
    print(
        f"validate_console: gates {counts['always_on']} always-on / "
        f"{counts['triggered']} triggered; "
        f"{counts['always_on_obligations']} always-on obligation(s)"
        + (
            f": {', '.join(audit['always_on_obligations'])}"
            if audit["always_on_obligations"]
            else ""
        )
    )

    private_root = private_repo_root()
    if private_root is None:
        print("validate_console: private Codex kernel unavailable; parity not checked")
        return
    parity = policy.kernel_parity_report(
        policy.KERNEL_PATH, private_root / "private" / "codex" / "global" / "AGENTS.md"
    )
    if not parity["ok"]:
        fail(f"Codex runtime kernel is missing canonical bullets: {parity['missing']}")


def private_repo_root() -> Path | None:
    import os

    root = Path(
        os.environ.get(
            "AGENT_HARNESS_PRIVATE_ROOT",
            str(ROOT / "harness" / "private"),
        )
    )
    return root if (root / "private" / "codex" / "global" / "AGENTS.md").is_file() else None


def validate_no_orphan_prompts(items: list) -> None:
    referenced: set[Path] = set()
    for item in items:
        for key in ("file", "launcher_file"):
            name = str(item.get(key) or "").strip()
            if name:
                referenced.add((ROOT / "prompts" / name).resolve())
    mechanism_dirs = {"profiles", "policies", "fragments"}
    for path in sorted((ROOT / "prompts").rglob("*.md")):
        relative = path.relative_to(ROOT / "prompts")
        if relative.parts and relative.parts[0] in mechanism_dirs:
            continue
        if path.resolve() not in referenced:
            fail(f"orphan prompt file not referenced by manifest: prompts/{relative}")


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    profiles = data.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        fail("manifest has no prompt profiles")
    profile_ids: set[str] = set()
    defaults_by_runtime: dict[str, int] = {}
    for profile in profiles:
        profile_id = str(profile.get("id") or "").strip()
        runtime = str(profile.get("runtime") or "").strip()
        file_name = str(profile.get("file") or "").strip()
        if not profile_id:
            fail("manifest profile without id")
        if profile_id in profile_ids:
            fail(f"duplicate profile id: {profile_id}")
        profile_ids.add(profile_id)
        if runtime not in {"claude", "codex"}:
            fail(f"manifest profile {profile_id} has invalid runtime: {runtime}")
        if profile.get("default"):
            defaults_by_runtime[runtime] = defaults_by_runtime.get(runtime, 0) + 1
        profile_overlay_files = overlay_files(profile)
        if profile_id in EXPECTED_PROFILE_OVERLAYS and profile_overlay_files != EXPECTED_PROFILE_OVERLAYS[profile_id]:
            fail(f"manifest profile {profile_id} overlays {profile_overlay_files} != {EXPECTED_PROFILE_OVERLAYS[profile_id]}")
        for overlay_file in profile_overlay_files:
            path = ROOT / "prompts" / overlay_file
            if not path.is_file():
                fail(f"manifest profile file missing: {overlay_file}")
            if not path.read_text(encoding="utf-8").strip():
                fail(f"manifest profile file is empty: {overlay_file}")
    for runtime in ("claude", "codex"):
        if defaults_by_runtime.get(runtime) != 1:
            fail(f"manifest must have exactly one default {runtime} profile")
    default_ids = {
        str(profile.get("runtime")): str(profile.get("id"))
        for profile in profiles
        if profile.get("default")
    }
    if default_ids.get("claude") != "fable-5.1":
        fail("Fable 5.1 must be the default Claude profile")
    if default_ids.get("codex") != "gpt-6-astra":
        fail("GPT-6 Astra must be the default Codex profile")
    for required_profile in {"fable-5.1", "opus-5", "gpt-6-astra"}:
        if required_profile not in profile_ids:
            fail(f"manifest profile missing: {required_profile}")
    for removed_profile in {"universal", "opus-4.8"}:
        if removed_profile in profile_ids:
            fail(f"removed profile remains selectable: {removed_profile}")

    items = data.get("prompts")
    if not isinstance(items, list) or not items:
        fail("manifest has no prompts")

    ids: set[str] = set()
    for item in items:
        prompt_id = str(item.get("id") or "").strip()
        file_name = str(item.get("file") or "").strip()
        launcher_file_name = str(item.get("launcher_file") or "").strip()
        library_visibility = str(item.get("library_visibility") or "").strip()
        runtimes = item.get("runtimes")
        if not prompt_id:
            fail("manifest prompt without id")
        if prompt_id in ids:
            fail(f"duplicate prompt id: {prompt_id}")
        ids.add(prompt_id)
        if not isinstance(runtimes, list) or not runtimes:
            fail(f"manifest prompt {prompt_id} has no runtimes")
        invalid_runtimes = sorted(set(runtimes) - {"shared", "codex", "claude"})
        if invalid_runtimes:
            fail(f"manifest prompt {prompt_id} has invalid runtimes: {invalid_runtimes}")
        if library_visibility not in {"manual", "system"}:
            fail(
                f"manifest prompt {prompt_id} has invalid library_visibility: "
                f"{library_visibility!r}"
            )
        if not file_name:
            fail(f"manifest prompt {prompt_id} has no file")
        if not launcher_file_name:
            fail(f"manifest prompt {prompt_id} has no launcher_file")
        path = ROOT / "prompts" / file_name
        if not path.is_file():
            fail(f"manifest prompt file missing: {file_name}")
        if not path.read_text(encoding="utf-8").strip():
            fail(f"manifest prompt file is empty: {file_name}")
        launcher_path = ROOT / "prompts" / launcher_file_name
        if not launcher_path.is_file():
            fail(f"manifest prompt launcher file missing: {launcher_file_name}")
        launcher_text = launcher_path.read_text(encoding="utf-8").strip()
        if not launcher_text:
            fail(f"manifest prompt launcher file is empty: {launcher_file_name}")
        if len(launcher_text) > 1000:
            fail(f"manifest prompt launcher too large: {launcher_file_name}")

    validate_no_orphan_prompts(items)

    module = load_panel_module()
    payload = module.prompt_payload()
    if payload.get("source") != "manifest":
        fail(f"expected manifest source, got {payload.get('source')!r}")

    prompt_payload = payload.get("prompts")
    if not isinstance(prompt_payload, list):
        fail("payload prompts is not a list")
    if len(prompt_payload) != len(items):
        fail(f"payload count {len(prompt_payload)} != manifest count {len(items)}")

    payload_ids = {str(item.get("id")) for item in prompt_payload}
    if payload_ids != ids:
        fail("payload ids differ from manifest ids")
    if not all(isinstance(item.get("runtimes"), list) and item["runtimes"] for item in prompt_payload):
        fail("payload prompts missing runtime metadata")
    for item in prompt_payload:
        if not item.get("launcher_text"):
            fail(f"payload prompt {item.get('id')} missing launcher_text")
        if not item.get("full_text"):
            fail(f"payload prompt {item.get('id')} missing full_text")
        if item.get("text") != item.get("full_text"):
            fail(f"payload prompt {item.get('id')} text must alias full_text")
        if not isinstance(item.get("launcher_chars"), int) or not isinstance(item.get("full_chars"), int):
            fail(f"payload prompt {item.get('id')} missing prompt size metadata")
    if payload.get("active_profile") is not None:
        fail("runtime-less payload unexpectedly selected a profile")
    assert_overlay_state(
        module.prompt_payload(runtime="codex"),
        runtime="codex",
        profile_id="gpt-6-astra",
        required_markers=[CODEX_ASTRA_MARKER],
        forbidden_markers=[CODEX_COMMON_MARKER] + CLAUDE_OVERLAY_MARKERS,
    )
    assert_overlay_state(
        module.prompt_payload(runtime="claude", profile_id="fable-5.1"),
        runtime="claude",
        profile_id="fable-5.1",
        required_markers=[CLAUDE_FABLE_MARKER],
        forbidden_markers=[CLAUDE_COMMON_MARKER, CLAUDE_OPUS_MARKER] + CODEX_OVERLAY_MARKERS,
    )
    assert_overlay_state(
        module.prompt_payload(runtime="claude", profile_id="opus-5"),
        runtime="claude",
        profile_id="opus-5",
        required_markers=[CLAUDE_OPUS_MARKER],
        forbidden_markers=[CLAUDE_COMMON_MARKER, CLAUDE_FABLE_MARKER] + CODEX_OVERLAY_MARKERS,
    )
    for removed_profile in ("universal", "opus-4.8"):
        try:
            module.prompt_payload(runtime="claude", profile_id=removed_profile)
        except ValueError:
            pass
        else:
            fail(f"removed profile silently resolved: {removed_profile}")
    if "dependency-docs-upgrade" not in ids:
        fail("dependency-docs-upgrade prompt missing")
    if "claude-start-stage" not in ids:
        fail("claude-start-stage prompt missing")

    docs_context = module.docs_context_payload()
    required_docs_keys = {"summary", "dependencies", "commands", "context7", "mcp", "sync_plan"}
    if not isinstance(docs_context, dict) or not required_docs_keys.issubset(docs_context):
        fail("docs_context_payload missing required keys")
    commands = docs_context.get("commands") or {}
    if not str(commands.get("refresh", "")).startswith("orch-prompts "):
        fail("docs context commands must prefer orch-prompts")

    overview = module.overview_payload()
    runtimes = overview.get("runtimes") or {}
    runtime_ids = {item.get("id") for item in runtimes.get("items", []) if isinstance(item, dict)}
    if not {"codex", "claude"}.issubset(runtime_ids):
        fail("overview runtimes must include codex and claude")
    claude = module.runtime_payload("claude")
    if "settings" not in claude or "vscode_wsl" not in claude or "plugins" not in claude:
        fail("claude runtime payload missing settings/vscode_wsl/plugins")
    masked = module.mask_secret_text("token=abc123 ANTHROPIC_API_KEY=secret ctx7sk-test")
    if "abc123" in masked or "secret" in masked or "ctx7sk-test" in masked:
        fail("secret masking failed")
    timed = module.run(["python3", "-c", "import time; time.sleep(2)"], timeout=1)
    if timed.returncode != 124 or "Timed out" not in (timed.stderr or ""):
        fail("timeout-safe command runner failed")

    plugin_root = ROOT / "claude-plugin" / "orchestration-bridge"
    if not (plugin_root / ".claude-plugin" / "plugin.json").is_file():
        fail("Claude orchestration plugin manifest missing")
    for name in ["orchestrator-stage", "dependency-docs-upgrade", "closeout"]:
        if not (plugin_root / "skills" / name / "SKILL.md").is_file():
            fail(f"Claude plugin skill missing: {name}")
    if not (plugin_root / "commands" / "stage.md").is_file():
        fail("Claude plugin command missing: commands/stage.md")
    for name in ["docs-researcher", "docs-reviewer", "correctness-reviewer", "improvement-reviewer", "worker"]:
        if not (plugin_root / "agents" / f"{name}.md").is_file():
            fail(f"Claude plugin agent missing: {name}")
    for name in ["correctness-reviewer", "docs-reviewer", "improvement-reviewer"]:
        text = (plugin_root / "agents" / f"{name}.md").read_text(encoding="utf-8")
        if "Stay read-only" not in text:
            fail(f"Claude reviewer agent lacks read-only policy: {name}")

    validate_prompt_hygiene()
    validate_rule_ownership()

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = set(path.relative_to(ROOT).parts)
        if relative_parts & SKIP_DIRS:
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in FORBIDDEN_PUBLIC_PATTERNS:
            if pattern.search(text):
                fail(f"machine-specific home path found in {path.relative_to(ROOT)}")

    print(f"validate_console: ok ({len(items)} prompts, source=manifest)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
