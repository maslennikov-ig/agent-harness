"""Provider-neutral coordination records shared by the store, broker, and API.

These types describe *visible* project history only. Hidden runtime reasoning
never becomes a `SharedEvent`; the gateway drops it before it reaches the store.

`SharedEvent` here is the durable coordination envelope. It is deliberately
distinct from the much narrower `contracts.SharedEvent` that Task 0's runtime
adapters accept as resume input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

# Who produced a visible event. `system` is the panel itself, never a model.
AUTHOR_KINDS = frozenset({"user", "codex", "claude", "system"})

# The visible-content allowlist from the plan. Anything outside it — reasoning,
# raw tool traffic, provider bookkeeping — is not shared history.
EVENT_KINDS = frozenset(
    {
        "message",
        "question",
        "answer",
        "decision",
        "blocker",
        "checkpoint",
        "result",
        "review",
    }
)

DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DispatchState(StrEnum):
    """One agent dispatch, following the plan's lifecycle diagram."""

    DRAFT = "draft"
    AWAITING_START = "awaiting_start"
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    AWAITING_REVIEW = "awaiting_review"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    ACCEPTED = "accepted"
    FAILED = "failed"


# Terminal states have no outgoing edge except the documented Blocked recovery.
_TRANSITIONS: dict[DispatchState, frozenset[DispatchState]] = {
    DispatchState.DRAFT: frozenset({DispatchState.AWAITING_START, DispatchState.CANCELLED}),
    DispatchState.AWAITING_START: frozenset({DispatchState.RUNNING, DispatchState.CANCELLED}),
    DispatchState.RUNNING: frozenset(
        {
            DispatchState.NEEDS_INPUT,
            DispatchState.AWAITING_REVIEW,
            DispatchState.BLOCKED,
            DispatchState.CANCELLED,
            DispatchState.FAILED,
        }
    ),
    DispatchState.NEEDS_INPUT: frozenset({DispatchState.RUNNING, DispatchState.CANCELLED}),
    # Acceptance itself is Task 3 work; the edge exists so the state machine is
    # one table rather than two that can drift.
    DispatchState.AWAITING_REVIEW: frozenset(
        {DispatchState.RUNNING, DispatchState.ACCEPTED, DispatchState.BLOCKED}
    ),
    DispatchState.BLOCKED: frozenset({DispatchState.RUNNING, DispatchState.CANCELLED}),
    DispatchState.CANCELLED: frozenset(),
    DispatchState.ACCEPTED: frozenset(),
    DispatchState.FAILED: frozenset(),
}

# A turn is in flight only in these two states. `awaiting_review` means the run
# already finished and is waiting for a judge, so it must not block the next
# dispatch on the same runtime.
ACTIVE_DISPATCH_STATES = frozenset({DispatchState.RUNNING, DispatchState.NEEDS_INPUT})


def allowed_transition(current: DispatchState, target: DispatchState) -> bool:
    """Return whether the lifecycle permits `current -> target`.

    A no-op transition is allowed so an idempotent replay of the same update
    does not have to special-case itself at every call site.
    """
    if current == target:
        return True
    return target in _TRANSITIONS[current]


@dataclass(frozen=True)
class ArtifactRef:
    """A pointer into the worktree, never a copy of the document itself."""

    path: str
    digest: str
    media_type: str = "text/plain"


@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    repo_path: str
    created_at: str = ""


@dataclass(frozen=True)
class Epic:
    epic_id: str
    project_id: str
    title: str
    beads_issue_id: str | None = None
    created_at: str = ""
    # Where the work came from: "github", "beads", or empty for an idea typed
    # straight into the panel.
    source_kind: str = ""
    source_ref: str = ""
    source_url: str = ""


@dataclass(frozen=True)
class SharedEvent:
    """One visible entry in the append-only project history."""

    project_id: str
    epic_id: str
    author_kind: str
    event_kind: str
    body_text: str
    idempotency_key: str
    beads_issue_id: str | None = None
    dispatch_id: str | None = None
    runtime_session_id: str | None = None
    artifact_refs: tuple[ArtifactRef, ...] = ()
    reply_to: str | None = None
    event_id: str = ""
    # Assigned by the store. It is the shared order and the SSE cursor.
    seq: int = 0
    created_at: str = ""


@dataclass(frozen=True)
class Dispatch:
    """One agent run. `dispatch_id` is an A2A task, not a Beads issue."""

    dispatch_id: str
    project_id: str
    epic_id: str
    provider: str
    state: DispatchState
    idempotency_key: str
    beads_issue_id: str | None = None
    runtime_session_id: str | None = None
    write_zone: str = ""
    prompt_card_id: str = ""
    prompt_digest: str = ""
    detail: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanningArtifact:
    """An accepted specification or plan, linked to an epic by path and digest.

    The panel stores the pointer only. Git owns the text, so the digest is what
    says which revision the epic actually accepted.
    """

    project_id: str
    epic_id: str
    kind: str
    path: str
    digest: str
    beads_issue_id: str | None = None
    registered_at: str = ""
