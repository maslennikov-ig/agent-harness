"""One loopback ASGI host for the panel plus the official A2A routes.

The panel keeps its blocking synchronous handlers; this module is only the
transport. Every panel call is pushed to a worker thread so filesystem, Beads,
Git, and subprocess work never runs on the event loop.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qs, urlsplit

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Match, Route

from orch_panel.coordination.a2a_gateway import CoordinationAgentExecutor

A2A_RPC_PREFIX = "/a2a/"
AGENT_CARD_PATH = "/.well-known/agent-card.json"
A2A_ECHO_SKILL_ID = "panel_echo"
A2A_COORDINATION_SKILL_ID = "panel_coordination_append"
COORDINATION_STREAM_PATH = "/api/coordination/stream"
# One second is under the browser's reconnect delay and far above the cost of an
# indexed `seq >` read, so a busy epic still feels live without polling hard.
STREAM_POLL_SECONDS = 1.0
STREAM_HEARTBEAT_SECONDS = 15.0


def panel_agent_card(base_url: str) -> AgentCard:
    return AgentCard(
        name="Orchestration Console Panel",
        description=(
            "Local orchestration console host exposing one bounded A2A echo skill "
            "and one coordination append skill."
        ),
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                protocol_version="1.0",
                url=f"{base_url}{A2A_RPC_PREFIX}",
            )
        ],
        skills=[
            AgentSkill(
                id=A2A_ECHO_SKILL_ID,
                name="Panel Echo",
                description="Echo one text message back over the official A2A SDK.",
                tags=["compatibility", "echo"],
            ),
            AgentSkill(
                id=A2A_COORDINATION_SKILL_ID,
                name="Coordination Append",
                description=(
                    "Append one visible event to the local epic stream. Requires "
                    "`coordination` metadata naming the project and epic."
                ),
                tags=["coordination", "epic-workspace"],
            ),
        ],
    )


def _send(response: Any, *, body: bytes) -> Response:
    """Serialise a PanelResponse verbatim.

    The panel's own `Content-Length` is kept so a HEAD reply still declares the
    length its GET would return.
    """
    return Response(
        content=body,
        status_code=response.status,
        headers=dict(response.headers),
    )


class PanelEndpoint:
    """ASGI endpoint for every path the official A2A routes do not own.

    Registered as a class instance on purpose: a raw ASGI endpoint leaves
    `Route.methods` unset, so every verb reaches the panel and it decides the
    status itself. HEAD answers with the headers its GET would return and no
    body, the way Starlette does; every other unsupported verb gets 405.
    """

    def __init__(self, panel: Any) -> None:
        self.panel = panel

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        request = Request(scope, receive)
        response = await self.respond(request)
        await response(scope, receive, send)

    async def respond(self, request: Request) -> Response:
        path = request.scope.get("path", "/")
        method = request.method
        if method in {"GET", "HEAD"}:
            query = parse_qs(request.scope.get("query_string", b"").decode("latin-1"))
            result = await run_in_threadpool(self.panel.panel_get, path, query)
            return _send(result, body=b"" if method == "HEAD" else result.body)
        if method == "POST":
            if not request_is_same_site(request):
                # Loopback binding does not stop a page in the user's browser
                # from firing a "simple" cross-origin POST at the panel; every
                # POST here mutates local state or starts a runtime turn.
                result = self.panel.json_response(
                    {"error": "cross-site request rejected"}, 403
                )
                return _send(result, body=result.body)
            raw_body = await request.body()
            result = await run_in_threadpool(self.panel.panel_post, path, raw_body)
            return _send(result, body=result.body)
        result = self.panel.method_not_allowed_response(method)
        return _send(result, body=result.body)


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def request_is_same_site(request: Request) -> bool:
    """Accept a mutating request only from the panel's own loopback origin.

    Browsers attach `Origin` to every cross-origin POST and `Sec-Fetch-Site`
    to every fetch; scripts and curl send neither and stay allowed. A `null`
    origin (sandboxed frame, `file://`) is treated as foreign.
    """
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if fetch_site == "cross-site":
        return False
    origin = request.headers.get("origin")
    if origin is None:
        return True
    hostname = urlsplit(origin.strip()).hostname
    return hostname is not None and hostname.lower() in LOOPBACK_HOSTS


class PanelFallbackRoute(Route):
    """Catch-all route that never claims a path another route owns.

    Starlette prefers a full match over a partial one, so an unrestricted
    catch-all would answer a POST to the agent-card path itself and replace the
    A2A router's 405 with the panel's 404. Standing down whenever an owned route
    recognises the path keeps those routing semantics untouched.
    """

    def __init__(self, endpoint: Any, *, owned_routes: Any) -> None:
        super().__init__("/{path:path}", endpoint)
        self.owned_routes = tuple(owned_routes)

    def matches(self, scope: Any) -> Any:
        for route in self.owned_routes:
            if route.matches(scope)[0] is not Match.NONE:
                return Match.NONE, {}
        return super().matches(scope)


def _sse_frame(event: dict[str, Any]) -> str:
    """One `id:`-tagged SSE record; the id is the store's shared order."""
    payload = json.dumps(event, ensure_ascii=False)
    return f"id: {event['seq']}\nevent: coordination\ndata: {payload}\n\n"


