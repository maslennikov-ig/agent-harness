"""Local SQLite coordination store: ordered, scoped, idempotent visible history.

Beads still owns task truth and Git still owns artifacts. This store owns only
the shared discussion stream, the dispatch records that link it to a runtime
session, and the consumer cursors that make a reload resumable.

Connections are per thread because the panel serves blocking handlers from a
worker pool while the SSE reader polls from another thread.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from orch_panel.coordination.models import (
    ACTIVE_DISPATCH_STATES,
    AUTHOR_KINDS,
    DIGEST_PATTERN,
    EVENT_KINDS,
    ArtifactRef,
    Dispatch,
    DispatchState,
    Epic,
    PlanningArtifact,
    Project,
    SharedEvent,
    allowed_transition,
)
from orch_panel.coordination.review import (
    VERDICT_OUTCOMES,
    Finding,
    ReviewRound,
    findings_from_json,
    findings_to_json,
)

SCHEMA_VERSION = "coordination-store/v1"

# An executor owns a write zone; a judge owns nothing and only reads.
DISPATCH_ROLES = ("executor", "judge")

# Who closed one review round. A model verdict and the user's own call after the
# loop ran out are both recorded, and only one of them is a review.
DECIDED_BY = ("judge", "user")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    repo_path  TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS epics (
    epic_id        TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(project_id),
    title          TEXT NOT NULL,
    beads_issue_id TEXT,
    created_at     TEXT NOT NULL,
    source_kind    TEXT NOT NULL DEFAULT '',
    source_ref     TEXT NOT NULL DEFAULT '',
    source_url     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS dispatches (
    dispatch_id        TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL REFERENCES projects(project_id),
    epic_id            TEXT NOT NULL REFERENCES epics(epic_id),
    beads_issue_id     TEXT,
    provider           TEXT NOT NULL,
    state              TEXT NOT NULL,
    runtime_session_id TEXT,
    idempotency_key    TEXT NOT NULL UNIQUE,
    write_zone         TEXT NOT NULL DEFAULT '',
    prompt_card_id     TEXT NOT NULL DEFAULT '',
    prompt_digest      TEXT NOT NULL DEFAULT '',
    detail             TEXT NOT NULL DEFAULT '',
    role               TEXT NOT NULL DEFAULT 'executor',
    review_required    INTEGER NOT NULL DEFAULT 0,
    parent_dispatch_id TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq                INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id           TEXT NOT NULL UNIQUE,
    project_id         TEXT NOT NULL,
    epic_id            TEXT NOT NULL,
    beads_issue_id     TEXT,
    dispatch_id        TEXT,
    runtime_session_id TEXT,
    author_kind        TEXT NOT NULL,
    event_kind         TEXT NOT NULL,
    body_text          TEXT NOT NULL,
    reply_to           TEXT,
    idempotency_key    TEXT NOT NULL UNIQUE,
    created_at         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifact_refs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    path       TEXT NOT NULL,
    digest     TEXT NOT NULL,
    media_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cursors (
    consumer_id   TEXT PRIMARY KEY,
    last_seen_seq INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS planning_artifacts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     TEXT NOT NULL REFERENCES projects(project_id),
    epic_id        TEXT NOT NULL REFERENCES epics(epic_id),
    kind           TEXT NOT NULL,
    path           TEXT NOT NULL,
    digest         TEXT NOT NULL,
    beads_issue_id TEXT,
    registered_at  TEXT NOT NULL,
    UNIQUE(epic_id, kind, path)
);
CREATE TABLE IF NOT EXISTS reviews (
    review_id            TEXT PRIMARY KEY,
    project_id           TEXT NOT NULL REFERENCES projects(project_id),
    epic_id              TEXT NOT NULL REFERENCES epics(epic_id),
    beads_issue_id       TEXT,
    executor_dispatch_id TEXT NOT NULL REFERENCES dispatches(dispatch_id),
    executor_provider    TEXT NOT NULL,
    judge_dispatch_id    TEXT NOT NULL DEFAULT '',
    judge_provider       TEXT NOT NULL DEFAULT '',
    judge_session_id     TEXT NOT NULL DEFAULT '',
    round                INTEGER NOT NULL,
    outcome              TEXT NOT NULL,
    summary              TEXT NOT NULL,
    findings_json        TEXT NOT NULL DEFAULT '[]',
    revision_returned    INTEGER NOT NULL DEFAULT 0,
    decided_by           TEXT NOT NULL DEFAULT 'judge',
    created_at           TEXT NOT NULL,
    UNIQUE(executor_dispatch_id, round)
);
CREATE INDEX IF NOT EXISTS reviews_by_issue ON reviews(epic_id, beads_issue_id, round);
CREATE INDEX IF NOT EXISTS events_by_epic ON events(epic_id, seq);
CREATE INDEX IF NOT EXISTS events_by_issue ON events(epic_id, beads_issue_id, seq);
CREATE INDEX IF NOT EXISTS artifact_refs_by_event ON artifact_refs(event_id);
CREATE INDEX IF NOT EXISTS planning_artifacts_by_epic ON planning_artifacts(epic_id, kind);
"""

