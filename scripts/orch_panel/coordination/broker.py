"""Routing between the visible stream and one runtime turn at a time.

The broker owns the coordination invariants the plan refuses to leave to a
prompt: one executor per write zone, one active turn per runtime session,
idempotent dispatch, and an explicit user action before any model call starts.

It owns neither workflow policy nor task truth. Beads still decides what a task
is, the harness still decides how the runtime works, and the runtime adapters
from Task 0 still own the provider protocols.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from orch_panel.context_policy import compose_dispatch_handoff
from orch_panel.coordination.a2a_gateway import (
    HIDDEN_KINDS,
    INCREMENTAL_KINDS,
    shared_event_from_runtime_event,
    visible_text,
)
from orch_panel.coordination.contracts import DispatchRequest, RuntimeStatus, SessionJournal
from orch_panel.coordination.contracts import SharedEvent as RuntimeResumeEvent
from orch_panel.coordination.models import (
    ACTIVE_DISPATCH_STATES,
    ArtifactRef,
    Dispatch,
    DispatchState,
    SharedEvent,
)
from orch_panel.coordination.review import (
    ReviewContext,
    ReviewPolicyError,
    ReviewRound,
    assert_cross_provider,
    assert_fresh_session,
    escalation_question,
    findings_return_text,
    judge_provider_for,
    next_action,
    parse_verdict,
    review_event_text,
    review_prompt,
)
from orch_panel.coordination.safety import redact_sensitive_text
from orch_panel.coordination.store import CoordinationStore, StoreError

PROVIDERS = ("codex", "claude")
# Validate only the models this panel selects itself. A caller may use a
# provider-visible custom model; its capabilities stay provider-owned rather
# than becoming a stale panel allowlist.
KNOWN_MODEL_EFFORTS = {
    "gpt-6-astra": frozenset({"low", "medium", "high", "xhigh", "max", "ultra"}),
    "gpt-5.6-sol": frozenset({"low", "medium", "high", "xhigh", "max", "ultra"}),
    "gpt-5.6-terra": frozenset({"low", "medium", "high", "xhigh", "max", "ultra"}),
    "gpt-5.6-luna": frozenset({"low", "medium", "high", "xhigh", "max"}),
    "claude-fable-5-1": frozenset({"low", "medium", "high", "xhigh", "max"}),
    "claude-opus-5": frozenset({"low", "medium", "high", "xhigh", "max"}),
}
# The explicitly chosen root role per runtime. The card text comes from
# `prompts/manifest.json` through the panel's own composition path; the panel
# and the Start sheet both read this table so they cannot drift apart.
ROOT_ROLE_CARDS = {"codex": "start-stage", "claude": "claude-start-stage"}


class BrokerError(RuntimeError):
    """A refused coordination request. Nothing was started or stored."""


def _assert_supported_effort(model: str | None, effort: str | None) -> None:
    """Reject unsupported choices for panel-known models before a launch path forks."""
    supported_efforts = KNOWN_MODEL_EFFORTS.get(model or "")
    if effort and supported_efforts and effort not in supported_efforts:
        raise ValueError(
            f"{model} does not support reasoning effort {effort!r}; "
            f"choose one of {', '.join(sorted(supported_efforts))}"
        )


@dataclass(frozen=True)
class StreamResult:
    """What draining one runtime turn produced."""

    cancelled: bool
    final_text: str = ""
    last_text: str = ""

    @property
    def result_text(self) -> str:
        """Where the final answer arrives is provider-specific.

        Claude puts it on the terminal `completed` event; Codex delivers it as
        the last `item/completed` and closes the turn with bookkeeping only.
        Keeping the last visible text works for both.
        """
        return self.final_text or self.last_text


def share_everything(runtime_event: object) -> bool:
    return True


def share_session_boundaries(runtime_event: object) -> bool:
    """A judge's running commentary stays in its runtime session.

    The epic keeps the native-context checkpoint, any blocker, and one short
    review event; the reasoning and the raw transcript are not shared history.
    """
    return getattr(runtime_event, "kind", "") in {"init", "failed"}


@dataclass(frozen=True)
class OrchestrationDecision:
    """The effective runtime choice for one explicitly started dispatch."""

    prompt_card_id: str
    staged: bool
    role: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    rationale: str = ""


def resolve_orchestration_decision(
    *,
    provider: str,
    prompt_card_id: str = "",
    task_shape: str = "simple",
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> OrchestrationDecision:
    """Resolve the model and effort actually handed to the runtime.

    A caller's explicit choice always wins. The proportional profiles are
    recommendations for a started dispatch, never an automatic delegation or
    an escalation of a neutral simple run.
    """

    shape = task_shape.strip().lower().replace("-", "_") or "simple"
    card_id = prompt_card_id.strip()
    _assert_supported_effort(model, reasoning_effort)
    if not card_id and shape == "simple":
        return OrchestrationDecision(
            prompt_card_id="",
            staged=False,
            model=model,
            reasoning_effort=reasoning_effort,
            rationale="simple local work keeps the runtime default",
        )
    root_card_explicit = card_id == ROOT_ROLE_CARDS[provider]
    if not card_id:
        card_id = ROOT_ROLE_CARDS[provider]

    profiles = {
        "codex": {
            "orchestration": ("orchestrator", "gpt-6-astra", "high"),
            "mechanical": ("worker", "gpt-5.6-luna", "low"),
            "repetitive": ("worker", "gpt-5.6-luna", "medium"),
            "read_heavy": ("explorer", "gpt-5.6-terra", "low"),
            "exploration": ("explorer", "gpt-5.6-terra", "medium"),
            "parallel_support": ("worker", "gpt-5.6-terra", "medium"),
            "implementation": ("worker", "gpt-5.6-sol", "medium"),
            "ambiguity": ("worker", "gpt-5.6-sol", "high"),
            "security": ("security_auditor", "gpt-5.6-sol", "high"),
            "correctness": ("correctness_reviewer", "gpt-5.6-sol", "high"),
            "architecture": ("architect_reviewer", "gpt-5.6-sol", "high"),
            "review": ("correctness_reviewer", "gpt-5.6-sol", "high"),
            "simple": ("worker", "gpt-5.6-terra", "low"),
        },
        "claude": {
            "orchestration": ("orchestrator", "claude-fable-5-1", "high"),
            "mechanical": ("worker", "claude-opus-5", "low"),
            "repetitive": ("worker", "claude-opus-5", "medium"),
            "read_heavy": ("explorer", "claude-opus-5", "medium"),
            "exploration": ("explorer", "claude-opus-5", "medium"),
            "parallel_support": ("worker", "claude-opus-5", "medium"),
            "implementation": ("worker", "claude-opus-5", "medium"),
            "ambiguity": ("worker", "claude-opus-5", "high"),
            "security": ("security_auditor", "claude-opus-5", "high"),
            "correctness": ("correctness_reviewer", "claude-opus-5", "high"),
            "architecture": ("architect_reviewer", "claude-opus-5", "high"),
            "review": ("correctness_reviewer", "claude-opus-5", "high"),
            "simple": ("worker", "claude-opus-5", "low"),
        },
    }
    profile_shape = "orchestration" if root_card_explicit else shape
    role, recommended_model, recommended_effort = profiles[provider].get(
        profile_shape, ("worker", None, None)
    )
    effective_model = model or recommended_model
    # A custom caller-selected model has provider-owned capabilities, so do
    # not guess an effort level for it. Known selected models are checked
    # below, including Astra's lack of `none` and `minimal`.
    use_recommended_effort = not model or model in KNOWN_MODEL_EFFORTS
    effective_effort = reasoning_effort or (
        recommended_effort if use_recommended_effort else None
    )
    _assert_supported_effort(effective_model, effective_effort)
    selected = []
    if model:
        selected.append("explicit model")
    if reasoning_effort:
        selected.append("explicit effort")
    rationale = (
        f"{profile_shape} task uses the proportional {effective_model}/{effective_effort} route"
        if recommended_model
        else f"{shape} has no profile; keep the runtime defaults"
    )
    if root_card_explicit and shape != "orchestration":
        rationale += "; explicit root card keeps the orchestrator runtime"
    if selected:
        rationale += "; " + " and ".join(selected) + " takes precedence"
    return OrchestrationDecision(
        prompt_card_id=card_id,
        staged=True,
        role=role,
        model=effective_model,
        reasoning_effort=effective_effort,
        rationale=rationale,
    )


@dataclass(frozen=True)
class DispatchStart:
    """One explicitly confirmed request to run an agent."""

    project_id: str
    epic_id: str
    provider: str
    task_text: str
    write_zone: str
    idempotency_key: str
    beads_issue_id: str | None = None
    prompt_card_id: str = ""
    model: str | None = None
    reasoning_effort: str | None = None
    verification: str = ""
    references: tuple[str, ...] = ()
    confirmed: bool = False
    # Whether this task's own policy asks for a cross-provider judge before it
    # may close. A task nobody marked stays outside the review loop entirely.
    review_required: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewRequest:
    """One explicitly confirmed request for a fresh cross-provider judge."""

    executor_dispatch_id: str
    requirements: str
    receipt: ArtifactRef | None
    idempotency_key: str
    diff_refs: tuple[str, ...] = ()
    artifact_refs: tuple[ArtifactRef, ...] = ()
    judge_provider: str = ""
    model: str | None = None
    confirmed: bool = False


class Broker:
    def __init__(
        self,
        store: CoordinationStore,
        *,
        journal_path: Path,
        adapter_factory: Callable[[str, SessionJournal], object],
        cwd_resolver: Callable[[str], Path],
        prompt_resolver: Callable[[str, str], dict],
    ) -> None:
        self.store = store
        self.journal = SessionJournal(Path(journal_path))
        self.adapter_factory = adapter_factory
        self.cwd_resolver = cwd_resolver
        self.prompt_resolver = prompt_resolver
        # `_lock` serializes every check-then-act on coordination state.
        # `_runtime_lock` guards the per-dispatch bookkeeping below, including
        # the hand-off of a cancel between `cancel_dispatch` and a worker thread
        # whose `adapter.start` is still in flight. A caller that needs both
        # takes `_lock` first; worker threads only ever take `_runtime_lock`.
        self._lock = threading.RLock()
        self._runtime_lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._session_ready: dict[str, threading.Event] = {}
        self._cancelled: set[str] = set()
        self._cancel_delivered: set[str] = set()
        self._adapters: dict[str, object] = {}
        self._closed = False

    # -- visible stream ------------------------------------------------------

    def post_message(
        self,
        *,
        project_id: str,
        epic_id: str,
        body_text: str,
        author_kind: str = "user",
        event_kind: str = "message",
        beads_issue_id: str | None = None,
        dispatch_id: str | None = None,
        artifact_refs: Iterable[ArtifactRef] = (),
        reply_to: str | None = None,
        idempotency_key: str | None = None,
    ) -> SharedEvent:
        if self.store.epic(epic_id) is None:
            raise BrokerError(f"unknown epic: {epic_id!r}")
        if not body_text.strip():
            raise BrokerError("an empty message is not shared history")
        return self.store.append_event(
            SharedEvent(
                project_id=project_id,
                epic_id=epic_id,
                beads_issue_id=beads_issue_id,
                dispatch_id=dispatch_id,
                author_kind=author_kind,
                event_kind=event_kind,
                body_text=body_text,
                artifact_refs=tuple(artifact_refs),
                reply_to=reply_to,
                idempotency_key=idempotency_key or f"local:{uuid.uuid4()}",
            )
        )

    def send_to_dispatch(
        self,
        dispatch_id: str,
        *,
        body_text: str,
        idempotency_key: str,
        confirmed: bool,
    ) -> SharedEvent:
        """Resume one existing executor turn after an explicit paid action.

        The visible user message is the durable idempotency marker. A retry
        returns that event, while a new key must pass the state and active-turn
        checks before the adapter is touched.
        """
        if not confirmed:
            raise BrokerError("resuming the executor is an explicit user action")
        body = body_text.strip()
        if not body:
            raise BrokerError("an executor message cannot be empty")
        key = idempotency_key.strip()
        if not key:
            raise BrokerError(
                "an executor message needs an idempotency_key from the caller; "
                "the panel must reuse it when retrying the confirmed action"
            )
        event_key = f"{key}:dispatch-message"

        with self._lock:
            dispatch = self.store.dispatch(dispatch_id)
            if dispatch is None:
                raise BrokerError(f"unknown dispatch: {dispatch_id!r}")
            prior = self.store.event_by_key(event_key)
            if prior is not None:
                if prior.dispatch_id == dispatch.dispatch_id:
                    return prior
                raise BrokerError(
                    f"idempotency key {key!r} already belongs to dispatch "
                    f"{prior.dispatch_id}, so it cannot resume {dispatch.dispatch_id}"
                )
            if dispatch.metadata.get("role") != "executor":
                raise BrokerError("only an executor dispatch can receive a user message")
            if dispatch.state in {
                DispatchState.CANCELLED,
                DispatchState.ACCEPTED,
                DispatchState.FAILED,
            }:
                raise BrokerError(
                    f"dispatch {dispatch.dispatch_id} is terminal ({dispatch.state}) "
                    "and cannot accept another model turn"
                )
            if dispatch.state == DispatchState.RUNNING:
                raise BrokerError(
                    f"runtime {dispatch.provider} already has an active turn "
                    f"({dispatch.dispatch_id}); wait for it to finish"
                )
            if dispatch.state not in {
                DispatchState.NEEDS_INPUT,
                DispatchState.AWAITING_REVIEW,
                DispatchState.BLOCKED,
            }:
                raise BrokerError(
                    f"dispatch {dispatch.dispatch_id} is {dispatch.state}, "
                    "not ready to accept input"
                )
            if not dispatch.runtime_session_id:
                raise BrokerError(
                    f"dispatch {dispatch.dispatch_id} has no runtime session to resume"
                )
            blocking = self._active_turn(dispatch.provider, dispatch.project_id)
            if blocking is not None and blocking.dispatch_id != dispatch.dispatch_id:
                raise BrokerError(
                    f"runtime {dispatch.provider} already has an active turn "
                    f"({blocking.dispatch_id}); cancel it or wait for it to finish"
                )
            sent = self.store.append_event(
                SharedEvent(
                    project_id=dispatch.project_id,
                    epic_id=dispatch.epic_id,
                    beads_issue_id=dispatch.beads_issue_id,
                    dispatch_id=dispatch.dispatch_id,
                    runtime_session_id=dispatch.runtime_session_id,
                    author_kind="user",
                    event_kind="message",
                    body_text=body,
                    idempotency_key=event_key,
                )
            )
            running = self.store.update_dispatch(
                dispatch.dispatch_id, state=DispatchState.RUNNING
            )
            self._start_thread(
                running.dispatch_id,
                self._run_resume,
                (running, sent.body_text, sent.event_id),
                f"dialogue-{running.dispatch_id[:12]}",
            )
        return sent

    # -- dispatch ------------------------------------------------------------

    def start_dispatch(self, request: DispatchStart) -> Dispatch:
        """Start one runtime turn, or return the dispatch this key already made.

        Every refusal happens before anything is written, so a rejected start
        leaves neither a dispatch row nor a visible event behind.
        """
        if not request.confirmed:
            raise BrokerError("starting a runtime is an explicit user action")
        if request.provider not in PROVIDERS:
            raise BrokerError(f"unknown runtime provider: {request.provider!r}")
        if self.store.epic(request.epic_id) is None:
            raise BrokerError(f"unknown epic: {request.epic_id!r}")
        if not request.task_text.strip():
            raise BrokerError("a dispatch needs task text")
        if not request.idempotency_key.strip():
            raise BrokerError(
                "a dispatch needs an idempotency_key from the caller; the panel "
                "must not invent one, or a retry becomes a second paid run"
            )
        task_shape = str(request.metadata.get("task_shape") or "").strip()
        if not task_shape:
            task_shape = "orchestration" if request.prompt_card_id else "simple"
        try:
            route = resolve_orchestration_decision(
                provider=request.provider,
                prompt_card_id=request.prompt_card_id,
                task_shape=task_shape,
                model=request.model,
                reasoning_effort=request.reasoning_effort,
            )
        except ValueError as exc:
            raise BrokerError(str(exc)) from exc
        card_id = route.prompt_card_id
        role_text = ""
        if card_id:
            try:
                role = self.prompt_resolver(card_id, request.provider)
            except Exception as exc:
                raise BrokerError(f"root role {card_id!r} is unavailable: {exc}") from exc
            role_text = str(role.get("text") or "")

        with self._lock:
            blocking = self._active_turn(request.provider, request.project_id)
            if blocking is not None and blocking.idempotency_key != request.idempotency_key:
                raise BrokerError(
                    f"runtime {request.provider} already has an active turn "
                    f"({blocking.dispatch_id}); cancel it or wait for it to finish"
                )

            references = self._references(request)
            if route.staged:
                references += (
                    "Runtime route: "
                    f"role={route.role}; model={route.model}; "
                    f"reasoning={route.reasoning_effort}; {route.rationale}",
                )
            prompt = compose_dispatch_handoff(
                goal=request.task_text,
                write_zone=request.write_zone,
                verification=request.verification,
                references=references,
                role_text=role_text,
            )
            dispatch = self.store.create_dispatch(
                project_id=request.project_id,
                epic_id=request.epic_id,
                beads_issue_id=request.beads_issue_id,
                provider=request.provider,
                idempotency_key=request.idempotency_key,
                write_zone=request.write_zone,
                prompt_card_id=card_id,
                prompt_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                review_required=request.review_required,
            )
            if dispatch.state != DispatchState.AWAITING_START:
                return dispatch

            self.store.append_event(
                SharedEvent(
                    project_id=request.project_id,
                    epic_id=request.epic_id,
                    beads_issue_id=request.beads_issue_id,
                    dispatch_id=dispatch.dispatch_id,
                    author_kind="user",
                    event_kind="decision",
                    body_text=self._start_decision_text(request, route),
                    idempotency_key=f"{dispatch.dispatch_id}:start",
                )
            )
            dispatch = self.store.update_dispatch(
                dispatch.dispatch_id, state=DispatchState.RUNNING
            )
            self._start_thread(
                dispatch.dispatch_id,
                self._run_dispatch,
                (dispatch, request, prompt, route),
                f"dispatch-{dispatch.dispatch_id[:12]}",
            )
        return dispatch

    @staticmethod
    def _start_decision_text(
        request: DispatchStart, route: OrchestrationDecision
    ) -> str:
        text = f"Start {request.provider} on {request.write_zone or 'the repository'}"
        if not route.staged:
            return text
        return (
            f"{text}; runtime role={route.role}, model={route.model}, "
            f"reasoning={route.reasoning_effort} — {route.rationale}"
        )

    def _references(self, request: DispatchStart) -> tuple[str, ...]:
        """Durable pointers only: Beads and repository truth, never chat text."""
        references = list(request.references)
        if request.beads_issue_id:
            references.insert(0, f"Beads issue: {request.beads_issue_id}")
        references.append(f"Epic workspace: {request.epic_id}")
        return tuple(references)

    def _active_turn(self, provider: str, project_id: str) -> Dispatch | None:
        # Asking the store for the active rows keeps this from loading every
        # dispatch the project ever had just to find at most one live turn.
        for dispatch in self.store.active_dispatches(
            provider=provider, project_id=project_id
        ):
            return dispatch
        return None

    def _adapter(self, provider: str) -> object:
        adapter = self._adapters.get(provider)
        if adapter is None:
            adapter = self.adapter_factory(provider, self.journal)
            self._adapters[provider] = adapter
        return adapter

    # -- per-dispatch runtime bookkeeping ------------------------------------

    def _start_thread(self, dispatch_id: str, target: Callable, args: tuple, name: str) -> None:
        """Register one turn's thread and readiness gate, then run it."""
        thread = threading.Thread(target=target, args=args, name=name, daemon=True)
        with self._runtime_lock:
            self._session_ready[dispatch_id] = threading.Event()
            self._threads[dispatch_id] = thread
        thread.start()

    def _ready_event(self, dispatch_id: str) -> threading.Event:
        with self._runtime_lock:
            ready = self._session_ready.get(dispatch_id)
            if ready is None:
                ready = threading.Event()
                self._session_ready[dispatch_id] = ready
            return ready

    def _forget_dispatch(self, dispatch_id: str) -> None:
        """Drop a finished turn's bookkeeping.

        Without this the four per-dispatch maps grew for the process lifetime,
        so a long-running panel kept every thread object and cancel flag it had
        ever created. A resumed dispatch registers fresh entries.
        """
        with self._runtime_lock:
            self._threads.pop(dispatch_id, None)
            self._session_ready.pop(dispatch_id, None)
            self._cancelled.discard(dispatch_id)
            self._cancel_delivered.discard(dispatch_id)

    def _finish_turn(self, dispatch_id: str, ready: threading.Event) -> None:
        ready.set()
        current = self.store.dispatch(dispatch_id)
        if current is None or current.state not in ACTIVE_DISPATCH_STATES:
            self._forget_dispatch(dispatch_id)

    def _consume_runtime_stream(
        self,
        dispatch: Dispatch,
        adapter: object,
        session: object,
        *,
        share: Callable[[object], bool] = share_everything,
    ) -> StreamResult:
        """Drain one runtime turn. The only copy of this loop.

        Each of the three turn runners used to carry its own cancel-check,
        append and settle sequence, so every fix to cancellation had to be made
        three times and proved three times.
        """
        dispatch_id = dispatch.dispatch_id
        final_text = ""
        last_text = ""
        for runtime_event in adapter.stream(session, None):
            if dispatch_id in self._cancelled:
                return StreamResult(True, final_text, last_text)
            if share(runtime_event):
                shared = shared_event_from_runtime_event(
                    runtime_event,
                    project_id=dispatch.project_id,
                    epic_id=dispatch.epic_id,
                    dispatch_id=dispatch_id,
                    beads_issue_id=dispatch.beads_issue_id,
                )
                if shared is not None:
                    self.store.append_event(shared)
            if runtime_event.kind in HIDDEN_KINDS or runtime_event.kind in INCREMENTAL_KINDS:
                continue
            text = visible_text(runtime_event.payload)
            if not text:
                continue
            last_text = text
            if runtime_event.kind == "completed":
                final_text = text
        return StreamResult(dispatch_id in self._cancelled, final_text, last_text)

    def _publish_session_id(self, dispatch_id: str, session: object) -> bool:
        """Record the session id and claim the cancel, if one is already pending.

        Publishing the id and reading the cancel flag under one lock closes the
        window: either `cancel_dispatch` already saw the session and delivered
        the cancel, or this thread does it here.
        """
        with self._runtime_lock:
            self.store.update_dispatch(
                dispatch_id, runtime_session_id=session.runtime_session_id
            )
            cancel_here = (
                dispatch_id in self._cancelled
                and dispatch_id not in self._cancel_delivered
            )
            if cancel_here:
                self._cancel_delivered.add(dispatch_id)
        return cancel_here

    def _run_dispatch(
        self,
        dispatch: Dispatch,
        request: DispatchStart,
        prompt: str,
        route: OrchestrationDecision,
    ) -> None:
        dispatch_id = dispatch.dispatch_id
        ready = self._ready_event(dispatch_id)
        try:
            adapter = self._adapter(request.provider)
            session = adapter.start(
                DispatchRequest(
                    idempotency_key=dispatch.idempotency_key,
                    cwd=Path(self.cwd_resolver(request.project_id)),
                    prompt=prompt,
                    model=route.model,
                    reasoning_effort=route.reasoning_effort,
                )
            )
            cancel_here = self._publish_session_id(dispatch_id, session)
            ready.set()
            if cancel_here:
                self._deliver_cancel(adapter, session, dispatch)
                return
            if dispatch_id in self._cancelled:
                return
            result = self._consume_runtime_stream(dispatch, adapter, session)
            if not result.cancelled:
                self.store.update_dispatch(dispatch_id, state=DispatchState.AWAITING_REVIEW)
        except Exception as exc:  # a runtime failure is a visible blocker, not a crash
            self._record_blocker(dispatch, request, exc)
        finally:
            self._finish_turn(dispatch_id, ready)

    def _record_blocker(
        self, dispatch: Dispatch, request: DispatchStart, exc: BaseException
    ) -> None:
        safe_error = redact_sensitive_text(exc)[:500]
        try:
            self.store.append_event(
                SharedEvent(
                    project_id=request.project_id,
                    epic_id=request.epic_id,
                    beads_issue_id=request.beads_issue_id,
                    dispatch_id=dispatch.dispatch_id,
                    author_kind="system",
                    event_kind="blocker",
                    body_text=f"{request.provider} dispatch failed: {safe_error}",
                    idempotency_key=f"{dispatch.dispatch_id}:blocker",
                )
            )
            current = self.store.dispatch(dispatch.dispatch_id)
            if current is not None and current.state not in {
                DispatchState.CANCELLED,
                DispatchState.BLOCKED,
            }:
                self.store.update_dispatch(
                    dispatch.dispatch_id, state=DispatchState.BLOCKED, detail=safe_error
                )
        except StoreError:  # pragma: no cover - the store already refused once
            pass

    def _deliver_cancel(self, adapter: object, session: object, dispatch: Dispatch) -> None:
        """Deliver one cancellation, falling back to closing the runtime transport."""
        try:
            adapter.cancel(session)
        except Exception as exc:
            close_error: Exception | None = None
            close = getattr(adapter, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as caught:
                    close_error = caught
            detail = f"cancel delivery failed: {redact_sensitive_text(exc)}"
            if close_error is not None:
                detail += f"; adapter close failed: {redact_sensitive_text(close_error)}"
            try:
                self.store.update_dispatch(
                    dispatch.dispatch_id, detail=detail[:500]
                )
                self.store.append_event(
                    SharedEvent(
                        project_id=dispatch.project_id,
                        epic_id=dispatch.epic_id,
                        beads_issue_id=dispatch.beads_issue_id,
                        dispatch_id=dispatch.dispatch_id,
                        author_kind="system",
                        event_kind="blocker",
                        body_text=detail,
                        idempotency_key=f"{dispatch.dispatch_id}:cancel-failed",
                    )
                )
            except StoreError:
                pass

    def cancel_dispatch(self, dispatch_id: str) -> Dispatch:
        """Record the cancel immediately, then deliver it exactly once.

        The state moves to `cancelled` before the runtime is reached, so a cancel
        raised in the window between `running` and a known `runtime_session_id`
        is never reported back as still running.

        It runs under the same lock as `send_to_dispatch`, which decides whether
        to persist a user message from the very same state. Without that, a
        message could be written for a dispatch the cancel was already settling.
        """
        with self._lock:
            dispatch = self.store.dispatch(dispatch_id)
            if dispatch is None:
                raise BrokerError(f"unknown dispatch: {dispatch_id!r}")
            if dispatch.state not in ACTIVE_DISPATCH_STATES:
                raise BrokerError(f"dispatch {dispatch_id} is {dispatch.state}, not running")
            with self._runtime_lock:
                self._cancelled.add(dispatch_id)
                current = self.store.dispatch(dispatch_id) or dispatch
                adapter = self._adapters.get(dispatch.provider)
                deliver_here = (
                    adapter is not None
                    and bool(current.runtime_session_id)
                    and dispatch_id not in self._cancel_delivered
                )
                if deliver_here:
                    self._cancel_delivered.add(dispatch_id)
            # Persist the user's intent before crossing the runtime boundary. A
            # transport failure must never strand a finished worker as `running`.
            #
            # The run can also settle itself between the check above and this
            # write: a judge stays `running` until its verdict is durable, so
            # that window is a real one. Whoever settles first owns the state, in
            # this direction as well as in `_record_verdict`'s. The cancel then
            # never happened, so the intent is dropped rather than left behind as
            # a flag a later read could mistake for a cancelled run.
            try:
                self.store.update_dispatch(dispatch_id, state=DispatchState.CANCELLED)
            except StoreError as exc:
                with self._runtime_lock:
                    self._cancelled.discard(dispatch_id)
                    self._cancel_delivered.discard(dispatch_id)
                settled = self.store.dispatch(dispatch_id)
                raise BrokerError(
                    f"dispatch {dispatch_id} is {settled.state if settled else 'gone'}, "
                    "not running; it settled before the cancel reached it"
                ) from exc
            self.store.append_event(
                SharedEvent(
                    project_id=dispatch.project_id,
                    epic_id=dispatch.epic_id,
                    beads_issue_id=dispatch.beads_issue_id,
                    dispatch_id=dispatch_id,
                    author_kind="user",
                    event_kind="decision",
                    body_text=f"Cancel {dispatch.provider} dispatch",
                    idempotency_key=f"{dispatch_id}:cancel",
                )
            )
            if deliver_here:
                self._deliver_cancel(
                    adapter,
                    self.journal.get_session(dispatch.provider, current.runtime_session_id),
                    dispatch,
                )
            return self.store.dispatch(dispatch_id)  # type: ignore[return-value]

    # -- cross-provider review ----------------------------------------------

    def next_review_action(self, executor_dispatch_id: str) -> str:
        """Name the only next step the bounded loop permits for this task."""
        return next_action(self.store.review_rounds(executor_dispatch_id))

    def request_review(self, request: ReviewRequest) -> Dispatch:
        """Start one fresh cross-provider judge, or refuse before anything runs.

        Every refusal happens before the adapter is touched, so a rejected
        review costs nothing: no dispatch row, no session, no paid turn.
        """
        if not request.confirmed:
            raise BrokerError("starting a judge is an explicit user action")
        key = request.idempotency_key.strip()
        if not key:
            raise BrokerError(
                "a review needs an idempotency_key from the caller; the panel must "
                "not invent one, or a retry becomes a second paid judge run"
            )

        # Everything from here on reads shared state and then acts on it, so it
        # runs inside one serialized section. Deciding outside the lock let two
        # callers both read "request_review" and both buy a judge turn.
        with self._lock:
            executor = self.store.dispatch(request.executor_dispatch_id)
            if executor is None:
                raise BrokerError(f"unknown dispatch: {request.executor_dispatch_id!r}")
            if executor.metadata.get("role") != "executor":
                raise BrokerError("only an executor run can be sent to a judge")
            if executor.state != DispatchState.AWAITING_REVIEW:
                raise BrokerError(
                    f"dispatch {executor.dispatch_id} is {executor.state}; a judge "
                    "reviews a finished result, not a run in flight"
                )
            existing = self.store.dispatch_by_key(key)
            if existing is not None:
                if (
                    existing.metadata.get("role") == "judge"
                    and existing.metadata.get("parent_dispatch_id") == executor.dispatch_id
                ):
                    # The same confirmed action, retried. It resolves to the judge
                    # run it already made rather than paying for a second one.
                    return existing
                raise BrokerError(
                    f"idempotency key {key!r} already belongs to dispatch "
                    f"{existing.dispatch_id}, so it cannot start a fresh judge "
                    "session; a required judge must open a new session of its own"
                )
            rounds = self.store.review_rounds(executor.dispatch_id)
            action = next_action(rounds)
            if action != "request_review":
                if action == "escalate":
                    self._escalate(executor, rounds)
                raise BrokerError(self._review_refusal(action))
            judge_provider = request.judge_provider or judge_provider_for(executor.provider)
            # `adapter.start` resolves an idempotency key against the journal
            # and hands back the session that key already opened, so a key with
            # a live session would reach a runtime that carries someone else's
            # turn. The assertion after `start` would catch it only once the
            # turn had been paid for, so freshness is asked here first.
            if self.journal.find_session(judge_provider, key) is not None:
                raise BrokerError(
                    f"idempotency key {key!r} already opened a {judge_provider} "
                    "runtime session, so it cannot start a fresh judge; a "
                    "required judge must open a new session of its own"
                )
            try:
                assert_cross_provider(
                    executor_provider=executor.provider, judge_provider=judge_provider
                )
                prompt = review_prompt(
                    ReviewContext(
                        requirements=request.requirements,
                        receipt=request.receipt,
                        diff_refs=tuple(request.diff_refs),
                        artifact_refs=tuple(request.artifact_refs),
                        # Round two carries only what round one asked for.
                        findings=rounds[-1].actionable_findings if rounds else (),
                        round=len(rounds) + 1,
                    )
                )
            except ReviewPolicyError as exc:
                raise BrokerError(str(exc)) from exc
            blocking = self._active_turn(judge_provider, executor.project_id)
            if blocking is not None:
                raise BrokerError(
                    f"runtime {judge_provider} already has an active turn "
                    f"({blocking.dispatch_id}); cancel it or wait for it to finish"
                )
            judge = self.store.create_dispatch(
                project_id=executor.project_id,
                epic_id=executor.epic_id,
                beads_issue_id=executor.beads_issue_id,
                provider=judge_provider,
                idempotency_key=key,
                # A judge owns nothing in the worktree, so it is granted nothing.
                write_zone="",
                prompt_card_id="",
                prompt_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                role="judge",
                parent_dispatch_id=executor.dispatch_id,
            )
            self.store.append_event(
                SharedEvent(
                    project_id=executor.project_id,
                    epic_id=executor.epic_id,
                    beads_issue_id=executor.beads_issue_id,
                    dispatch_id=judge.dispatch_id,
                    author_kind="user",
                    event_kind="decision",
                    body_text=(
                        f"Start a fresh read-only {judge_provider} judge for round "
                        f"{len(rounds) + 1} of {len(rounds) + 1 if rounds else 1}"
                    ),
                    idempotency_key=f"{judge.dispatch_id}:start",
                )
            )
            judge = self.store.update_dispatch(
                judge.dispatch_id, state=DispatchState.RUNNING
            )
            self._start_thread(
                judge.dispatch_id,
                self._run_judge,
                (judge, executor, prompt, request),
                f"judge-{judge.dispatch_id[:12]}",
            )
        return judge

    @staticmethod
    def _review_refusal(action: str) -> str:
        return {
            "accept": "this result already has an accepted verdict",
            "resolved": "the user already decided this review",
            "return_findings": (
                "the last verdict has findings that have not returned to the "
                "executor yet; send them back before asking the judge again"
            ),
            "escalate": (
                "the review loop is bounded and has run out of rounds; no further "
                "model call will start, so the user has to decide"
            ),
        }.get(action, f"the review loop does not permit {action!r} right now")

    def _run_judge(
        self,
        judge: Dispatch,
        executor: Dispatch,
        prompt: str,
        request: ReviewRequest,
    ) -> None:
        """Run one judge turn and turn its answer into structure.

        The judge's running commentary is not appended to shared history. What
        the epic keeps is the native-context checkpoint, any blocker, and one
        short review event; the reasoning and the raw transcript stay in the
        runtime session where they belong.
        """
        judge_id = judge.dispatch_id
        ready = self._ready_event(judge_id)
        start_request = DispatchStart(
            project_id=judge.project_id,
            epic_id=judge.epic_id,
            provider=judge.provider,
            task_text=request.requirements,
            write_zone="",
            idempotency_key=judge.idempotency_key,
            beads_issue_id=judge.beads_issue_id,
        )
        try:
            adapter = self._adapter(judge.provider)
            session = adapter.start(
                DispatchRequest(
                    idempotency_key=judge.idempotency_key,
                    cwd=Path(self.cwd_resolver(judge.project_id)),
                    prompt=prompt,
                    model=request.model,
                    # The adapter turns this into a real runtime restriction.
                    # Codex already runs its turn under `sandbox: read-only`;
                    # Claude needs its write tools removed at launch.
                    metadata={"read_only": True},
                )
            )
            cancel_here = self._publish_session_id(judge_id, session)
            ready.set()
            if cancel_here:
                self._deliver_cancel(adapter, session, judge)
                return
            if judge_id in self._cancelled:
                return
            # The session id is only real now, so the freshness rule is confirmed
            # against it as well as against the key that was checked up front.
            assert_fresh_session(
                judge_session_id=session.runtime_session_id,
                used_session_ids=self.store.used_session_ids(executor.dispatch_id),
            )
            result = self._consume_runtime_stream(
                judge, adapter, session, share=share_session_boundaries
            )
            if result.cancelled:
                return
            self._record_verdict(
                judge, executor, session.runtime_session_id, result.result_text
            )
        except Exception as exc:  # a judge failure, policy or runtime, is visible
            self._record_blocker(judge, start_request, exc)
        finally:
            self._finish_turn(judge_id, ready)

    def _record_verdict(
        self,
        judge: Dispatch,
        executor: Dispatch,
        judge_session_id: str,
        result_text: str,
    ) -> None:
        verdict = parse_verdict(result_text)
        round_record = self.store.record_review_round(
            executor_dispatch_id=executor.dispatch_id,
            outcome=verdict.outcome,
            summary=verdict.summary,
            findings=verdict.findings,
            judge_dispatch_id=judge.dispatch_id,
            judge_provider=judge.provider,
            judge_session_id=judge_session_id,
        )
        self.store.append_event(
            SharedEvent(
                project_id=judge.project_id,
                epic_id=judge.epic_id,
                beads_issue_id=judge.beads_issue_id,
                dispatch_id=judge.dispatch_id,
                runtime_session_id=judge_session_id,
                author_kind=judge.provider,
                event_kind="review",
                body_text=review_event_text(
                    verdict,
                    judge_provider=judge.provider,
                    round_number=round_record.round,
                ),
                idempotency_key=f"{judge.dispatch_id}:review",
            )
        )
        # Keep the judge active until its structured verdict and visible event
        # are durable. Otherwise a second request can observe neither an active
        # turn nor a review round and buy another judge in that narrow window.
        #
        # A cancel can land inside that window. It settles the dispatch itself
        # and `cancelled` has no outgoing edge, so settling again would raise
        # and be written to shared history as a failed judge run standing next
        # to a verdict that is durable and correct. Whoever settled it first
        # owns the state; the verdict above is unaffected either way.
        try:
            self.store.update_dispatch(
                judge.dispatch_id, state=DispatchState.AWAITING_REVIEW
            )
            # The judge run itself is finished the moment its verdict is durable.
            self.store.update_dispatch(judge.dispatch_id, state=DispatchState.ACCEPTED)
        except StoreError:
            pass
        if verdict.accepted:
            current = self.store.dispatch(executor.dispatch_id)
            if current is not None and current.state == DispatchState.AWAITING_REVIEW:
                self.store.update_dispatch(
                    executor.dispatch_id, state=DispatchState.ACCEPTED
                )
        self._escalate(executor, self.store.review_rounds(executor.dispatch_id))

    def _escalate(self, executor: Dispatch, rounds: Sequence[ReviewRound]) -> None:
        """Ask the user once when the loop has no move left. Never a model call."""
        if next_action(rounds) != "escalate":
            return
        try:
            self.store.append_event(
                SharedEvent(
                    project_id=executor.project_id,
                    epic_id=executor.epic_id,
                    beads_issue_id=executor.beads_issue_id,
                    dispatch_id=executor.dispatch_id,
                    author_kind="system",
                    event_kind="question",
                    body_text=escalation_question(rounds),
                    idempotency_key=f"{executor.dispatch_id}:escalation:{len(rounds)}",
                )
            )
        except StoreError:  # pragma: no cover - the store already refused once
            pass

    def return_findings(
        self, executor_dispatch_id: str, *, idempotency_key: str, confirmed: bool
    ) -> Dispatch:
        """Resume the same executor session with only the findings.

        The executor keeps its own context; what it receives back is the judge's
        actionable findings and the new visible events, not a fresh briefing and
        not the judge's prose.
        """
        if not confirmed:
            raise BrokerError("resuming the executor is an explicit user action")
        if not idempotency_key.strip():
            raise BrokerError("returning findings needs an idempotency_key from the caller")

        # One serialized section again: the round this returns is also the round
        # it marks as returned, so reading it outside the lock would let two
        # callers resume the same session twice.
        with self._lock:
            executor = self.store.dispatch(executor_dispatch_id)
            if executor is None:
                raise BrokerError(f"unknown dispatch: {executor_dispatch_id!r}")
            rounds = self.store.review_rounds(executor_dispatch_id)
            action = next_action(rounds)
            if action != "return_findings":
                # One key is one confirmed action. The first call moves the loop
                # past `return_findings`, so a retry of that same key would read
                # as a refusal of an action that in fact succeeded. It resolves
                # to the run it already resumed instead, the way a retried
                # `request_review` resolves to the judge it already started. The
                # key has to name this executor: it is not a skeleton key for
                # resuming a second one.
                prior = self.store.event_by_key(f"{idempotency_key}:return")
                if prior is not None and prior.dispatch_id == executor.dispatch_id:
                    return executor
                if action == "escalate":
                    self._escalate(executor, rounds)
                raise BrokerError(self._review_refusal(action))
            if not executor.runtime_session_id:
                raise BrokerError(
                    f"dispatch {executor_dispatch_id} has no runtime session to resume"
                )
            last = rounds[-1]
            try:
                body = findings_return_text(rounds)
            except ReviewPolicyError as exc:
                raise BrokerError(str(exc)) from exc
            blocking = self._active_turn(executor.provider, executor.project_id)
            if blocking is not None:
                raise BrokerError(
                    f"runtime {executor.provider} already has an active turn "
                    f"({blocking.dispatch_id}); cancel it or wait for it to finish"
                )
            self.store.append_event(
                SharedEvent(
                    project_id=executor.project_id,
                    epic_id=executor.epic_id,
                    beads_issue_id=executor.beads_issue_id,
                    dispatch_id=executor.dispatch_id,
                    author_kind="user",
                    event_kind="decision",
                    body_text=(
                        f"Return {len(last.actionable_findings)} finding(s) from the "
                        f"{last.judge_provider} judge to the {executor.provider} executor"
                    ),
                    idempotency_key=f"{idempotency_key}:return",
                )
            )
            self.store.mark_revision_returned(last.review_id)
            dispatch = self.store.update_dispatch(
                executor.dispatch_id, state=DispatchState.RUNNING
            )
            self._start_thread(
                dispatch.dispatch_id,
                self._run_resume,
                (dispatch, body, last.review_id),
                f"revision-{dispatch.dispatch_id[:12]}",
            )
        return dispatch

    def _run_resume(self, dispatch: Dispatch, body: str, resume_event_id: str) -> None:
        dispatch_id = dispatch.dispatch_id
        ready = self._ready_event(dispatch_id)
        start_request = DispatchStart(
            project_id=dispatch.project_id,
            epic_id=dispatch.epic_id,
            provider=dispatch.provider,
            task_text=body,
            write_zone=dispatch.write_zone,
            idempotency_key=dispatch.idempotency_key,
            beads_issue_id=dispatch.beads_issue_id,
        )
        try:
            adapter = self._adapter(dispatch.provider)
            session = self.journal.get_session(
                dispatch.provider, dispatch.runtime_session_id or ""
            )
            if session is None:
                raise BrokerError(
                    f"runtime session {dispatch.runtime_session_id!r} is no longer known"
                )
            adapter.resume(
                session,
                [RuntimeResumeEvent(event_id=resume_event_id, body_text=body)],
            )
            ready.set()
            if dispatch_id in self._cancelled:
                return
            result = self._consume_runtime_stream(dispatch, adapter, session)
            if not result.cancelled:
                self.store.update_dispatch(
                    dispatch_id, state=DispatchState.AWAITING_REVIEW
                )
        except Exception as exc:
            self._record_blocker(dispatch, start_request, exc)
        finally:
            self._finish_turn(dispatch_id, ready)

    def record_user_decision(
        self,
        executor_dispatch_id: str,
        *,
        decision: str,
        reason: str,
        idempotency_key: str,
    ) -> ReviewRound:
        """Record the user's own call after the loop ran out of rounds.

        This is the only way a review-gated task moves without an accepted
        verdict, and it is stored as an explicit user decision so the override
        is never mistaken for a review.
        """
        if decision not in {"accepted", "rejected"}:
            raise BrokerError(f"a decision is 'accepted' or 'rejected': {decision!r}")
        if not reason.strip():
            raise BrokerError("an override needs a reason someone can read later")
        if not idempotency_key.strip():
            raise BrokerError("a decision needs an idempotency_key from the caller")

        # The override is check-then-write like the other two, so it is
        # serialized the same way. A second caller finds the loop already
        # `resolved` and receives that one durable decision.
        with self._lock:
            executor = self.store.dispatch(executor_dispatch_id)
            if executor is None:
                raise BrokerError(f"unknown dispatch: {executor_dispatch_id!r}")
            rounds = self.store.review_rounds(executor_dispatch_id)
            action = next_action(rounds)
            if action == "resolved":
                return next(item for item in reversed(rounds) if item.decided_by == "user")
            if action != "escalate":
                raise BrokerError(
                    "the review loop has not asked for a decision yet; it is still at "
                    f"{action!r}"
                )
            record = self.store.record_review_round(
                executor_dispatch_id=executor_dispatch_id,
                outcome="accepted" if decision == "accepted" else "changes_requested",
                summary=reason.strip()[:240],
                decided_by="user",
            )
            self.store.append_event(
                SharedEvent(
                    project_id=executor.project_id,
                    epic_id=executor.epic_id,
                    beads_issue_id=executor.beads_issue_id,
                    dispatch_id=executor.dispatch_id,
                    author_kind="user",
                    event_kind="decision",
                    body_text=(
                        f"User {decision} this result after the review loop: "
                        f"{reason.strip()}"
                    ),
                    idempotency_key=f"{idempotency_key}:decision",
                )
            )
            if decision == "accepted":
                current = self.store.dispatch(executor_dispatch_id)
                if current is not None and current.state == DispatchState.AWAITING_REVIEW:
                    self.store.update_dispatch(
                        executor_dispatch_id, state=DispatchState.ACCEPTED
                    )
            return record

    # -- test and shutdown helpers ------------------------------------------

    def wait_for_session(self, dispatch_id: str, timeout: float = 10) -> bool:
        with self._runtime_lock:
            ready = self._session_ready.get(dispatch_id)
        return bool(ready and ready.wait(timeout=timeout))

    def wait_for_dispatch(self, dispatch_id: str, timeout: float = 10) -> bool:
        with self._runtime_lock:
            thread = self._threads.get(dispatch_id)
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def running_dispatch_ids(self) -> Sequence[str]:
        with self._runtime_lock:
            threads = list(self._threads.items())
        return [dispatch_id for dispatch_id, thread in threads if thread.is_alive()]

    def reconcile(self) -> list[Dispatch]:
        """Settle dispatch rows a previous panel process left active.

        Reconciliation never starts or resumes a model turn. It asks the
        provider adapter to inspect the persisted native session, replays only
        runtime events already present in the local journal, and records one
        deterministic recovery event before changing the dispatch state. That
        ordering makes a crash inside this pass safe to retry.
        """
        reconciled: list[Dispatch] = []
        with self._lock:
            active = [
                dispatch
                for dispatch in self.store.dispatches()
                if dispatch.state in ACTIVE_DISPATCH_STATES
            ]
            for dispatch in active:
                session = (
                    self.journal.get_session(
                        dispatch.provider, dispatch.runtime_session_id
                    )
                    if dispatch.runtime_session_id
                    else None
                )
                inspected = None
                detail = ""
                if session is None:
                    detail = "recovery: the panel stopped before a native session was recorded"
                    target = DispatchState.BLOCKED
                else:
                    try:
                        inspected = self._adapter(dispatch.provider).inspect(session)
                    except Exception as exc:
                        detail = (
                            "recovery: native session inspection failed: "
                            f"{redact_sensitive_text(exc)}"
                        )
                        target = DispatchState.BLOCKED
                    else:
                        for runtime_event in self.journal.events(
                            dispatch.provider, dispatch.runtime_session_id
                        ):
                            shared = shared_event_from_runtime_event(
                                runtime_event,
                                project_id=dispatch.project_id,
                                epic_id=dispatch.epic_id,
                                dispatch_id=dispatch.dispatch_id,
                                beads_issue_id=dispatch.beads_issue_id,
                            )
                            if shared is not None:
                                self.store.append_event(shared)
                        if inspected.status == RuntimeStatus.COMPLETED:
                            target = (
                                DispatchState.BLOCKED
                                if dispatch.metadata.get("role") == "judge"
                                else DispatchState.AWAITING_REVIEW
                            )
                            detail = (
                                "recovery: judge completed before its verdict was persisted"
                                if target == DispatchState.BLOCKED
                                else "recovery: native turn had already completed"
                            )
                        elif inspected.status == RuntimeStatus.CANCELLED:
                            target = DispatchState.CANCELLED
                            detail = "recovery: native turn had already been cancelled"
                        else:
                            target = DispatchState.BLOCKED
                            detail = (
                                "recovery: the native turn did not reach a durable terminal "
                                f"state ({inspected.status})"
                            )
                self.store.append_event(
                    SharedEvent(
                        project_id=dispatch.project_id,
                        epic_id=dispatch.epic_id,
                        beads_issue_id=dispatch.beads_issue_id,
                        dispatch_id=dispatch.dispatch_id,
                        runtime_session_id=dispatch.runtime_session_id,
                        author_kind="system",
                        event_kind=(
                            "blocker" if target == DispatchState.BLOCKED else "checkpoint"
                        ),
                        body_text=detail,
                        idempotency_key=f"{dispatch.dispatch_id}:recovery",
                    )
                )
                if dispatch.state == DispatchState.NEEDS_INPUT and target not in {
                    DispatchState.RUNNING,
                    DispatchState.CANCELLED,
                }:
                    self.store.update_dispatch(
                        dispatch.dispatch_id, state=DispatchState.RUNNING
                    )
                reconciled.append(
                    self.store.update_dispatch(
                        dispatch.dispatch_id,
                        state=target,
                        detail=detail[:500],
                    )
                )
        return reconciled

    def resolve_orphan(
        self,
        dispatch_id: str,
        *,
        idempotency_key: str,
        confirmed: bool,
    ) -> Dispatch:
        """Close one recovery blocker locally while retaining native state."""
        if not confirmed:
            raise BrokerError("closing an orphan is an explicit user action")
        if not idempotency_key.strip():
            raise BrokerError("resolving an orphan needs an idempotency_key")
        with self._lock:
            dispatch = self.store.dispatch(dispatch_id)
            if dispatch is None:
                raise BrokerError(f"unknown dispatch: {dispatch_id!r}")
            if not dispatch.detail.startswith("recovery:"):
                raise BrokerError(
                    f"dispatch {dispatch_id} is not a startup-recovery orphan"
                )
            if dispatch.state not in {DispatchState.BLOCKED, DispatchState.CANCELLED}:
                raise BrokerError(
                    f"dispatch {dispatch_id} is {dispatch.state}, not a recoverable orphan"
                )
            if dispatch.state == DispatchState.CANCELLED:
                return dispatch
            self.store.append_event(
                SharedEvent(
                    project_id=dispatch.project_id,
                    epic_id=dispatch.epic_id,
                    beads_issue_id=dispatch.beads_issue_id,
                    dispatch_id=dispatch.dispatch_id,
                    runtime_session_id=dispatch.runtime_session_id,
                    author_kind="user",
                    event_kind="decision",
                    body_text=(
                        "Closed the orphaned dispatch in local coordination state; "
                        "the native runtime session and linked artifacts were retained."
                    ),
                    idempotency_key=f"{idempotency_key}:resolve-orphan",
                )
            )
            if dispatch.state == DispatchState.BLOCKED:
                dispatch = self.store.update_dispatch(
                    dispatch_id,
                    state=DispatchState.CANCELLED,
                    detail=f"{dispatch.detail}; closed locally, native session retained"[:500],
                )
            return dispatch

    def close(self, *, timeout: float = 5) -> None:
        """Stop every in-flight turn and release the adapters. Safe to repeat.

        This is Task 1's graceful shutdown only. Reconciling a dispatch that a
        crash left `running` is Task 4 and is deliberately not attempted here.
        """
        if self._closed:
            return
        with self._runtime_lock:
            dispatch_ids = list(self._threads)
        for dispatch_id in dispatch_ids:
            dispatch = self.store.dispatch(dispatch_id)
            if dispatch is not None and dispatch.state in ACTIVE_DISPATCH_STATES:
                try:
                    self.cancel_dispatch(dispatch_id)
                except (BrokerError, StoreError):
                    # Already finished or already cancelled between the read and
                    # the call; shutdown must not fail on that race.
                    pass
        for adapter in self._adapters.values():
            close = getattr(adapter, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    # A failed close must not prevent other adapters and
                    # dispatch threads from receiving their cleanup attempt.
                    pass
        # Only a live thread costs anything to wait for. Joining the finished
        # ones spent the timeout budget on threads that had already exited.
        with self._runtime_lock:
            threads = list(self._threads.values())
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=timeout)
        if not self.running_dispatch_ids():
            self._adapters.clear()
            self._closed = True
