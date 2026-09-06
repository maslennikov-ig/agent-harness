"""Thin-context composition and semantic ownership checks.

This module owns prompt-layer composition and deterministic context budgets.
It deliberately does not own task workflow, model selection, or repository
policy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


CONSOLE_DIR = Path(__file__).resolve().parents[2]
KERNEL_ID = "shared-orchestration/v1"
KERNEL_MARKER = f"harness-kernel: {KERNEL_ID}"
KERNEL_PATH = CONSOLE_DIR / "policy" / "runtime-kernel-v1.md"
LEDGER_PATH = CONSOLE_DIR / "policy" / "semantic-rule-ownership.json"

# Single source of truth for every context budget. `evaluate_thin_context.py`
# imports this table rather than keeping a second copy that could drift.
LAYER_BUDGETS = {
    # Raised from 3500 once the cap started costing content: the plain-language
    # rule would not fit, and the previous time the kernel hit this ceiling the
    # design-routing block was silently dropped to make room. Raise it
    # deliberately rather than let the budget decide what the kernel says.
    "kernel": 3_800,
    "model_overlay": 1_500,
    "launcher": 1_000,
    "router": 4_500,
    "reference": 3_000,
    "scenario_references": 5_000,
    "selective_skill": 5_000,
    "hook_output": 1_000,
}
MANAGED_BEGIN = "<!-- HARNESS-KERNEL:BEGIN -->"
MANAGED_END = "<!-- HARNESS-KERNEL:END -->"

# A retired rule survives as a paraphrase far more often than as its exact
# sentence: the mandatory-delegation rule was deleted from the ledger while four
# rewordings stayed live for weeks. Short markers catch the idea, not the
# wording, and are checked over the surfaces a runtime actually loads. Docs and
# specs are deliberately out of scope: they record history and must be free to
# quote a rule the harness no longer follows.
RETIRED_MARKER_SURFACES = (
    "prompts",
    "policy",
    "claude-plugin",
    "harness/private/private",
    "harness/core",
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
)
RETIRED_MARKER_SUFFIXES = {".md", ".json", ".toml", ".py", ".sh", ".txt"}

CORPUS_SUFFIX = ".md"
CORPUS_SKIP_DIRS = {
    ".beads",
    ".codex",
    ".git",
    ".playwright-cli",
    "__pycache__",
    "node_modules",
    "state",
    "stitch",
}
# Three words are enough to cover the current shortest meaningful ownership
# contract. Shorter text is too collision-prone and therefore fails closed as
# explicitly uncovered rather than silently bypassing the audit.
MIN_SCANNABLE_WORDS = 3

# Character budgets answer "how much context does the harness spend". They say
# nothing about how much the harness *demands*, which is the cost the operator
# actually feels: a rule can be one short line and still fire on every task.
# These two axes make that measurable.
#
# `trigger` — does the rule apply to every task, or only in a named situation.
# `burden` — what the rule does to the agent:
#   boundary   a safety limit; it forbids, it never asks for work
#   latitude   it grants freedom or narrows when something else applies
#   obligation it demands an action, an artifact, or a recorded decision
#
# An always-on obligation is the expensive combination and fails the ownership
# audit. Make it triggered with a named condition or model it as a boundary or
# latitude rule instead.
RULE_TRIGGERS = ("always-on", "triggered")
RULE_BURDENS = ("boundary", "latitude", "obligation")
REQUIRED_RULE_FIELDS = (
    "id",
    "source_path",
    "source_span",
    "rule_text",
    "normalized_hash",
    "disposition",
    "owner",
    "enforcement",
    "regression_scenario",
    "trigger",
    "burden",
)


def normalize_rule_text(text: str) -> str:
    """Normalize formatting drift without erasing semantic punctuation."""

    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)
        lines.append(cleaned)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def normalized_rule_hash(text: str) -> str:
    return hashlib.sha256(normalize_rule_text(text).encode("utf-8")).hexdigest()


def kernel_text(path: Path = KERNEL_PATH) -> str:
    return path.read_text(encoding="utf-8").strip()


def managed_kernel_body(text: str) -> str | None:
    if MANAGED_BEGIN not in text or MANAGED_END not in text:
        return None
    return text.split(MANAGED_BEGIN, 1)[1].split(MANAGED_END, 1)[0].strip()


def inspect_kernel_file(path: Path) -> dict[str, Any]:
    result = {
        "kernel_id": KERNEL_ID,
        "path": str(path),
        "matched": False,
        "status": "missing",
        "heuristic": True,
        "semantic_verified": False,
    }
    try:
        body = path.read_text(encoding="utf-8")
    except OSError:
        return result
    managed = managed_kernel_body(body)
    if managed is not None:
        result["semantic_verified"] = (
            normalize_rule_text(managed) == normalize_rule_text(kernel_text())
        )
        result["matched"] = result["semantic_verified"]
        result["status"] = "matched" if result["matched"] else "semantic_mismatch"
        result["heuristic"] = False
        return result
    if KERNEL_MARKER in body:
        normalized_body = normalize_rule_text(body)
        result["semantic_verified"] = all(
            bullet in normalized_body for bullet in kernel_bullets()
        )
        result["matched"] = result["semantic_verified"]
        result["status"] = (
            "matched" if result["matched"] else "semantic_mismatch"
        )
        result["heuristic"] = False
        return result
    result["status"] = "version_mismatch"
    return result


def runtime_kernel_path(
    runtime: str,
    *,
    home_dir: Path | None = None,
    windows_users_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    home = home_dir or Path.home()
    if runtime == "claude":
        start = (cwd or Path.cwd()).resolve()
        claude_home = Path(env.get("CLAUDE_HOME") or (home / ".claude"))
        global_claude = claude_home / "CLAUDE.md"
        memory_files = [
            directory / "CLAUDE.md"
            for directory in (start, *start.parents)
            if directory != Path(directory.anchor)
        ]
        if global_claude not in memory_files:
            memory_files.append(global_claude)

        for memory_file in memory_files:
            try:
                lines = memory_file.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            in_fence = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence or not re.fullmatch(r"@\S+", stripped):
                    continue
                raw_path = stripped[1:]
                if raw_path.startswith("~/"):
                    imported = home / raw_path[2:]
                else:
                    imported = Path(raw_path)
                    if not imported.is_absolute():
                        imported = memory_file.parent / imported
                try:
                    imported = imported.resolve()
                except (OSError, RuntimeError):
                    continue
                if inspect_kernel_file(imported)["matched"]:
                    return imported
        return global_claude
    if runtime == "codex":
        explicit = env.get("CODEX_HOME")
        if explicit:
            return Path(explicit) / "AGENTS.md"
        candidates = [home / ".codex"]
        users_root = windows_users_root or Path("/mnt/c/Users")
        if users_root.is_dir():
            candidates.extend(sorted(users_root.glob("*/.codex")))

        def score(path: Path) -> tuple[int, int]:
            value = int(path.is_dir())
            value += 4 * int((path / "AGENTS.md").is_file())
            value += 2 * int((path / "config.toml").is_file())
            return value, -len(str(path))

        base = max(candidates, key=score)
        return base / "AGENTS.md"
    raise ValueError(f"unsupported runtime: {runtime}")


def compose_prompt(
    task_text: str,
    overlay_text: str,
    *,
    mode: str,
    kernel_state: dict[str, Any],
    fallback_reason: str | None = None,
) -> str:
    if mode not in {"native", "portable"}:
        raise ValueError(f"invalid composition mode: {mode}")
    parts: list[str] = []
    if mode == "native":
        parts.append(
            f"Requires effective kernel: {KERNEL_ID}. "
            "If absent, request the portable prompt."
        )
    else:
        parts.append(kernel_text())
    parts.append(task_text.strip())
    if overlay_text.strip():
        parts.append(overlay_text.strip())
    return "\n\n---\n\n".join(part for part in parts if part)


def compose_dispatch_handoff(
    *,
    goal: str,
    write_zone: str = "",
    verification: str = "",
    stop: str = "",
    references: tuple[str, ...] = (),
    role_text: str = "",
    overlay_text: str = "",
) -> str:
    """Build the compact same-session worker contract for one agent dispatch.

    `role_text` is the explicitly chosen root-role card, resolved through the
    prompt manifest by the caller. Coordination adds task context and durable
    references only. The kernel, the repository rules, and the triggered skills
    are loaded structurally by the runtime, so this text must never restate
    them, and none of it is stored in coordination state.
    """
    lines = [f"Goal: {goal.strip()}"]
    if write_zone.strip():
        lines.append(f"Write zone: {write_zone.strip()}")
    if verification.strip():
        lines.append(f"Verification: {verification.strip()}")
    lines.append(
        f"Stop: {stop.strip()}"
        if stop.strip()
        else "Stop: the write zone or the goal would have to change."
    )
    if references:
        lines.append("References:")
        lines.extend(f"- {reference}" for reference in references)
    contract = "\n".join(lines)
    task_text = (
        f"{role_text.strip()}\n\n---\n\n{contract}" if role_text.strip() else contract
    )
    return compose_prompt(task_text, overlay_text, mode="native", kernel_state={})


def composition_metadata(
    runtime: str,
    overlay_text: str,
    kernel_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = kernel_state or inspect_kernel_file(runtime_kernel_path(runtime))
    return {
        "kernel_id": KERNEL_ID,
        "kernel_file": state,
        "recommended_mode": "native" if state["matched"] else "portable",
        "fallback_reason": None
        if state["matched"]
        else (
            "kernel not found"
            if state["status"] == "missing"
            else (
                "kernel semantic mismatch"
                if state["status"] == "semantic_mismatch"
                else "kernel version mismatch"
            )
        ),
        "kernel_chars": len(kernel_text()),
        "overlay_chars": len(overlay_text.strip()),
        "budgets": dict(LAYER_BUDGETS),
    }


def kernel_bullets(path: Path = KERNEL_PATH) -> list[str]:
    """Return the canonical kernel bullets as normalized single-line rules."""

    bullets: list[str] = []
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            if current:
                bullets.append(normalize_rule_text(" ".join(current)))
            current = [line[2:].strip()]
        elif current and line.startswith("  ") and line.strip():
            current.append(line.strip())
        elif current:
            bullets.append(normalize_rule_text(" ".join(current)))
            current = []
    if current:
        bullets.append(normalize_rule_text(" ".join(current)))
    return bullets


def kernel_parity_report(
    canonical_path: Path = KERNEL_PATH,
    runtime_path: Path = KERNEL_PATH,
) -> dict[str, Any]:
    """Assert every canonical kernel bullet survives verbatim in a runtime file.

    Cross-runtime parity is a containment check over the two kernel files rather
    than duplicated records in each repository's ownership ledger.
    """

    bullets = kernel_bullets(canonical_path)
    try:
        runtime_text = normalize_rule_text(runtime_path.read_text(encoding="utf-8"))
    except OSError:
        return {
            "ok": False,
            "canonical": str(canonical_path),
            "runtime": str(runtime_path),
            "bullets": len(bullets),
            "missing": bullets,
            "unreadable": True,
        }
    missing = [bullet for bullet in bullets if bullet not in runtime_text]
    return {
        "ok": not missing,
        "canonical": str(canonical_path),
        "runtime": str(runtime_path),
        "bullets": len(bullets),
        "missing": missing,
        "unreadable": False,
    }


def _markdown_corpus(source_root: Path) -> dict[str, str]:
    corpus: dict[str, str] = {}
    for path in source_root.rglob(f"*{CORPUS_SUFFIX}"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if set(relative.parts) & CORPUS_SKIP_DIRS:
            continue
        corpus[relative.as_posix()] = normalize_rule_text(
            path.read_text(encoding="utf-8", errors="replace")
        )
    return corpus


def _active_surface_corpus(
    source_root: Path,
    ledger_path: Path,
) -> dict[str, str]:
    """Lower-cased normalized text of every file a runtime actually loads."""

    corpus: dict[str, str] = {}
    ledger_name = None
    try:
        ledger_name = ledger_path.resolve().relative_to(source_root.resolve()).as_posix()
    except ValueError:
        pass
    for surface in RETIRED_MARKER_SURFACES:
        root = source_root / surface
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = [path for path in root.rglob("*") if path.is_file()]
        else:
            continue
        for path in candidates:
            if path.suffix not in RETIRED_MARKER_SUFFIXES:
                continue
            relative = path.relative_to(source_root).as_posix()
            if set(path.relative_to(source_root).parts) & CORPUS_SKIP_DIRS:
                continue
            if relative == ledger_name:
                continue
            corpus[relative] = normalize_rule_text(
                path.read_text(encoding="utf-8", errors="replace")
            ).lower()
    return corpus


def _span_bullet_index(source_span: str) -> int | None:
    match = re.fullmatch(r"kernel bullet (\d+)", source_span.strip())
    return int(match.group(1)) if match else None


def _scan_reason(source_path: str, rule_text: str) -> str | None:
    if len(rule_text.split()) < MIN_SCANNABLE_WORDS:
        return (
            f"rule_text is {len(rule_text.split())} words, below the "
            f"{MIN_SCANNABLE_WORDS}-word corpus-matching threshold"
        )
    return None


def audit_rule_ownership(
    ledger_path: Path = LEDGER_PATH,
    source_root: Path = CONSOLE_DIR,
) -> dict[str, Any]:
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        raise ValueError("semantic ownership ledger requires a rules array")

    ids = [str(item.get("id") or "") for item in rules]
    duplicate_rule_ids = sorted(
        rule_id for rule_id, count in Counter(ids).items() if rule_id and count > 1
    )
    invalid_rules: list[str] = []
    hash_drift: list[str] = []
    source_drift: list[str] = []
    unowned_occurrences: dict[str, list[str]] = {}
    unowned_policy_rules: dict[str, list[str]] = {}
    invalid_policy_sources: list[str] = []
    uncovered: dict[str, str] = {}
    always_on_obligations: list[str] = []
    span_drift: dict[str, str] = {}
    retired_marker_hits: dict[str, list[str]] = {}
    trigger_counts: Counter[str] = Counter()
    burden_counts: Counter[str] = Counter()
    corpus = _markdown_corpus(source_root)
    active_surfaces = _active_surface_corpus(source_root, ledger_path)
    for item in rules:
        rule_id = str(item.get("id") or "")
        if not rule_id or not set(REQUIRED_RULE_FIELDS) <= set(item):
            invalid_rules.append(rule_id or "<missing-id>")
            continue
        trigger = str(item["trigger"])
        burden = str(item["burden"])
        if trigger not in RULE_TRIGGERS or burden not in RULE_BURDENS:
            invalid_rules.append(rule_id)
            continue
        # A triggered rule that cannot say when it fires is an always-on rule
        # wearing a cheaper label, so the condition is required rather than
        # decorative.
        if trigger == "triggered" and not str(item.get("trigger_condition") or "").strip():
            invalid_rules.append(rule_id)
            continue
        if str(item["disposition"]) != "delete":
            trigger_counts[trigger] += 1
            burden_counts[burden] += 1
            if trigger == "always-on" and burden == "obligation":
                always_on_obligations.append(rule_id)
        source_path = str(item["source_path"])
        source = source_root / source_path
        disposition = str(item["disposition"])
        rule_text = str(item["rule_text"])
        normalized = normalize_rule_text(rule_text)
        if item["normalized_hash"] != normalized_rule_hash(rule_text):
            hash_drift.append(rule_id)

        if disposition == "delete":
            # A removed rule is healthy exactly when its text is gone. The
            # previous check demanded the opposite and passed while the text
            # was still live.
            survivors = sorted(
                name for name, body in corpus.items() if normalized in body
            )
            if source.is_file() and normalized in normalize_rule_text(
                source.read_text(encoding="utf-8", errors="replace")
            ):
                survivors = sorted(set(survivors) | {source_path})
            if survivors:
                source_drift.append(rule_id)
                unowned_occurrences[rule_id] = survivors
            markers = item.get("retired_markers")
            if (
                not isinstance(markers, list)
                or not markers
                or any(not str(marker).strip() for marker in markers)
            ):
                invalid_rules.append(rule_id)
                continue
            hits = sorted(
                f"{name}: {marker}"
                for marker in (
                    normalize_rule_text(str(raw)).lower() for raw in markers
                )
                for name, body in active_surfaces.items()
                if marker in body
            )
            if hits:
                retired_marker_hits[rule_id] = hits
            continue

        if not source.is_file():
            invalid_rules.append(rule_id)
            continue
        source_text = normalize_rule_text(source.read_text(encoding="utf-8"))
        if normalized not in source_text:
            source_drift.append(rule_id)

        # A span is a coordinate into the owner file. When it is only prose the
        # ledger cannot say a rule moved, and four kernel spans were one or two
        # bullets off without anything noticing.
        bullet_index = _span_bullet_index(str(item["source_span"]))
        if bullet_index is not None:
            bullets = kernel_bullets(source)
            if not 1 <= bullet_index <= len(bullets):
                span_drift[rule_id] = (
                    f"{source_path} has {len(bullets)} bullets, span names {bullet_index}"
                )
            elif bullets[bullet_index - 1] != normalized:
                span_drift[rule_id] = (
                    f"{source_path} bullet {bullet_index} is a different rule"
                )

        reason = _scan_reason(source_path, rule_text)
        if reason:
            uncovered[rule_id] = reason
            continue
        allowed = {source_path} | {
            str(mirror) for mirror in item.get("allowed_mirrors", [])
        }
        strays = sorted(
            name
            for name, body in corpus.items()
            if name not in allowed and normalized in body
        )
        if strays:
            unowned_occurrences[rule_id] = strays

    # These are the startup policy surfaces for which the ledger claims full
    # ownership. Every top-level rule must map to a registered semantic owner;
    # adding prose without owner/trigger/burden metadata therefore fails closed.
    governed_sources = data.get("governed_policy_sources")
    if not isinstance(governed_sources, list) or any(
        not isinstance(item, str) or not item.strip() for item in governed_sources
    ):
        invalid_policy_sources.append("<governed_policy_sources>")
        governed_sources = []
    for source_path in governed_sources:
        source = source_root / source_path
        if not source.is_file():
            invalid_policy_sources.append(source_path)
            continue
        owned_texts = [
            normalize_rule_text(str(item["rule_text"]))
            for item in rules
            if str(item.get("source_path")) == source_path
            and str(item.get("disposition")) != "delete"
            and set(REQUIRED_RULE_FIELDS) <= set(item)
        ]
        missing = [
            bullet
            for bullet in kernel_bullets(source)
            if bullet not in owned_texts
        ]
        if missing:
            unowned_policy_rules[source_path] = missing

    return {
        "ok": not duplicate_rule_ids
        and not invalid_rules
        and not hash_drift
        and not source_drift
        and not unowned_occurrences
        and not uncovered
        and not unowned_policy_rules
        and not invalid_policy_sources
        and not always_on_obligations
        and not span_drift
        and not retired_marker_hits,
        "ledger_version": data.get("ledger_version"),
        "kernel_id": data.get("kernel_id"),
        "rules": rules,
        "duplicate_rule_ids": duplicate_rule_ids,
        "invalid_rules": sorted(set(invalid_rules)),
        "hash_drift": hash_drift,
        "source_drift": source_drift,
        "unowned_occurrences": unowned_occurrences,
        "unowned_policy_rules": unowned_policy_rules,
        "invalid_policy_sources": sorted(set(invalid_policy_sources)),
        "span_drift": span_drift,
        "retired_marker_hits": retired_marker_hits,
        "uncovered": uncovered,
        "gate_counts": {
            "always_on": trigger_counts["always-on"],
            "triggered": trigger_counts["triggered"],
            "boundary": burden_counts["boundary"],
            "latitude": burden_counts["latitude"],
            "obligation": burden_counts["obligation"],
            "always_on_obligations": len(always_on_obligations),
        },
        "always_on_obligations": sorted(always_on_obligations),
    }


def context_budget_report(
    *,
    launcher_text: str,
    overlay_text: str,
    hook_chars: dict[str, int] | None = None,
    selective_skill_chars: dict[str, int] | None = None,
    memory_index_chars: int = 0,
    catalog_chars: dict[str, int] | None = None,
) -> dict[str, Any]:
    hook_chars = hook_chars or {}
    selective_skill_chars = selective_skill_chars or {}
    catalog_chars = catalog_chars or {}
    layers = {
        "kernel": len(kernel_text()),
        "launcher": len(launcher_text.strip()),
        "model_overlay": len(overlay_text.strip()),
        "hooks": sum(hook_chars.values()),
        "memory_index": memory_index_chars,
        "catalogs": sum(catalog_chars.values()),
        "selective_skills": sum(selective_skill_chars.values()),
    }
    startup = layers["kernel"] + layers["launcher"] + layers["model_overlay"]
    scenario_peak = startup + layers["selective_skills"]
    total = (
        scenario_peak
        + layers["hooks"]
        + layers["memory_index"]
        + layers["catalogs"]
    )
    return {
        "layers": layers,
        "harness_owned_startup_chars": startup,
        "harness_owned_scenario_peak_chars": scenario_peak,
        "total_effective_chars": total,
        "hook_sources": hook_chars,
        "selective_skill_sources": selective_skill_chars,
        "catalog_sources": catalog_chars,
        "budget_violations": [
            name
            for name in ("kernel", "launcher", "model_overlay")
            if layers[name] > LAYER_BUDGETS[name]
        ]
        + [
            f"hook_output:{name}"
            for name, size in hook_chars.items()
            if size > LAYER_BUDGETS["hook_output"]
        ]
        + [
            f"selective_skill:{name}"
            for name, size in selective_skill_chars.items()
            if size > LAYER_BUDGETS["selective_skill"]
        ],
    }
