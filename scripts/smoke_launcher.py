#!/usr/bin/env python3
"""Run the launcher from a temporary clone-like path and verify HTTP payloads."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IGNORED_COPY_DIRS = {".beads", ".git", ".venv", "state", "stitch", "__pycache__"}
CLAUDE_COMMON_MARKER = "Claude common overlay"
CLAUDE_FABLE_MARKER = "Claude profile overlay: Fable 5.1"
CLAUDE_OPUS_MARKER = "Claude profile overlay: Opus 5"
CLAUDE_OVERLAY_MARKERS = [CLAUDE_COMMON_MARKER, CLAUDE_FABLE_MARKER, CLAUDE_OPUS_MARKER]
CODEX_COMMON_MARKER = "Codex common overlay"
CODEX_ASTRA_MARKER = "Codex profile overlay: GPT-6 Astra"
CODEX_OVERLAY_MARKERS = [CODEX_COMMON_MARKER, CODEX_ASTRA_MARKER]
ALL_OVERLAY_MARKERS = CLAUDE_OVERLAY_MARKERS + CODEX_OVERLAY_MARKERS
SERVER_START_TIMEOUT_SECONDS = 30.0


def provision_locked_env(project: Path) -> Path:
    """Build the panel's runtime environment the way a fresh restore does.

    The smoke must exercise the supported install path, so it runs `uv sync`
    inside the clone instead of borrowing the source checkout's `.venv`.
    """
    if shutil.which("uv") is None:
        raise RuntimeError(
            "uv is required to provision the panel runtime; see 'Restore' in README.md"
        )
    result = subprocess.run(
        ["uv", "sync", "--frozen", "--no-progress"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"uv sync failed in {project}:\n{result.stderr.strip()}")
    interpreter = project / ".venv" / "bin" / "python"
    if not interpreter.exists():
        raise RuntimeError(f"uv sync did not create {interpreter}")
    return interpreter


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in IGNORED_COPY_DIRS:
            ignored.add(name)
        elif name.endswith(".pyc"):
            ignored.add(name)
    return ignored


def fetch_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read())


def prompt_supports_runtime(prompt: dict, runtime: str) -> bool:
    runtimes = prompt.get("runtimes") or []
    return "shared" in runtimes or runtime in runtimes


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
            raise RuntimeError(f"{runtime} unexpectedly selected profile: {active_profile!r}")
    elif (active_profile or {}).get("id") != profile_id:
        raise RuntimeError(f"{runtime}/{profile_id} profile not selected")

    checked_supported = 0
    for prompt in payload.get("prompts") or []:
        text = prompt.get("text") or ""
        prompt_id = prompt.get("id")
        if profile_id is None:
            if prompt.get("profile") is not None:
                raise RuntimeError(f"{runtime} prompt {prompt_id} unexpectedly has profile metadata")
            for marker in ALL_OVERLAY_MARKERS:
                if marker in text:
                    raise RuntimeError(f"{runtime} prompt {prompt_id} unexpectedly contains {marker}")
            continue

        if prompt_supports_runtime(prompt, runtime):
            checked_supported += 1
            for marker in required_markers:
                if marker not in text:
                    raise RuntimeError(f"{runtime}/{profile_id} prompt {prompt_id} missing {marker}")
            for marker in forbidden_markers:
                if marker in text:
                    raise RuntimeError(f"{runtime}/{profile_id} prompt {prompt_id} unexpectedly contains {marker}")
        else:
            for marker in ALL_OVERLAY_MARKERS:
                if marker in text:
                    raise RuntimeError(f"{runtime}/{profile_id} prompt {prompt_id} should not contain {marker}")

    if profile_id is not None and checked_supported == 0:
        raise RuntimeError(f"{runtime}/{profile_id} had no runtime-supported prompts to check")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="orch-prompts-smoke-"))
    port = free_port()
    proc: subprocess.Popen[str] | None = None
    last_error: Exception | None = None
    try:
        clone = tmp / "orchestration-console"
        shutil.copytree(ROOT, clone, ignore=ignore, symlinks=True)
        env = os.environ.copy()
        env["ORCH_PROMPTS_PORT"] = str(port)
        # Provision the clone itself and set no ORCH_PANEL_PYTHON, so the
        # launcher has to resolve the interpreter a restored checkout would get.
        env.pop("ORCH_PANEL_PYTHON", None)
        provision_locked_env(clone)
        log_path = tmp / "server.log"
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                [str(clone / "scripts" / "start_console.sh"), "serve"],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

        startup_deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
        while time.monotonic() < startup_deadline:
            try:
                fetch_json(f"http://127.0.0.1:{port}/api/health")
                payload = fetch_json(f"http://127.0.0.1:{port}/api/prompts")
                if payload.get("source") != "manifest":
                    raise RuntimeError(f"unexpected prompt source: {payload.get('source')!r}")
                prompts = payload.get("prompts") or []
                expected_count = len(json.loads((clone / "prompts" / "manifest.json").read_text(encoding="utf-8")).get("prompts") or [])
                if len(prompts) != expected_count:
                    raise RuntimeError(f"unexpected prompt count: {len(prompts)} != {expected_count}")
                codex_payload = fetch_json(f"http://127.0.0.1:{port}/api/prompts?runtime=codex", timeout=8.0)
                assert_overlay_state(
                    codex_payload,
                    runtime="codex",
                    profile_id="gpt-6-astra",
                    required_markers=[CODEX_ASTRA_MARKER],
                    forbidden_markers=[CODEX_COMMON_MARKER] + CLAUDE_OVERLAY_MARKERS,
                )
                fable_payload = fetch_json(f"http://127.0.0.1:{port}/api/prompts?runtime=claude&profile=fable-5.1", timeout=8.0)
                assert_overlay_state(
                    fable_payload,
                    runtime="claude",
                    profile_id="fable-5.1",
                    required_markers=[CLAUDE_FABLE_MARKER],
                    forbidden_markers=[CLAUDE_COMMON_MARKER, CLAUDE_OPUS_MARKER] + CODEX_OVERLAY_MARKERS,
                )
                opus_payload = fetch_json(f"http://127.0.0.1:{port}/api/prompts?runtime=claude&profile=opus-5", timeout=8.0)
                assert_overlay_state(
                    opus_payload,
                    runtime="claude",
                    profile_id="opus-5",
                    required_markers=[CLAUDE_OPUS_MARKER],
                    forbidden_markers=[CLAUDE_COMMON_MARKER, CLAUDE_FABLE_MARKER] + CODEX_OVERLAY_MARKERS,
                )
                for removed_profile in ("universal", "opus-4.8"):
                    try:
                        fetch_json(
                            f"http://127.0.0.1:{port}/api/prompts?runtime=claude&profile={removed_profile}",
                            timeout=8.0,
                        )
                    except Exception:
                        pass
                    else:
                        raise RuntimeError(
                            f"removed Claude profile still resolves: {removed_profile}"
                        )
                overview = fetch_json(f"http://127.0.0.1:{port}/api/overview", timeout=8.0)
                runtime_ids = {item.get("id") for item in overview.get("runtimes", {}).get("items", [])}
                if not {"codex", "claude"}.issubset(runtime_ids):
                    raise RuntimeError(f"missing runtimes: {runtime_ids}")
                telemetry = fetch_json(f"http://127.0.0.1:{port}/api/telemetry", timeout=8.0)
                telemetry_keys = {"available", "generated_at", "repo_count", "sidecar_count", "stage_count", "repos", "stages", "totals", "warnings"}
                if not telemetry_keys.issubset(telemetry):
                    raise RuntimeError("telemetry endpoint incomplete")
                if not isinstance(telemetry.get("available"), bool) or not isinstance(telemetry.get("stages"), list):
                    raise RuntimeError("telemetry endpoint has invalid contract types")
                delegation_total_keys = {
                    "subagent_count",
                    "agent_wall_seconds",
                    "coordination_seconds",
                    "delegation_decisions",
                    "delegation_reasons",
                }
                if not delegation_total_keys.issubset(telemetry.get("totals") or {}):
                    raise RuntimeError("telemetry delegation contract incomplete")
                claude = fetch_json(f"http://127.0.0.1:{port}/api/runtime/claude", timeout=20.0)
                if "settings" not in claude or "vscode_wsl" not in claude:
                    raise RuntimeError("claude runtime payload incomplete")
                print(f"smoke_launcher: ok ({len(prompts)} prompts, source=manifest, port={port})")
                return 0
            except Exception as exc:
                last_error = exc
                if proc.poll() is not None:
                    break
                time.sleep(0.2)

        if log_path.exists():
            print(log_path.read_text(encoding="utf-8", errors="replace"))
        if last_error is not None:
            print(f"smoke_launcher: last error: {last_error}")
        print("smoke_launcher: server did not become healthy")
        return 1
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
