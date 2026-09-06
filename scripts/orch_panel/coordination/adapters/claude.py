from __future__ import annotations

import hashlib
import json
import queue
import subprocess
import threading
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from orch_panel.coordination.contracts import (
    DispatchRequest,
    RuntimeEvent,
    RuntimeSession,
    RuntimeStatus,
    SessionJournal,
    SharedEvent,
)


# Built-in tools a read-only turn must not even see. Naming them bare removes
# them from context; MCP servers are untouched and keep their own tools.
READ_ONLY_DENIED_TOOLS: tuple[str, ...] = ("Edit", "Write", "NotebookEdit")


class _ClaudeTurn:
    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None,
        prompt: str,
    ) -> None:
        self.process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env=dict(env) if env else None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.incoming: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        self.reader.start()
        # The prompt goes down stdin, never argv: a composed handoff carries the
        # task text, and argv is world-readable in `ps` and process listings.
        # The reader is already running, so a chatty first turn cannot fill the
        # stdout pipe while this write is still in flight.
        if self.process.stdin is not None:
            try:
                self.process.stdin.write(prompt)
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    self.process.stdin.close()
                except OSError:
                    pass

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                self.incoming.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        self.incoming.put(None)

    def next_event(self, timeout: float) -> dict[str, Any] | None:
        try:
            return self.incoming.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("timed out waiting for Claude CLI stream event") from exc

    def finish(self, *, terminate: bool = False) -> None:
        if terminate and self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


