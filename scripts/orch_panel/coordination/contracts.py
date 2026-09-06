from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path


class RuntimeStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class DispatchRequest:
    idempotency_key: str
    cwd: Path
    prompt: str
    model: str | None = None
    reasoning_effort: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SharedEvent:
    event_id: str
    body_text: str


@dataclass(frozen=True)
class RuntimeSession:
    provider: str
    runtime_session_id: str
    idempotency_key: str
    status: RuntimeStatus
    turn_id: str | None = None
    cursor: str | None = None
    instruction_sources: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeEvent:
    provider: str
    runtime_session_id: str
    cursor: str
    event_id: str
    kind: str
    payload: dict[str, object]


class SessionJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._sessions = self._load_sessions()
        self._events = self._load_events()

    def _load_payload(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _load_sessions(self) -> list[RuntimeSession]:
        payload = self._load_payload()
        return [
            RuntimeSession(
                provider=item["provider"],
                runtime_session_id=item["runtime_session_id"],
                idempotency_key=item["idempotency_key"],
                status=RuntimeStatus(item["status"]),
                turn_id=item.get("turn_id"),
                cursor=item.get("cursor"),
                instruction_sources=tuple(item.get("instruction_sources", [])),
                metadata=item.get("metadata", {}),
            )
            for item in payload.get("sessions", [])
        ]

    def _load_events(self) -> list[RuntimeEvent]:
        payload = self._load_payload()
        return [
            RuntimeEvent(
                provider=item["provider"],
                runtime_session_id=item["runtime_session_id"],
                cursor=item["cursor"],
                event_id=item["event_id"],
                kind=item["kind"],
                payload=item["payload"],
            )
            for item in payload.get("events", [])
        ]

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": "coordination-compatibility/v1",
                    "sessions": [asdict(session) for session in self._sessions],
                    "events": [asdict(event) for event in self._events],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def save_session(self, session: RuntimeSession) -> RuntimeSession:
        for existing in self._sessions:
            if (
                existing.provider == session.provider
                and existing.idempotency_key == session.idempotency_key
            ):
                return existing
        self._sessions.append(session)
        self._write()
        return session

    def sessions(self) -> list[RuntimeSession]:
        return list(self._sessions)

    def find_session(
        self, provider: str, idempotency_key: str
    ) -> RuntimeSession | None:
        return next(
            (
                session
                for session in self._sessions
                if session.provider == provider
                and session.idempotency_key == idempotency_key
            ),
            None,
        )

    def get_session(
        self, provider: str, runtime_session_id: str
    ) -> RuntimeSession | None:
        return next(
            (
                session
                for session in self._sessions
                if session.provider == provider
                and session.runtime_session_id == runtime_session_id
            ),
            None,
        )

    def replace_session(self, session: RuntimeSession) -> RuntimeSession:
        for index, existing in enumerate(self._sessions):
            if (
                existing.provider == session.provider
                and existing.runtime_session_id == session.runtime_session_id
            ):
                self._sessions[index] = session
                self._write()
                return session
        return self.save_session(session)

    def append_event(self, event: RuntimeEvent) -> bool:
        if any(
            existing.provider == event.provider
            and existing.runtime_session_id == event.runtime_session_id
            and existing.event_id == event.event_id
            for existing in self._events
        ):
            return False
        self._events.append(event)
        self._write()
        return True

    def events(
        self,
        provider: str,
        runtime_session_id: str,
        *,
        after: str | None = None,
    ) -> list[RuntimeEvent]:
        return [
            event
            for event in self._events
            if event.provider == provider
            and event.runtime_session_id == runtime_session_id
            and (after is None or event.cursor > after)
        ]
