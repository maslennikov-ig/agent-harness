"""Translate agent traffic into the shared visible envelope.

Two directions meet here:

- inbound, an official A2A message carrying coordination metadata becomes one
  `SharedEvent` in the local store;
- outbound, a runtime adapter event becomes at most one `SharedEvent`.

Both directions drop hidden reasoning. The panel projects visible operational
content — questions, answers, decisions, blockers, checkpoints, results, and
review findings — and nothing else ever reaches the database.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Role

from orch_panel.coordination.contracts import RuntimeEvent
from orch_panel.coordination.models import SharedEvent
from orch_panel.coordination.safety import redact_sensitive_text
from orch_panel.coordination.store import CoordinationStore, StoreError

COORDINATION_METADATA_KEY = "coordination"

# Reasoning is never shared history, whatever the provider calls it.
HIDDEN_KINDS = frozenset(
    {
        "reasoning",
        "thinking",
        "item/reasoning",
        "item/reasoning/delta",
        "item/reasoning/summary",
        "item/reasoning/summaryDelta",
    }
)
HIDDEN_CONTENT_BLOCKS = frozenset({"thinking", "redacted_thinking"})
# Increments whose complete text arrives again in a later event. Storing them
# would duplicate every answer once per token batch.
INCREMENTAL_KINDS = frozenset({"delta", "item/agentMessage/delta", "stream_event"})

_PROVIDER_AUTHORS = {"codex": "codex", "claude": "claude"}
_KIND_TO_EVENT_KIND = {
    "message": "checkpoint",
    "item/completed": "checkpoint",
    "completed": "result",
    "failed": "blocker",
    "cancelled": "checkpoint",
}


def visible_text(payload: Any) -> str:
    """Extract only the text a person is meant to read.

    Assistant content blocks are filtered by type, so a `thinking` or
    `redacted_thinking` block cannot leak into visible history even when the
    provider ships it in the same message as the answer.
    """
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            parts = [
                str(block.get("text") or "")
                for block in content
                if isinstance(block, dict)
                and block.get("type") not in HIDDEN_CONTENT_BLOCKS
                and block.get("text")
            ]
            return "\n".join(part for part in parts if part).strip()
        if isinstance(content, str):
            return content.strip()
    for key in ("result", "delta", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    item = payload.get("item")
    if isinstance(item, dict):
        return visible_text(item)
    return ""


def _native_context_summary(payload: dict[str, Any]) -> str:
    """Summarise the runtime's own context without copying its inventory.

    The counts report which native MCP servers and tools the runtime exposed,
    while the raw lists stay in the runtime session where they belong.
    """
    tools = payload.get("tools")
    servers = payload.get("mcp_servers")
    plugins = payload.get("plugins")
    parts = ["runtime session ready"]
    if isinstance(tools, list):
        parts.append(f"{len(tools)} native tools")
    if isinstance(servers, list):
        parts.append(f"{len(servers)} MCP servers")
    if isinstance(plugins, list):
        parts.append(f"{len(plugins)} plugins")
    return "; ".join(parts)


def shared_event_from_runtime_event(
    event: RuntimeEvent,
    *,
    project_id: str,
    epic_id: str,
    dispatch_id: str,
    beads_issue_id: str | None = None,
) -> SharedEvent | None:
    """Translate one runtime event, or return None when it is not shared history.

    The idempotency key is derived from the native event id, so replaying a
    stream after a restart resolves to the event that is already stored.
    """
    if event.kind in HIDDEN_KINDS or event.kind in INCREMENTAL_KINDS:
        return None
    payload = event.payload if isinstance(event.payload, dict) else {}
    if event.kind == "init":
        body = _native_context_summary(payload)
        event_kind = "checkpoint"
    else:
        body = visible_text(payload)
        event_kind = _KIND_TO_EVENT_KIND.get(event.kind, "checkpoint")
        if not body:
            return None
    return SharedEvent(
        project_id=project_id,
        epic_id=epic_id,
        beads_issue_id=beads_issue_id,
        dispatch_id=dispatch_id,
        runtime_session_id=event.runtime_session_id,
        author_kind=_PROVIDER_AUTHORS.get(event.provider, "system"),
        event_kind=event_kind,
        body_text=redact_sensitive_text(body),
        idempotency_key=f"{dispatch_id}:{event.provider}:{event.event_id}",
    )


class CoordinationAgentExecutor(AgentExecutor):
    """Official A2A entry point into the shared stream.

    A message carrying `coordination` metadata is appended to the local store.
    A message without it keeps the bounded echo behavior, so the compatibility
    contract does not change when coordination is enabled.
    """

    def __init__(self, *, store_provider: Callable[[], CoordinationStore | None]) -> None:
        self.store_provider = store_provider

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(
            new_text_message(
                self._reply(context),
                context_id=context.context_id,
                role=Role.ROLE_AGENT,
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        return None

    def _reply(self, context: RequestContext) -> str:
        text = context.get_user_input()
        scope = (context.metadata or {}).get(COORDINATION_METADATA_KEY)
        if not isinstance(scope, dict) or not scope:
            return f"echo: {text}"
        store = self.store_provider()
        if store is None:
            return "coordination is disabled on this panel"
        epic_id = str(scope.get("epic_id") or "")
        project_id = str(scope.get("project_id") or "")
        if not epic_id or store.epic(epic_id) is None:
            return f"unknown epic: {epic_id!r}"
        try:
            stored = store.append_event(
                SharedEvent(
                    project_id=project_id,
                    epic_id=epic_id,
                    beads_issue_id=scope.get("beads_issue_id") or None,
                    dispatch_id=scope.get("dispatch_id") or None,
                    author_kind=str(scope.get("author_kind") or "system"),
                    event_kind=str(scope.get("event_kind") or "message"),
                    body_text=text,
                    idempotency_key=str(scope.get("idempotency_key") or f"a2a:{context.context_id}"),
                )
            )
        except StoreError as exc:
            return f"rejected: {exc}"
        return f"stored {stored.event_id} at seq {stored.seq}"