class ClaudeCliAdapter:
    def __init__(
        self,
        *,
        command: Sequence[str],
        journal: SessionJournal,
        env: Mapping[str, str] | None = None,
        timeout: float = 10,
    ) -> None:
        self.command = list(command)
        self.journal = journal
        self.env = dict(env or {})
        self.timeout = timeout
        self._active: _ClaudeTurn | None = None

    def launch_args(
        self,
        session: RuntimeSession,
        *,
        resume: bool,
    ) -> list[str]:
        """Build one turn's argv, read-only when the session is a judge.

        The prompt is not here: `-p` with no argument reads it from stdin, so
        the composed handoff never appears in a process listing.

        Telling a judge in its prompt not to write leaves every native write
        tool in its hands, so the restriction has to be in the invocation. Two
        first-party controls carry it for Claude Code 2.1.227:

        - `--permission-mode plan`, the documented read-only mode: Claude reads
          files and explores, but "does not edit your source" and edits stay
          blocked until a plan is approved. There is no approver in a `-p`
          session, so they stay blocked for the whole turn.
        - `--disallowedTools Edit Write NotebookEdit`, where a bare tool name
          removes the tool from context rather than prompting for it.

        Nothing here touches MCP or instruction loading: no `--strict-mcp-config`,
        no `--tools` allowlist that would drop native servers, and no
        permission bypass. The judge keeps the runtime's own configuration.
        """
        args = [
            *self.command,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        if resume:
            args.extend(["--resume", session.runtime_session_id])
        else:
            args.extend(["--session-id", session.runtime_session_id])
        model = str(session.metadata.get("model") or "")
        if model:
            args.extend(["--model", model])
        effort = str(session.metadata.get("reasoning_effort") or "")
        if effort:
            args.extend(["--effort", effort])
        if session.metadata.get("read_only"):
            # Last, because `--disallowedTools` is variadic and would otherwise
            # swallow the flag that follows it.
            args.extend(["--permission-mode", "plan", "--disallowedTools", *READ_ONLY_DENIED_TOOLS])
        return args

    def _launch(
        self,
        session: RuntimeSession,
        *,
        prompt: str,
        resume: bool,
    ) -> None:
        if self._active is not None and self._active.process.poll() is None:
            raise RuntimeError("Claude session already has an active turn")
        args = self.launch_args(session, resume=resume)
        cwd = Path(str(session.metadata.get("cwd") or "."))
        self._active = _ClaudeTurn(args, cwd=cwd, env=self.env, prompt=prompt)

    def start(self, request: DispatchRequest) -> RuntimeSession:
        existing = self.journal.find_session("claude", request.idempotency_key)
        if existing is not None:
            return existing
        session = self.journal.save_session(
            RuntimeSession(
                provider="claude",
                runtime_session_id=str(uuid.uuid4()),
                idempotency_key=request.idempotency_key,
                status=RuntimeStatus.RUNNING,
                metadata={
                    "cwd": str(request.cwd),
                    "native_config": True,
                    "model": request.model,
                    "reasoning_effort": request.reasoning_effort,
                    # Carried on the session so a resumed turn cannot quietly
                    # regain the write tools the first turn was denied.
                    "read_only": bool(request.metadata.get("read_only")),
                },
            )
        )
        self._launch(session, prompt=request.prompt, resume=False)
        return session

    def resume(
        self, session: RuntimeSession, events: list[SharedEvent]
    ) -> None:
        current = self.journal.get_session(
            "claude", session.runtime_session_id
        ) or session
        prompt = "\n\n".join(event.body_text for event in events)
        if not prompt:
            return
        current = self.journal.replace_session(
            replace(current, status=RuntimeStatus.RUNNING)
        )
        self._launch(current, prompt=prompt, resume=True)

    def _event_from_message(
        self, session: RuntimeSession, message: dict[str, Any]
    ) -> RuntimeEvent:
        prior = self.journal.events("claude", session.runtime_session_id)
        cursor = f"{len(prior) + 1:08d}"
        message_type = str(message.get("type") or "event")
        subtype = str(message.get("subtype") or "")
        if message_type == "system" and subtype == "init":
            kind = "init"
        elif message_type == "assistant":
            kind = "message"
        elif message_type == "result" and subtype == "success":
            kind = "completed"
        elif message_type == "result":
            kind = "failed"
        else:
            kind = message_type
        digest = hashlib.sha256(
            json.dumps(message, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        return RuntimeEvent(
            provider="claude",
            runtime_session_id=session.runtime_session_id,
            cursor=cursor,
            event_id=f"{session.runtime_session_id}:{cursor}:{digest}",
            kind=kind,
            payload=message,
        )

    def stream(
        self, session: RuntimeSession, after: str | None
    ) -> Iterator[RuntimeEvent]:
        for stored in self.journal.events(
            "claude", session.runtime_session_id, after=after
        ):
            yield stored
        active = self._active
        if active is None:
            return
        while True:
            message = active.next_event(self.timeout)
            if message is None:
                current = self.inspect(session)
                if current.status == RuntimeStatus.RUNNING:
                    self.journal.replace_session(
                        replace(current, status=RuntimeStatus.FAILED)
                    )
                active.finish()
                self._active = None
                return
            event = self._event_from_message(session, message)
            if not self.journal.append_event(event):
                continue
            current = self.inspect(session)
            if event.kind == "init":
                metadata = dict(current.metadata)
                for key in ("cwd", "tools", "mcp_servers", "plugins"):
                    if key in message:
                        metadata[key] = message[key]
                self.journal.replace_session(
                    replace(current, cursor=event.cursor, metadata=metadata)
                )
            elif event.kind in {"completed", "failed"}:
                status = (
                    RuntimeStatus.COMPLETED
                    if event.kind == "completed"
                    else RuntimeStatus.FAILED
                )
                self.journal.replace_session(
                    replace(current, cursor=event.cursor, status=status)
                )
            yield event
            if event.kind in {"completed", "failed"}:
                active.finish()
                self._active = None
                return

    def cancel(self, session: RuntimeSession) -> None:
        if self._active is not None:
            self._active.finish(terminate=True)
            self._active = None
        current = self.journal.get_session(
            "claude", session.runtime_session_id
        ) or session
        self.journal.replace_session(
            replace(current, status=RuntimeStatus.CANCELLED)
        )

    def inspect(self, session: RuntimeSession) -> RuntimeSession:
        current = self.journal.get_session(
            "claude", session.runtime_session_id
        ) or session
        # Claude Code is a per-turn local process. A new adapter has no process
        # it can safely inspect or attach to, so a persisted in-flight status is
        # stale after restart. Mark it failed without invoking `--resume`, which
        # would open a new paid model turn.
        if self._active is None and current.status in {
            RuntimeStatus.STARTING,
            RuntimeStatus.RUNNING,
        }:
            metadata = dict(current.metadata)
            metadata["recovery"] = "local Claude CLI process is no longer attached"
            current = self.journal.replace_session(
                replace(current, status=RuntimeStatus.FAILED, metadata=metadata)
            )
        return current

    def close(self) -> None:
        if self._active is not None:
            self._active.finish(terminate=True)
            self._active = None
