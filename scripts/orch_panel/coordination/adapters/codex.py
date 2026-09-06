from __future__ import annotations

import hashlib
import json
import queue
import subprocess
import threading
from collections import deque
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


class _RpcFuture:
    def __init__(
        self,
        rpc: _JsonLineRpc,
        request_id: int,
        responses: queue.Queue[dict[str, Any] | None],
    ) -> None:
        self.rpc = rpc
        self.request_id = request_id
        self.responses = responses
        self._done = False
        self._result: dict[str, Any] = {}
        self._error: RuntimeError | None = None

    def result(self) -> dict[str, Any]:
        if not self._done:
            try:
                message = self.responses.get(timeout=self.rpc.timeout)
            except queue.Empty as exc:
                self.rpc._forget_response(self.request_id)
                raise TimeoutError("timed out waiting for codex app-server response") from exc
            self.rpc._forget_response(self.request_id)
            self._done = True
            if message is None:
                self._error = RuntimeError(
                    "codex app-server exited while awaiting response"
                )
            elif "error" in message:
                self._error = RuntimeError(
                    f"codex app-server error: {message['error']}"
                )
            else:
                self._result = message.get("result", {})
        if self._error is not None:
            raise self._error
        return self._result


class _JsonLineRpc:
    def __init__(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None,
        timeout: float,
    ) -> None:
        self.timeout = timeout
        self.process = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=dict(env) if env else None,
        )
        self._incoming: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._pending: deque[dict[str, Any]] = deque()
        self._responses: dict[
            int, queue.Queue[dict[str, Any] | None]
        ] = {}
        self._response_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._next_id = 0
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            request_id = message.get("id")
            if isinstance(request_id, int):
                with self._response_lock:
                    responses = self._responses.get(request_id)
                if responses is not None:
                    responses.put(message)
                    continue
            self._incoming.put(message)
        with self._response_lock:
            response_queues = list(self._responses.values())
        for responses in response_queues:
            responses.put(None)
        self._incoming.put(None)

    def _write(self, payload: dict[str, Any]) -> None:
        if self.process.poll() is not None:
            raise RuntimeError("codex app-server exited before request")
        assert self.process.stdin is not None
        with self._write_lock:
            self.process.stdin.write(
                json.dumps(payload, separators=(",", ":")) + "\n"
            )
            self.process.stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"method": method, "params": params})

    def request_async(self, method: str, params: dict[str, Any]) -> _RpcFuture:
        with self._response_lock:
            self._next_id += 1
            request_id = self._next_id
            responses: queue.Queue[dict[str, Any] | None] = queue.Queue()
            self._responses[request_id] = responses
        try:
            self._write({"method": method, "id": request_id, "params": params})
        except BaseException:
            self._forget_response(request_id)
            raise
        return _RpcFuture(self, request_id, responses)

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return self.request_async(method, params).result()

    def _forget_response(self, request_id: int) -> None:
        with self._response_lock:
            self._responses.pop(request_id, None)

    def prepend_notifications(self, messages: list[dict[str, Any]]) -> None:
        for message in reversed(messages):
            self._pending.appendleft(message)

    def next_notification(self) -> dict[str, Any] | None:
        if self._pending:
            return self._pending.popleft()
        try:
            return self._incoming.get(timeout=self.timeout)
        except queue.Empty as exc:
            raise TimeoutError("timed out waiting for codex app-server event") from exc

    def close(self) -> None:
        if self.process.poll() is None:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=2)
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