class CoordinationStreamEndpoint:
    """Server-Sent Events over the shared coordination stream.

    The cursor is the store's `seq`, so a browser reconnect replays exactly the
    events it missed: `Last-Event-ID` is the resume contract, not a heuristic.
    Reads run in the threadpool because the store is blocking SQLite.
    """

    def __init__(self, panel: Any) -> None:
        self.panel = panel

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        request = Request(scope, receive)
        if request.method != "GET":
            # Starlette adds HEAD to any GET route. An endless stream is the
            # wrong answer to HEAD, so every other verb gets 405 here.
            result = self.panel.method_not_allowed_response(request.method)
            await _send(result, body=b"" if request.method == "HEAD" else result.body)(
                scope, receive, send
            )
            return
        epic_id = request.query_params.get("epic_id", "")
        if not epic_id:
            response: Response = Response(
                content=b'{"error": "missing epic_id"}',
                status_code=400,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return
        cursor = _stream_cursor(request)
        stream = StreamingResponse(
            self._events(epic_id, cursor),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "Connection": "keep-alive",
                # Loopback has no proxy today, but an SSE stream that a future
                # one buffers looks exactly like a hung panel.
                "X-Accel-Buffering": "no",
            },
        )
        await stream(scope, receive, send)

    async def _events(self, epic_id: str, cursor: int) -> Any:
        # Starlette cancels this generator on disconnect, so cleanup lives in
        # `finally` rather than after the loop.
        idle = 0.0
        try:
            yield f"retry: {int(STREAM_POLL_SECONDS * 2000)}\n\n"
            while True:
                batch = await run_in_threadpool(
                    self.panel.coordination_events_payload,
                    epic_id,
                    after_seq=cursor,
                    limit=200,
                )
                for event in batch["events"]:
                    cursor = event["seq"]
                    idle = 0.0
                    yield _sse_frame(event)
                if idle >= STREAM_HEARTBEAT_SECONDS:
                    idle = 0.0
                    yield ": heartbeat\n\n"
                await asyncio.sleep(STREAM_POLL_SECONDS)
                idle += STREAM_POLL_SECONDS
        finally:
            pass


def _stream_cursor(request: Request) -> int:
    """Resume from the browser's `Last-Event-ID`, falling back to `after_seq`."""
    for raw in (request.headers.get("last-event-id"), request.query_params.get("after_seq")):
        try:
            if raw:
                return max(0, int(raw))
        except (TypeError, ValueError):
            continue
    return 0


def build_app(panel: Any, *, host: str, port: int) -> Starlette:
    """Build the single Starlette app that serves the panel and A2A.

    `panel` is the loaded `orchestration_panel` module. It is injected rather
    than imported so tests can drive the same module object they patch.
    """
    base_url = f"http://{host}:{port}"
    card = panel_agent_card(base_url)
    request_handler = DefaultRequestHandler(
        agent_executor=CoordinationAgentExecutor(
            store_provider=lambda: panel.coordination_store()
        ),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )

    @asynccontextmanager
    async def lifespan(app: Starlette):
        # A killed process never reaches shutdown. Settle its persisted active
        # rows before serving any request so stale `running` state cannot block
        # a newly confirmed dispatch.
        await run_in_threadpool(panel.coordination_startup)
        yield
        await request_handler.aclose()
        # Coordination owns threads, adapters, and a SQLite handle, so a normal
        # shutdown has to release them. `coordination_shutdown` is idempotent.
        await run_in_threadpool(panel.coordination_shutdown)

    owned_routes = [
        *create_agent_card_routes(card, card_url=AGENT_CARD_PATH),
        *create_jsonrpc_routes(request_handler, A2A_RPC_PREFIX),
        Route(COORDINATION_STREAM_PATH, CoordinationStreamEndpoint(panel), methods=["GET"]),
    ]
    routes = [*owned_routes, PanelFallbackRoute(PanelEndpoint(panel), owned_routes=owned_routes)]
    return Starlette(routes=routes, lifespan=lifespan)