# An accepted specification or plan. The row is a pointer, never a copy: Git
# keeps the text, and the digest is what proves which revision was accepted.
PLANNING_KINDS = ("specification", "plan")


class StoreError(RuntimeError):
    """A rejected coordination write. Never a partially applied one."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def validate_artifact_ref(ref: ArtifactRef) -> ArtifactRef:
    """Accept only a repository-relative path and a real sha256 digest.

    Artifact paths reach the panel from agent output, so an absolute or
    escaping path is treated as hostile input rather than a typo.
    """
    path = PurePosixPath(ref.path)
    if not ref.path or path.is_absolute() or ".." in path.parts:
        raise StoreError(f"artifact path must stay inside the repository: {ref.path!r}")
    if not DIGEST_PATTERN.match(ref.digest or ""):
        raise StoreError(f"artifact digest must be a sha256 hex digest: {ref.digest!r}")
    return ArtifactRef(path=str(path), digest=ref.digest, media_type=ref.media_type or "text/plain")


class CoordinationStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._closed = False
        self._connections: list[tuple[int, sqlite3.Connection]] = []
        self._initialise()

    # -- connection handling -------------------------------------------------

    def connection(self) -> sqlite3.Connection:
        """Return this thread's connection, opening it on first use."""
        if self._closed:
            raise StoreError("coordination store is closed")
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")
            self._local.conn = conn
            with self._write_lock:
                self._connections.append((threading.get_ident(), conn))
        return conn

    def _initialise(self) -> None:
        conn = self.connection()
        with conn:
            conn.executescript(_SCHEMA)
            self._add_missing_columns(conn)
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)",
                    (SCHEMA_VERSION,),
                )
            elif row["value"] != SCHEMA_VERSION:
                # Guessing at an unknown layout would corrupt visible history.
                raise StoreError(
                    f"coordination store schema {row['value']} is not {SCHEMA_VERSION}; "
                    "migrate or archive state/coordination before continuing"
                )

    # Task 3 widens two records without changing how anything already stored is
    # read: the new columns carry defaults, and an older panel simply ignores
    # them. That is why the schema version stays `coordination-store/v1` and a
    # real migration remains Task 4's problem, not this stage's.
    _ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
        ("dispatches", "role", "TEXT NOT NULL DEFAULT 'executor'"),
        ("dispatches", "review_required", "INTEGER NOT NULL DEFAULT 0"),
        ("dispatches", "parent_dispatch_id", "TEXT NOT NULL DEFAULT ''"),
        # Where an epic came from. Empty for everything created before this,
        # which reads as "typed in by hand" and needs no backfill.
        ("epics", "source_kind", "TEXT NOT NULL DEFAULT ''"),
        ("epics", "source_ref", "TEXT NOT NULL DEFAULT ''"),
        ("epics", "source_url", "TEXT NOT NULL DEFAULT ''"),
    )

    def _add_missing_columns(self, conn: sqlite3.Connection) -> None:
        for table, column, definition in self._ADDED_COLUMNS:
            existing = {
                row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            if not existing or column in existing:
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def schema_version(self) -> str:
        row = self.connection().execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return row["value"] if row else ""

    def close(self) -> None:
        """Close this thread's connection and stop handing out new ones.

        A sqlite connection belongs to the thread that opened it, so closing
        another thread's connection here raised `ProgrammingError` that the
        blanket `except` then swallowed — the connection stayed open and the
        failure was invisible. Marking the store closed stops every other
        thread from using its connection again; the reference is dropped and
        the object closes itself when it is collected.
        """
        self._closed = True
        current = threading.get_ident()
        with self._write_lock:
            for owner, conn in self._connections:
                if owner != current:
                    continue
                try:
                    conn.close()
                except sqlite3.Error:  # pragma: no cover - best-effort teardown
                    pass
            self._connections.clear()
        self._local = threading.local()

    # -- projects and epics --------------------------------------------------

    def upsert_project(self, project_id: str, *, name: str, repo_path: str) -> Project:
        conn = self.connection()
        with self._write_lock, conn:
            conn.execute(
                """
                INSERT INTO projects(project_id, name, repo_path, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET name = excluded.name,
                                                      repo_path = excluded.repo_path
                """,
                (project_id, name, repo_path, _now()),
            )
        return self.project(project_id)  # type: ignore[return-value]

    def project(self, project_id: str) -> Project | None:
        row = self.connection().execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return Project(**dict(row)) if row else None

    def projects(self) -> list[Project]:
        rows = self.connection().execute("SELECT * FROM projects ORDER BY name").fetchall()
        return [Project(**dict(row)) for row in rows]

    def upsert_epic(
        self,
        epic_id: str,
        *,
        project_id: str,
        title: str,
        beads_issue_id: str | None = None,
        source_kind: str = "",
        source_ref: str = "",
        source_url: str = "",
    ) -> Epic:
        if self.project(project_id) is None:
            raise StoreError(f"unknown project: {project_id!r}")
        conn = self.connection()
        with self._write_lock, conn:
            conn.execute(
                """
                INSERT INTO epics(epic_id, project_id, title, beads_issue_id, created_at,
                                  source_kind, source_ref, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(epic_id) DO UPDATE SET title = excluded.title,
                                                   beads_issue_id = excluded.beads_issue_id,
                                                   source_kind = excluded.source_kind,
                                                   source_ref = excluded.source_ref,
                                                   source_url = excluded.source_url
                """,
                (
                    epic_id,
                    project_id,
                    title,
                    beads_issue_id,
                    _now(),
                    source_kind,
                    source_ref,
                    source_url,
                ),
            )
        return self.epic(epic_id)  # type: ignore[return-value]

    def epic(self, epic_id: str) -> Epic | None:
        row = self.connection().execute(
            "SELECT * FROM epics WHERE epic_id = ?", (epic_id,)
        ).fetchone()
        return Epic(**dict(row)) if row else None

    def epics(self, project_id: str | None = None) -> list[Epic]:
        sql = "SELECT * FROM epics"
        params: tuple[object, ...] = ()
        if project_id:
            sql += " WHERE project_id = ?"
            params = (project_id,)
        rows = self.connection().execute(sql + " ORDER BY created_at, epic_id", params).fetchall()
        return [Epic(**dict(row)) for row in rows]

    # -- durable planning ----------------------------------------------------

    def register_planning_artifact(
        self,
        *,
        project_id: str,
        epic_id: str,
        kind: str,
        path: str,
        digest: str,
        beads_issue_id: str | None = None,
    ) -> PlanningArtifact:
        """Link an accepted spec or plan to an epic as path plus digest.

        Re-registering the same document updates the digest rather than adding
        a row: the store tracks which revision is accepted now, while Git keeps
        the history of how it got there.
        """
        if kind not in PLANNING_KINDS:
            raise StoreError(f"planning artifact kind must be one of {PLANNING_KINDS}: {kind!r}")
        self._require_scope(epic_id, project_id)
        ref = validate_artifact_ref(ArtifactRef(path=path, digest=digest))
        conn = self.connection()
        with self._write_lock, conn:
            conn.execute(
                """
                INSERT INTO planning_artifacts(
                    project_id, epic_id, kind, path, digest, beads_issue_id, registered_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(epic_id, kind, path)
                DO UPDATE SET digest = excluded.digest,
                              beads_issue_id = excluded.beads_issue_id,
                              registered_at = excluded.registered_at
                """,
                (project_id, epic_id, kind, ref.path, ref.digest, beads_issue_id, _now()),
            )
        row = conn.execute(
            "SELECT * FROM planning_artifacts WHERE epic_id = ? AND kind = ? AND path = ?",
            (epic_id, kind, ref.path),
        ).fetchone()
        return _planning_artifact_from_row(row)

    def planning_artifacts(
        self, epic_id: str, kind: str | None = None
    ) -> list[PlanningArtifact]:
        sql = "SELECT * FROM planning_artifacts WHERE epic_id = ?"
        params: tuple[object, ...] = (epic_id,)
        if kind:
            sql += " AND kind = ?"
            params += (kind,)
        rows = self.connection().execute(sql + " ORDER BY kind, path", params).fetchall()
        return [_planning_artifact_from_row(row) for row in rows]

    # -- scope ---------------------------------------------------------------

    def _require_scope(self, epic_id: str, project_id: str) -> Epic:
        """The epic owns the project; every writer is checked in this one place.

        The check runs before the transaction and before the idempotency lookup,
        so a refused write stores nothing and leaves the key free for a
        corrected retry.
        """
        epic = self.epic(epic_id)
        if epic is None:
            raise StoreError(f"unknown epic: {epic_id!r}")
        if project_id != epic.project_id:
            raise StoreError(
                f"project {project_id!r} does not own epic {epic_id!r} "
                f"(it belongs to {epic.project_id!r})"
            )
        return epic

    # -- events --------------------------------------------------------------

    def append_event(self, event: SharedEvent) -> SharedEvent:
        """Append one visible event, or return the one this key already stored.

        Validation runs before the transaction opens, and the event row plus its
        artifact references are written inside a single transaction, so a
        rejected reference can never leave half an event in the history.
        """
        if event.author_kind not in AUTHOR_KINDS:
            raise StoreError(f"unknown author kind: {event.author_kind!r}")
        if event.event_kind not in EVENT_KINDS:
            raise StoreError(f"{event.event_kind!r} is not visible shared history")
        if not event.idempotency_key:
            raise StoreError("every event needs an idempotency key")
        self._require_scope(event.epic_id, event.project_id)
        refs = tuple(validate_artifact_ref(ref) for ref in event.artifact_refs)

        conn = self.connection()
        with self._write_lock:
            existing = self._event_by_key(conn, event.idempotency_key)
            if existing is not None:
                return existing
            event_id = event.event_id or f"evt-{uuid.uuid4()}"
            created_at = event.created_at or _now()
            with conn:
                conn.execute(
                    """
                    INSERT INTO events(event_id, project_id, epic_id, beads_issue_id,
                                       dispatch_id, runtime_session_id, author_kind,
                                       event_kind, body_text, reply_to, idempotency_key,
                                       created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        event.project_id,
                        event.epic_id,
                        event.beads_issue_id,
                        event.dispatch_id,
                        event.runtime_session_id,
                        event.author_kind,
                        event.event_kind,
                        event.body_text,
                        event.reply_to,
                        event.idempotency_key,
                        created_at,
                    ),
                )
                conn.executemany(
                    "INSERT INTO artifact_refs(event_id, path, digest, media_type)"
                    " VALUES (?, ?, ?, ?)",
                    [(event_id, ref.path, ref.digest, ref.media_type) for ref in refs],
                )
            return self.event(event_id)  # type: ignore[return-value]

    def event_by_key(self, idempotency_key: str) -> SharedEvent | None:
        """Find the event one idempotency key already appended, if any.

        A caller that keeps one key per confirmed action can ask with it whether
        that action already happened, instead of inferring it from state that
        the action itself has since moved on.
        """
        if not idempotency_key:
            return None
        return self._event_by_key(self.connection(), idempotency_key)

    def _event_by_key(self, conn: sqlite3.Connection, key: str) -> SharedEvent | None:
        row = conn.execute(
            "SELECT * FROM events WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return self._event_from_row(conn, row) if row else None

    def _event_from_row(self, conn: sqlite3.Connection, row: sqlite3.Row) -> SharedEvent:
        refs = conn.execute(
            "SELECT path, digest, media_type FROM artifact_refs WHERE event_id = ? ORDER BY id",
            (row["event_id"],),
        ).fetchall()
        return SharedEvent(
            project_id=row["project_id"],
            epic_id=row["epic_id"],
            beads_issue_id=row["beads_issue_id"],
            dispatch_id=row["dispatch_id"],
            runtime_session_id=row["runtime_session_id"],
            author_kind=row["author_kind"],
            event_kind=row["event_kind"],
            body_text=row["body_text"],
            idempotency_key=row["idempotency_key"],
            artifact_refs=tuple(
                ArtifactRef(path=ref["path"], digest=ref["digest"], media_type=ref["media_type"])
                for ref in refs
            ),
            reply_to=row["reply_to"],
            event_id=row["event_id"],
            seq=row["seq"],
            created_at=row["created_at"],
        )

    def event(self, event_id: str) -> SharedEvent | None:
        conn = self.connection()
        row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return self._event_from_row(conn, row) if row else None

    def events(
        self,
        *,
        epic_id: str | None = None,
        beads_issue_id: str | None = None,
        dispatch_id: str | None = None,
        after_seq: int = 0,
        limit: int | None = None,
    ) -> list[SharedEvent]:
        """Return one ordered projection of the shared stream.

        Every filter narrows the same rows, so an epic view and a task thread
        are two windows onto one history rather than two histories.
        """
        clauses = ["seq > ?"]
        params: list[object] = [int(after_seq)]
        if epic_id:
            clauses.append("epic_id = ?")
            params.append(epic_id)
        if beads_issue_id:
            clauses.append("beads_issue_id = ?")
            params.append(beads_issue_id)
        if dispatch_id:
            clauses.append("dispatch_id = ?")
            params.append(dispatch_id)
        sql = f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY seq"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        conn = self.connection()
        return [self._event_from_row(conn, row) for row in conn.execute(sql, params).fetchall()]

    def latest_seq(self) -> int:
        row = self.connection().execute("SELECT max(seq) AS top FROM events").fetchone()
        return int(row["top"] or 0)

    # -- cursors -------------------------------------------------------------

    def set_cursor(self, consumer_id: str, seq: int) -> None:
        conn = self.connection()
        with self._write_lock, conn:
            conn.execute(
                """
                INSERT INTO cursors(consumer_id, last_seen_seq) VALUES (?, ?)
                ON CONFLICT(consumer_id) DO UPDATE SET
                    last_seen_seq = max(excluded.last_seen_seq, cursors.last_seen_seq)
                """,
                (consumer_id, int(seq)),
            )

    def cursor(self, consumer_id: str) -> int:
        row = self.connection().execute(
            "SELECT last_seen_seq FROM cursors WHERE consumer_id = ?", (consumer_id,)
        ).fetchone()
        return int(row["last_seen_seq"]) if row else 0

    # -- dispatches ----------------------------------------------------------

    def create_dispatch(
        self,
        *,
        project_id: str,
        epic_id: str,
        provider: str,
        idempotency_key: str,
        beads_issue_id: str | None = None,
        write_zone: str = "",
        prompt_card_id: str = "",
        prompt_digest: str = "",
        role: str = "executor",
        review_required: bool = False,
        parent_dispatch_id: str = "",
        state: DispatchState = DispatchState.AWAITING_START,
    ) -> Dispatch:
        if role not in DISPATCH_ROLES:
            raise StoreError(f"dispatch role must be one of {DISPATCH_ROLES}: {role!r}")
        self._require_scope(epic_id, project_id)
        conn = self.connection()
        with self._write_lock:
            existing = conn.execute(
                "SELECT * FROM dispatches WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                return _dispatch_from_row(existing)
            dispatch_id = f"dsp-{uuid.uuid4()}"
            stamp = _now()
            with conn:
                conn.execute(
                    """
                    INSERT INTO dispatches(dispatch_id, project_id, epic_id, beads_issue_id,
                                           provider, state, runtime_session_id,
                                           idempotency_key, write_zone, prompt_card_id,
                                           prompt_digest, detail, role, review_required,
                                           parent_dispatch_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, '', ?, ?, ?, ?, ?)
                    """,
                    (
                        dispatch_id,
                        project_id,
                        epic_id,
                        beads_issue_id,
                        provider,
                        str(state),
                        idempotency_key,
                        write_zone,
                        prompt_card_id,
                        prompt_digest,
                        role,
                        1 if review_required else 0,
                        parent_dispatch_id,
                        stamp,
                        stamp,
                    ),
                )
        return self.dispatch(dispatch_id)  # type: ignore[return-value]

    def update_dispatch(
        self,
        dispatch_id: str,
        *,
        state: DispatchState | None = None,
        runtime_session_id: str | None = None,
        detail: str | None = None,
    ) -> Dispatch:
        conn = self.connection()
        with self._write_lock:
            row = conn.execute(
                "SELECT * FROM dispatches WHERE dispatch_id = ?", (dispatch_id,)
            ).fetchone()
            if row is None:
                raise StoreError(f"unknown dispatch: {dispatch_id!r}")
            current = DispatchState(row["state"])
            target = state if state is not None else current
            if not allowed_transition(current, target):
                raise StoreError(f"dispatch {dispatch_id} cannot move {current} -> {target}")
            with conn:
                conn.execute(
                    """
                    UPDATE dispatches
                       SET state = ?,
                           runtime_session_id = COALESCE(?, runtime_session_id),
                           detail = COALESCE(?, detail),
                           updated_at = ?
                     WHERE dispatch_id = ?
                    """,
                    (str(target), runtime_session_id, detail, _now(), dispatch_id),
                )
        return self.dispatch(dispatch_id)  # type: ignore[return-value]

    def dispatch(self, dispatch_id: str) -> Dispatch | None:
        row = self.connection().execute(
            "SELECT * FROM dispatches WHERE dispatch_id = ?", (dispatch_id,)
        ).fetchone()
        return _dispatch_from_row(row) if row else None

    def dispatch_by_key(self, idempotency_key: str) -> Dispatch | None:
        """Find the dispatch one idempotency key already created, if any.

        A key that already made a dispatch also already made its runtime
        session, which is what makes it unusable for a fresh judge.
        """
        if not idempotency_key:
            return None
        row = self.connection().execute(
            "SELECT * FROM dispatches WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return _dispatch_from_row(row) if row else None

    def dispatches(
        self, *, epic_id: str | None = None, beads_issue_id: str | None = None
    ) -> list[Dispatch]:
        clauses: list[str] = []
        params: list[object] = []
        if epic_id:
            clauses.append("epic_id = ?")
            params.append(epic_id)
        if beads_issue_id:
            clauses.append("beads_issue_id = ?")
            params.append(beads_issue_id)
        sql = "SELECT * FROM dispatches"
        if clauses:
            sql += f" WHERE {' AND '.join(clauses)}"
        rows = self.connection().execute(sql + " ORDER BY created_at, dispatch_id", params).fetchall()
        return [_dispatch_from_row(row) for row in rows]

    def active_dispatches(
        self, *, provider: str | None = None, project_id: str | None = None
    ) -> list[Dispatch]:
        """Only the rows in a non-terminal state, filtered in SQL.

        The broker asks this on every start, message and review to find the one
        live turn per runtime. Loading and rehydrating every dispatch the
        project ever had to answer that is work that grows without bound.
        """
        states = sorted(str(state) for state in ACTIVE_DISPATCH_STATES)
        clauses = ["state IN ({})".format(", ".join("?" for _ in states))]
        params: list[object] = list(states)
        if provider:
            clauses.append("provider = ?")
            params.append(provider)
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        rows = self.connection().execute(
            "SELECT * FROM dispatches WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at, dispatch_id",
            params,
        ).fetchall()
        return [_dispatch_from_row(row) for row in rows]

    # -- cross-provider review -----------------------------------------------

    def record_review_round(
        self,
        *,
        executor_dispatch_id: str,
        outcome: str,
        summary: str,
        findings: Sequence[Finding] = (),
        judge_dispatch_id: str = "",
        judge_provider: str = "",
        judge_session_id: str = "",
        decided_by: str = "judge",
    ) -> ReviewRound:
        """Persist one round, or return the round this executor already has.

        The round number is derived here rather than supplied, so two callers
        racing on the same verdict cannot invent two rounds for one opinion. The
        stored record is structure plus one short summary; the reviewed text
        stays in the worktree and the runtime session.
        """
        if outcome not in VERDICT_OUTCOMES:
            raise StoreError(f"unknown review outcome: {outcome!r}")
        if decided_by not in DECIDED_BY:
            raise StoreError(f"a review round is decided by {DECIDED_BY}: {decided_by!r}")
        conn = self.connection()
        with self._write_lock:
            dispatch_row = conn.execute(
                "SELECT * FROM dispatches WHERE dispatch_id = ?", (executor_dispatch_id,)
            ).fetchone()
            if dispatch_row is None:
                raise StoreError(f"unknown dispatch: {executor_dispatch_id!r}")
            if judge_dispatch_id:
                existing = conn.execute(
                    "SELECT * FROM reviews WHERE judge_dispatch_id = ?",
                    (judge_dispatch_id,),
                ).fetchone()
                if existing is not None:
                    return _review_round_from_row(existing)
            top = conn.execute(
                "SELECT max(round) AS top FROM reviews WHERE executor_dispatch_id = ?",
                (executor_dispatch_id,),
            ).fetchone()
            round_number = int(top["top"] or 0) + 1
            review_id = f"rev-{uuid.uuid4()}"
            with conn:
                conn.execute(
                    """
                    INSERT INTO reviews(review_id, project_id, epic_id, beads_issue_id,
                                        executor_dispatch_id, executor_provider,
                                        judge_dispatch_id, judge_provider,
                                        judge_session_id, round, outcome, summary,
                                        findings_json, revision_returned, decided_by,
                                        created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        review_id,
                        dispatch_row["project_id"],
                        dispatch_row["epic_id"],
                        dispatch_row["beads_issue_id"],
                        executor_dispatch_id,
                        dispatch_row["provider"],
                        judge_dispatch_id,
                        judge_provider,
                        judge_session_id,
                        round_number,
                        outcome,
                        summary,
                        findings_to_json(findings),
                        decided_by,
                        _now(),
                    ),
                )
        row = conn.execute(
            "SELECT * FROM reviews WHERE review_id = ?", (review_id,)
        ).fetchone()
        return _review_round_from_row(row)

    def mark_revision_returned(self, review_id: str) -> ReviewRound:
        conn = self.connection()
        with self._write_lock, conn:
            conn.execute(
                "UPDATE reviews SET revision_returned = 1 WHERE review_id = ?",
                (review_id,),
            )
        row = conn.execute(
            "SELECT * FROM reviews WHERE review_id = ?", (review_id,)
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown review round: {review_id!r}")
        return _review_round_from_row(row)

    def review_rounds(
        self,
        executor_dispatch_id: str | None = None,
        *,
        epic_id: str | None = None,
        beads_issue_id: str | None = None,
    ) -> list[ReviewRound]:
        clauses: list[str] = []
        params: list[object] = []
        if executor_dispatch_id:
            clauses.append("executor_dispatch_id = ?")
            params.append(executor_dispatch_id)
        if epic_id:
            clauses.append("epic_id = ?")
            params.append(epic_id)
        if beads_issue_id:
            clauses.append("beads_issue_id = ?")
            params.append(beads_issue_id)
        sql = "SELECT * FROM reviews"
        if clauses:
            sql += f" WHERE {' AND '.join(clauses)}"
        rows = self.connection().execute(
            sql + " ORDER BY executor_dispatch_id, round", params
        ).fetchall()
        return [_review_round_from_row(row) for row in rows]

    def used_session_ids(self, executor_dispatch_id: str) -> set[str]:
        """Every runtime session this task has already spoken to.

        A fresh judge may reuse none of them: not the executor's session and not
        a previous judge's.
        """
        conn = self.connection()
        used: set[str] = set()
        row = conn.execute(
            "SELECT runtime_session_id FROM dispatches WHERE dispatch_id = ?",
            (executor_dispatch_id,),
        ).fetchone()
        if row is not None and row["runtime_session_id"]:
            used.add(row["runtime_session_id"])
        for review in conn.execute(
            "SELECT judge_session_id FROM reviews WHERE executor_dispatch_id = ?",
            (executor_dispatch_id,),
        ):
            if review["judge_session_id"]:
                used.add(review["judge_session_id"])
        return used

    def current_executor_for_issue(
        self, epic_id: str, beads_issue_id: str
    ) -> Dispatch | None:
        """The executor run a Done decision is actually about.

        Review policy and review rounds both hang off one executor dispatch, so
        the gate has to name which one. It is the most recent executor run for
        this issue: `rowid` breaks a tie because `created_at` has one-second
        resolution and two runs can share it. Reading every round on the issue
        instead would let an accepted old run open Done for a newer, unreviewed
        one.
        """
        if not beads_issue_id:
            return None
        row = self.connection().execute(
            """
            SELECT * FROM dispatches
             WHERE epic_id = ? AND beads_issue_id = ? AND role = 'executor'
             ORDER BY created_at DESC, rowid DESC
             LIMIT 1
            """,
            (epic_id, beads_issue_id),
        ).fetchone()
        return _dispatch_from_row(row) if row else None

    def active_dispatch_for_session(self, runtime_session_id: str) -> Dispatch | None:
        """The one dispatch currently holding this runtime session, if any."""
        rows = self.connection().execute(
            "SELECT * FROM dispatches WHERE runtime_session_id = ?", (runtime_session_id,)
        ).fetchall()
        for row in rows:
            dispatch = _dispatch_from_row(row)
            if dispatch.state in {DispatchState.RUNNING, DispatchState.NEEDS_INPUT}:
                return dispatch
        return None


def _dispatch_from_row(row: sqlite3.Row) -> Dispatch:
    return Dispatch(
        dispatch_id=row["dispatch_id"],
        project_id=row["project_id"],
        epic_id=row["epic_id"],
        provider=row["provider"],
        state=DispatchState(row["state"]),
        idempotency_key=row["idempotency_key"],
        beads_issue_id=row["beads_issue_id"],
        runtime_session_id=row["runtime_session_id"],
        write_zone=row["write_zone"],
        prompt_card_id=row["prompt_card_id"],
        prompt_digest=row["prompt_digest"],
        detail=row["detail"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        # The Task 3 columns ride in `metadata`, the field the record already
        # reserves for row-specific extras. Widening the shared `Dispatch`
        # dataclass is Task 4's call, not this stage's.
        metadata={
            "role": row["role"],
            "review_required": bool(row["review_required"]),
            "parent_dispatch_id": row["parent_dispatch_id"],
        },
    )


def _review_round_from_row(row: sqlite3.Row) -> ReviewRound:
    return ReviewRound(
        review_id=row["review_id"],
        round=int(row["round"]),
        executor_dispatch_id=row["executor_dispatch_id"],
        executor_provider=row["executor_provider"],
        judge_dispatch_id=row["judge_dispatch_id"],
        judge_provider=row["judge_provider"],
        judge_session_id=row["judge_session_id"],
        outcome=row["outcome"],
        summary=row["summary"],
        findings=findings_from_json(row["findings_json"]),
        revision_returned=bool(row["revision_returned"]),
        decided_by=row["decided_by"],
        created_at=row["created_at"],
    )


def _planning_artifact_from_row(row: sqlite3.Row) -> PlanningArtifact:
    return PlanningArtifact(
        project_id=row["project_id"],
        epic_id=row["epic_id"],
        kind=row["kind"],
        path=row["path"],
        digest=row["digest"],
        beads_issue_id=row["beads_issue_id"],
        registered_at=row["registered_at"],
    )