class CodexAppServerAdapter:
    def __init__(
        self,
        *,
        command: Sequence[str],
        journal: SessionJournal,
        env: Mapping[str, str] | None = None,
        timeout: float = 5,
    ) -> None:
        self.command = list(command)
        self.journal = journal
        self.env = dict(env or {})
        self.timeout = timeout
        self._rpc: _JsonLineRpc | None = None
        self._initialization: dict[str, Any] = {}
        self._turn_start_futures: dict[str, _RpcFuture] = {}

    def _connect(self) -> _JsonLineRpc:
        if self._rpc is not None and self._rpc.process.poll() is None:
            return self._rpc
        self._rpc = _JsonLineRpc(self.command, env=self.env, timeout=self.timeout)
        self._initialization = self._rpc.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "orchestration_console_compatibility",
                    "title": "Orchestration Console Compatibility Spike",
                    "version": "0.1.0",
                }
            },
        )
        self._rpc.notify("initialized", {})
        return self._rpc

    def _record_native_context(
        self, rpc: _JsonLineRpc, session: RuntimeSession
    ) -> RuntimeSession:
        """Persist one provider-native init checkpoint before the model turn."""
        try:
            status = rpc.request(
                "mcpServerStatus/list", {"detail": "toolsAndAuthOnly"}
            )
        except Exception:
            status = {}
        servers = status.get("data") if isinstance(status.get("data"), list) else []
        prior = self.journal.events("codex", session.runtime_session_id)
        event = RuntimeEvent(
            provider="codex",
            runtime_session_id=session.runtime_session_id,
            cursor=f"{len(prior) + 1:08d}",
            event_id=f"{session.runtime_session_id}:init",
            kind="init",
            payload={
                "mcp_servers": servers,
                "instruction_sources": list(session.instruction_sources),
                "user_agent": self._initialization.get("userAgent", ""),
                "platform_family": self._initialization.get("platformFamily", ""),
                "platform_os": self._initialization.get("platformOs", ""),
            },
        )
        self.journal.append_event(event)
        metadata = dict(session.metadata)
        metadata["mcp_servers"] = servers
        metadata["platform_family"] = self._initialization.get("platformFamily", "")
        return self.journal.replace_session(
            replace(session, cursor=event.cursor, metadata=metadata)
        )

    def preflight(self) -> dict[str, Any]:
        """Prove the app-server handshake without starting a thread or turn."""
        self._connect()
        return dict(self._initialization)

    @staticmethod
    def _instruction_sources(result: dict[str, Any]) -> tuple[str, ...]:
        raw = result.get("instructionSources")
        if raw is None and isinstance(result.get("thread"), dict):
            raw = result["thread"].get("instructionSources")
        return tuple(str(path) for path in (raw or []))

    def _start_turn(
        self, rpc: _JsonLineRpc, session: RuntimeSession, request: DispatchRequest
    ) -> RuntimeSession:
        params: dict[str, Any] = {
            "threadId": session.runtime_session_id,
            "input": [{"type": "text", "text": request.prompt}],
            "cwd": str(request.cwd),
            "approvalPolicy": "never",
            "sandboxPolicy": {"type": "readOnly"},
        }
        if request.model:
            params["model"] = request.model
        if request.reasoning_effort:
            params["effort"] = request.reasoning_effort
        future = rpc.request_async("turn/start", params)
        deferred: list[dict[str, Any]] = []
        turn: dict[str, Any] = {}
        while True:
            message = rpc.next_notification()
            if message is None:
                raise RuntimeError(
                    "codex app-server exited before turn/started notification"
                )
            params_payload = (
                message.get("params")
                if isinstance(message.get("params"), dict)
                else {}
            )
            candidate = (
                params_payload.get("turn")
                if isinstance(params_payload.get("turn"), dict)
                else {}
            )
            if (
                message.get("method") == "turn/started"
                and params_payload.get("threadId") == session.runtime_session_id
                and candidate.get("id")
            ):
                turn = candidate
                break
            deferred.append(message)
        rpc.prepend_notifications(deferred)
        updated = replace(
            session,
            turn_id=str(turn.get("id")) if turn.get("id") else None,
            status=RuntimeStatus.RUNNING,
        )
        updated = self.journal.replace_session(updated)
        assert updated.turn_id is not None
        self._turn_start_futures[updated.turn_id] = future
        return updated

    def start(self, request: DispatchRequest) -> RuntimeSession:
        existing = self.journal.find_session("codex", request.idempotency_key)
        if existing is not None:
            return existing
        rpc = self._connect()
        params: dict[str, Any] = {
            "cwd": str(request.cwd),
            "approvalPolicy": "never",
            "sandbox": "read-only",
            "serviceName": "orchestration_console_compatibility",
        }
        if request.model:
            params["model"] = request.model
        result = rpc.request("thread/start", params)
        thread = result.get("thread") or {}
        thread_id = thread.get("id")
        if not thread_id:
            raise RuntimeError("codex thread/start response omitted thread.id")
        session = self.journal.save_session(
            RuntimeSession(
                provider="codex",
                runtime_session_id=str(thread_id),
                idempotency_key=request.idempotency_key,
                status=RuntimeStatus.STARTING,
                instruction_sources=self._instruction_sources(result),
                metadata={
                    "session_id": thread.get("sessionId"),
                    "cwd": str(request.cwd),
                    "model": request.model,
                    "reasoning_effort": request.reasoning_effort,
                },
            )
        )
        session = self._record_native_context(rpc, session)
        return self._start_turn(rpc, session, request) if request.prompt else session

    def _event_from_notification(
        self, session: RuntimeSession, message: dict[str, Any]
    ) -> RuntimeEvent | None:
        method = message.get("method")
        if not isinstance(method, str):
            return None
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        prior = self.journal.events("codex", session.runtime_session_id)
        cursor = f"{len(prior) + 1:08d}"
        event_id = params.get("eventId")
        if not event_id:
            digest = hashlib.sha256(
                json.dumps(message, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()[:16]
            event_id = f"{session.runtime_session_id}:{cursor}:{digest}"
        if method == "item/agentMessage/delta":
            kind = "delta"
        elif method == "turn/completed":
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            kind = "cancelled" if turn.get("status") == "interrupted" else "completed"
        else:
            kind = method
        return RuntimeEvent(
            provider="codex",
            runtime_session_id=session.runtime_session_id,
            cursor=cursor,
            event_id=str(event_id),
            kind=kind,
            payload=params,
        )

    def stream(
        self, session: RuntimeSession, after: str | None
    ) -> Iterator[RuntimeEvent]:
        for stored in self.journal.events(
            "codex", session.runtime_session_id, after=after
        ):
            yield stored
        rpc = self._rpc
        if rpc is None:
            return
        while True:
            message = rpc.next_notification()
            if message is None:
                return
            event = self._event_from_notification(session, message)
            if event is None or not self.journal.append_event(event):
                continue
            yield event
            if event.kind in {"completed", "cancelled"}:
                turn_payload = (
                    event.payload.get("turn")
                    if isinstance(event.payload.get("turn"), dict)
                    else {}
                )
                turn_id = turn_payload.get("id")
                if turn_id:
                    future = self._turn_start_futures.pop(str(turn_id), None)
                    if future is not None:
                        future.result()
                status = (
                    RuntimeStatus.CANCELLED
                    if event.kind == "cancelled"
                    else RuntimeStatus.COMPLETED
                )
                current = self.journal.get_session(
                    "codex", session.runtime_session_id
                ) or session
                self.journal.replace_session(
                    replace(current, cursor=event.cursor, status=status)
                )
                return

    def resume(
        self, session: RuntimeSession, events: list[SharedEvent]
    ) -> None:
        rpc = self._connect()
        result = rpc.request(
            "thread/resume", {"threadId": session.runtime_session_id}
        )
        current = self.journal.get_session(
            "codex", session.runtime_session_id
        ) or session
        current = self.journal.replace_session(
            replace(
                current,
                instruction_sources=self._instruction_sources(result)
                or current.instruction_sources,
                status=RuntimeStatus.IDLE,
            )
        )
        if events:
            self._start_turn(
                rpc,
                current,
                DispatchRequest(
                    idempotency_key=current.idempotency_key,
                    cwd=Path(str(current.metadata.get("cwd") or ".")),
                    prompt="\n\n".join(event.body_text for event in events),
                    model=str(current.metadata.get("model") or "") or None,
                    reasoning_effort=(
                        str(current.metadata.get("reasoning_effort") or "") or None
                    ),
                ),
            )

    def cancel(self, session: RuntimeSession) -> None:
        current = self.journal.get_session(
            "codex", session.runtime_session_id
        ) or session
        if current.turn_id:
            try:
                self._connect().request(
                    "turn/interrupt",
                    {
                        "threadId": current.runtime_session_id,
                        "turnId": current.turn_id,
                    },
                )
            except RuntimeError as exc:
                if "no active turn to interrupt" not in str(exc):
                    raise
        self.journal.replace_session(
            replace(current, status=RuntimeStatus.CANCELLED)
        )

    def mcp_status(self) -> dict[str, Any]:
        """Read native Codex MCP status without starting a model turn."""
        return self._connect().request(
            "mcpServerStatus/list",
            {"detail": "toolsAndAuthOnly"},
        )

    def inspect(self, session: RuntimeSession) -> RuntimeSession:
        current = self.journal.get_session(
            "codex", session.runtime_session_id
        ) or session
        if current.status not in {
            RuntimeStatus.STARTING,
            RuntimeStatus.RUNNING,
            RuntimeStatus.IDLE,
        }:
            return current
        result = self._connect().request(
            "thread/read",
            {"threadId": current.runtime_session_id, "includeTurns": True},
        )
        thread = result.get("thread") if isinstance(result.get("thread"), dict) else {}
        turns = thread.get("turns") if isinstance(thread.get("turns"), list) else []
        turn = next(
            (
                item
                for item in reversed(turns)
                if isinstance(item, dict)
                and current.turn_id
                and str(item.get("id") or "") == current.turn_id
            ),
            turns[-1] if turns and isinstance(turns[-1], dict) else {},
        )
        raw_turn_status = str(turn.get("status") or "")
        thread_status = (
            thread.get("status") if isinstance(thread.get("status"), dict) else {}
        )
        raw_thread_status = str(thread_status.get("type") or "")
        if raw_turn_status in {"completed"}:
            status = RuntimeStatus.COMPLETED
        elif raw_turn_status in {"interrupted", "cancelled", "canceled"}:
            status = RuntimeStatus.CANCELLED
        elif raw_turn_status in {"failed"} or raw_thread_status == "systemError":
            status = RuntimeStatus.FAILED
        elif raw_turn_status in {"inProgress", "running"} or raw_thread_status == "active":
            status = RuntimeStatus.RUNNING
        else:
            status = RuntimeStatus.IDLE
        metadata = dict(current.metadata)
        metadata["thread_status"] = raw_thread_status
        return self.journal.replace_session(
            replace(current, status=status, metadata=metadata)
        )

    def close(self) -> None:
        if self._rpc is not None:
            self._rpc.close()
            self._rpc = None
            self._initialization = {}
