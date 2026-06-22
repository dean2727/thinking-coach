from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .paths import state_db_path
from .schema import Goal
from .settings import MirrorSettings


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MirrorState:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or state_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dirty_sessions (
                    session_id TEXT PRIMARY KEY,
                    transcript_path TEXT NOT NULL,
                    mtime REAL,
                    reason TEXT,
                    queued_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ingest_watermarks (
                    transcript_path TEXT PRIMARY KEY,
                    session_id TEXT,
                    line_index INTEGER NOT NULL DEFAULT 0,
                    last_uuid TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    mem0_id TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_links (
                    local_id TEXT PRIMARY KEY,
                    mem0_id TEXT,
                    mirror_type TEXT NOT NULL,
                    session_id TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS digest_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    transcript_path TEXT,
                    error TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS digest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    sessions_seen INTEGER NOT NULL DEFAULT 0,
                    sessions_processed INTEGER NOT NULL DEFAULT 0,
                    memories_written INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def load_settings(self) -> MirrorSettings:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'mirror'").fetchone()
        if not row:
            settings = MirrorSettings.defaults()
            self.save_settings(settings)
            return settings
        return MirrorSettings.model_validate_json(row["value"])

    def save_settings(self, settings: MirrorSettings) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES('mirror', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (settings.model_dump_json(), utc_iso()),
            )

    def enqueue_session(self, session_id: str, transcript_path: str, *, mtime: float | None = None, reason: str = "hook") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO dirty_sessions(session_id, transcript_path, mtime, reason, queued_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    transcript_path = excluded.transcript_path,
                    mtime = excluded.mtime,
                    reason = excluded.reason,
                    queued_at = excluded.queued_at
                """,
                (session_id, transcript_path, mtime, reason, utc_iso()),
            )

    def dirty_sessions(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM dirty_sessions ORDER BY queued_at"))

    def clear_dirty_session(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM dirty_sessions WHERE session_id = ?", (session_id,))

    def watermark(self, transcript_path: str) -> tuple[int, str | None]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT line_index, last_uuid FROM ingest_watermarks WHERE transcript_path = ?",
                (transcript_path,),
            ).fetchone()
        if not row:
            return 0, None
        return int(row["line_index"]), row["last_uuid"]

    def save_watermark(self, transcript_path: str, session_id: str, line_index: int, last_uuid: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ingest_watermarks(transcript_path, session_id, line_index, last_uuid, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(transcript_path) DO UPDATE SET
                    session_id = excluded.session_id,
                    line_index = excluded.line_index,
                    last_uuid = excluded.last_uuid,
                    updated_at = excluded.updated_at
                """,
                (transcript_path, session_id, line_index, last_uuid, utc_iso()),
            )

    def save_goal(self, goal: Goal) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO goals(id, payload, active, mem0_id, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    active = excluded.active,
                    mem0_id = excluded.mem0_id,
                    updated_at = excluded.updated_at
                """,
                (goal.id, goal.model_dump_json(), int(goal.active), goal.mem0_id, utc_iso()),
            )

    def goals(self, active_only: bool = False) -> list[Goal]:
        query = "SELECT payload FROM goals"
        if active_only:
            query += " WHERE active = 1"
        with self.connect() as conn:
            rows = conn.execute(query).fetchall()
        return [Goal.model_validate_json(row["payload"]) for row in rows]

    def record_memory_link(self, local_id: str, mem0_id: str | None, mirror_type: str, session_id: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_links(local_id, mem0_id, mirror_type, session_id, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(local_id) DO UPDATE SET
                    mem0_id = excluded.mem0_id,
                    mirror_type = excluded.mirror_type,
                    session_id = excluded.session_id,
                    updated_at = excluded.updated_at
                """,
                (local_id, mem0_id, mirror_type, session_id, utc_iso()),
            )

    def record_digest_error(self, session_id: str | None, transcript_path: str | None, error: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO digest_errors(session_id, transcript_path, error, created_at) VALUES(?, ?, ?, ?)",
                (session_id, transcript_path, error, utc_iso()),
            )

    def reset(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()
        self.init()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())
