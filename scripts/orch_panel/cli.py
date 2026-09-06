"""Command-line entry point for the orchestration panel.

Every subcommand is a thin wrapper: it reads arguments, calls one panel
function, and prints. The panel module is imported lazily inside `main` so the
CLI and the panel can import each other without a cycle.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    import orchestration_panel as panel

    parser = argparse.ArgumentParser(description="Codex orchestration dashboard server")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=[
            "serve",
            "docs-context",
            "docs-context-plan",
            "docs-context-sync",
            "docs-diagnose",
            "docs-resolve",
            "docs-persist",
            "docs-signature",
            "claude-aitmpl",
            "claude-agents",
            "claude-agent-install",
            "prompt-get",
            "prompt-check",
            "prompts-sync",
            "benchmark",
            "context-audit",
            "coordination-archive",
            "homes",
        ],
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--status", action="append", choices=["missing", "stale", "future", "floating", "ok"])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--cwd", default=".", help="docs-resolve project directory")
    parser.add_argument("--package", dest="package_name", default=None, help="docs-resolve package name")
    parser.add_argument("--topic", default=None, help="docs-resolve domain/API keyword query")
    parser.add_argument("--ecosystem", choices=["npm", "pip", "cargo", "go", "python"], default=None)
    parser.add_argument("--symbol", default=None, help="docs-signature symbol to look up in the installed package")
    parser.add_argument("--version", default=None, help="docs-resolve explicit package version")
    parser.add_argument("--no-download", action="store_true", help="docs-resolve: do not auto-download registry L1 docs")
    parser.add_argument("--provider", default="", choices=["", *panel.L2_PERSIST_PROVIDERS], help="docs-persist provider that answered: context7 or first-party")
    parser.add_argument("--source", default=None, help="docs-persist source URL the content came from")
    parser.add_argument("--runtime", choices=sorted(panel.PROMPT_CHECK_RUNTIMES), default="codex")
    parser.add_argument("--id", dest="prompt_id", default=None, help="exact prompt card id for prompt-get")
    parser.add_argument("--mode", choices=["launcher", "full"], default="launcher", help="raw prompt card form for prompt-get")
    parser.add_argument("--profile", choices=sorted(panel.PROMPT_CHECK_PROFILES), default=None)
    parser.add_argument("--kind", choices=sorted(panel.PROMPT_CHECK_KINDS), default="worker")
    parser.add_argument("--file", default=None, help="prompt-check input file; omit or use - for stdin")
    parser.add_argument("--agent", dest="agent_name", default=None, help="Claude agent library item")
    parser.add_argument("--scope", choices=["project", "user"], default="project", help="Claude agent install scope")
    parser.add_argument("--overwrite", action="store_true", help="overwrite existing Claude agent target")
    parser.add_argument("--quick", action="store_true", help="benchmark only prompt, overview, repository discovery, and panel freshness")
    parser.add_argument("--confirm", default="", help="exact confirmation token for local recovery actions")
    parser.add_argument(
        "--private-root",
        default=os.environ.get(
            "AGENT_HARNESS_PRIVATE_ROOT",
            str(panel.CONSOLE_DIR / "harness" / "private"),
        ),
        help="private harness root for context-audit (defaults to embedded source)",
    )
    args = parser.parse_args()
    if args.command == "serve":
        panel.serve(args.host, args.port)
        return 0
    if args.command == "homes":
        # The launcher needs the same answer the panel serves, and a second
        # scoring implementation in shell is how the two drifted apart.
        homes = {
            "codex_home": str(panel.codex_home()),
            "codex_asset_home": str(panel.codex_asset_home()),
            "claude_home": str(panel.claude_home()),
            "agents_home": str(panel.agents_home()),
        }
        if args.json:
            print(json.dumps(homes, ensure_ascii=False, indent=2))
        else:
            for key, value in homes.items():
                print(f"{key}={value}")
        return 0
    if args.command == "coordination-archive":
        try:
            archived = panel.coordination_archive_state(confirm=args.confirm)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"Archived local coordination state to {archived}")
        print("Native runtime sessions, Beads issues, and repository artifacts were not deleted.")
        return 0
    if args.command == "prompt-get":
        if not args.prompt_id:
            print("prompt-get requires --id", file=sys.stderr)
            return 2
        try:
            payload = panel.prompt_get_payload(args.prompt_id, args.runtime, args.mode)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["text"])
        return 0
    if args.command == "prompt-check":
        selected_profile = args.profile or ("fable-5.1" if args.runtime == "claude" else "gpt-6-astra")
        payload = panel.prompt_check_payload(
            panel.read_prompt_check_input(args.file),
            args.runtime,
            selected_profile,
            args.kind,
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(panel.prompt_check_text(payload))
        return 0 if payload["ok"] else 1
    if args.command == "prompts-sync":
        from orch_panel.prompts_sync import main as prompts_sync_main

        return prompts_sync_main(["--write"] if args.write else ["--check"])
    if args.command == "benchmark":
        payload = panel.latency_benchmark_payload(args.quick, args.host, args.port)
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else panel.latency_benchmark_text(payload))
        # A budget that always exits 0 is a report, not a gate.
        return 0 if payload["budget_status"] == "pass" else 1
    if args.command == "context-audit":
        if (panel.CONSOLE_DIR / "release-manifest.json").is_file():
            print(
                "context-audit uses internal development evidence, which is not "
                "part of the public release. Use 'harness doctor' for installation health.",
                file=sys.stderr,
            )
            return 2
        from evaluate_thin_context import evaluate

        payload = evaluate(panel.CONSOLE_DIR, Path(args.private_root))
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            state = "pass" if payload["context_size_gate"]["eligible"] else "fail"
            print(f"context-size-audit: {state}")
            for profile in payload["profiles"]:
                startup = min(
                    item["reduction"]["harness_owned_startup"]
                    for item in profile["scenarios"]
                )
                peak = min(
                    item["reduction"]["harness_owned_scenario_peak"]
                    for item in profile["scenarios"]
                )
                print(
                    f"- {profile['runtime']}/{profile['profile']}: "
                    f"startup {startup:.1%}, scenario peak {peak:.1%}"
                )
            print(
                "- behavioral canary: "
                f"{payload['behavioral_gate']['status']}; "
                "production promotion and speed claims not allowed"
            )
            # Size is only half the cost. This is the half the operator feels
            # on every task, so it is reported beside the reductions.
            for name in ("console", "private"):
                counts = (payload["ownership"][name] or {}).get("gate_counts")
                if not counts:
                    continue
                obligations = payload["ownership"][name]["always_on_obligations"]
                print(
                    f"- {name} gates: {counts['always_on']} always-on / "
                    f"{counts['triggered']} triggered; "
                    f"{counts['always_on_obligations']} always-on obligation(s)"
                    + (f": {', '.join(obligations)}" if obligations else "")
                )
        return 0 if payload["context_size_gate"]["eligible"] else 1
    statuses = set(args.status or [])
    if args.command == "docs-context":
        payload = panel.docs_context_payload()
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else panel.docs_context_text(payload))
        return 0
    if args.command == "docs-context-plan":
        payload = panel.docs_context_payload()
        if args.json:
            entries = panel.filtered_sync_entries(payload, statuses, args.limit)
            print(json.dumps({"summary": payload.get("sync_plan", {}).get("summary", {}), "entries": entries}, ensure_ascii=False, indent=2))
        else:
            print(panel.docs_sync_plan_text(payload, statuses, args.limit))
        return 0
    if args.command == "docs-context-sync":
        return panel.run_docs_sync(args.write, statuses, args.limit)
    if args.command == "docs-diagnose":
        payload = panel.docs_diagnostic_payload()
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else panel.docs_diagnostic_text(payload))
        return 0 if payload.get("status") == "ok" else 1
    if args.command == "docs-resolve":
        if not args.package_name or not args.topic:
            print("docs-resolve requires --package and --topic", file=sys.stderr)
            return 2
        payload = panel.resolve_docs(
            cwd=Path(args.cwd),
            package_name=args.package_name,
            topic=args.topic,
            ecosystem=args.ecosystem,
            version=args.version,
            allow_download=not args.no_download,
        )
        panel.record_docs_resolution(payload)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(panel.docs_resolve_text(payload))
        return 0 if payload.get("status") not in {"blocked", "provider-error"} else 1
    if args.command == "docs-signature":
        if not args.package_name or not args.symbol:
            print("docs-signature requires --package and --symbol", file=sys.stderr)
            return 2
        ecosystem = args.ecosystem
        if ecosystem in {"pip", "python"}:
            ecosystem = "python"
        elif ecosystem not in {"npm", None}:
            print(f"docs-signature does not support --ecosystem {ecosystem}", file=sys.stderr)
            return 2
        payload = panel.resolve_installed_signature(
            cwd=Path(args.cwd),
            package=args.package_name,
            symbol=args.symbol,
            ecosystem=ecosystem,
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(panel.signature_text(payload))
        return 0 if payload.get("ok") else 1
    if args.command == "docs-persist":
        if not args.package_name or not args.version or not args.source:
            print(
                "docs-persist requires --package, --version, and --source",
                file=sys.stderr,
            )
            return 2
        if not args.file and sys.stdin.isatty():
            print(
                "docs-persist reads the answer from stdin: "
                "add `< answer.md` or `--file <path>`",
                file=sys.stderr,
            )
            return 2
        try:
            content = panel.read_prompt_check_input(args.file)
        except OSError as error:
            print(f"docs-persist could not read the answer: {error}", file=sys.stderr)
            return 2
        payload = panel.persist_l2_docs(
            package_name=args.package_name,
            version=args.version,
            provider=args.provider,
            topic=args.topic or "",
            results=[
                {
                    "title": args.topic or args.package_name,
                    "source": args.source,
                    "content": content,
                }
            ],
        )
        panel.record_docs_persist(payload, args.topic or "", args.ecosystem or "")
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            state = "ok" if payload["ok"] else f"skipped: {payload['skipped']}"
            print(f"docs-persist {payload['package']}@{payload['version']}: {state}")
        # Already-covered is the intended no-op, not a failure: reporting it as
        # one would push a caller back into another network round trip.
        if payload["ok"] or payload["skipped"].startswith("L1 already covers"):
            return 0
        return 1
    if args.command == "claude-aitmpl":
        payload = panel.claude_aitmpl_summary()
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else panel.claude_aitmpl_text(payload))
        return 0
    if args.command == "claude-agents":
        payload = panel.claude_agent_library_payload()
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else panel.claude_agent_library_text(payload))
        return 0
    if args.command == "claude-agent-install":
        if not args.agent_name:
            print("claude-agent-install requires --agent", file=sys.stderr)
            return 2
        result = panel.install_claude_agent_from_library(args.agent_name, scope=args.scope, overwrite=args.overwrite)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else panel.claude_agent_install_text(result))
        return 0
    return 0
