"""Persistent session/message storage for multi-user chat."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    username: str
    hashed_password: str
    created_at: str


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SessionSummaryRecord(SessionRecord):
    last_message: str | None = None


@dataclass(frozen=True)
class MessageRecord:
    message_id: int
    session_id: str
    role: str
    content: str
    created_at: str


class SqliteSessionStore:
    """Simple SQLite-backed session/message store.

    Notes
    -----
    - One SQLite connection is opened per operation (thread-safe pattern).
    - Operations are serialized by an asyncio lock for predictable ordering.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            await asyncio.to_thread(self._initialize_sync)

    async def finalize(self) -> None:
        return None

    def _initialize_sync(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username
                ON users(username)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
                ON sessions(user_id, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_session_id
                ON messages(session_id, message_id)
                """
            )

    async def create_user(
        self,
        username: str,
        hashed_password: str,
    ) -> UserRecord:
        user_id = str(uuid4())
        now = _utc_now_iso()
        async with self._lock:
            await asyncio.to_thread(
                self._create_user_sync, user_id, username, hashed_password, now
            )
        return UserRecord(
            user_id=user_id,
            username=username,
            hashed_password=hashed_password,
            created_at=now,
        )

    def _create_user_sync(
        self, user_id: str, username: str, hashed_password: str, now: str
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, username, hashed_password, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, username, hashed_password, now),
            )

    async def get_user_by_username(self, username: str) -> UserRecord | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_user_by_username_sync, username)

    def _get_user_by_username_sync(self, username: str) -> UserRecord | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT user_id, username, hashed_password, created_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return UserRecord(
            user_id=row["user_id"],
            username=row["username"],
            hashed_password=row["hashed_password"],
            created_at=row["created_at"],
        )

    async def create_session(
        self,
        user_id: str,
        *,
        title: str = "",
        session_id: str | None = None,
    ) -> SessionRecord:
        user_id = user_id.strip()
        if not user_id:
            raise ValueError("user_id cannot be empty")

        sid = session_id or str(uuid4())
        now = _utc_now_iso()
        clean_title = title.strip()

        async with self._lock:
            await asyncio.to_thread(
                self._create_session_sync,
                sid,
                user_id,
                clean_title,
                now,
            )
        return SessionRecord(
            session_id=sid,
            user_id=user_id,
            title=clean_title,
            created_at=now,
            updated_at=now,
        )

    def _create_session_sync(
        self,
        session_id: str,
        user_id: str,
        title: str,
        now: str,
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_id, title, now, now),
            )

    async def get_session(self, session_id: str) -> SessionRecord | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_session_sync, session_id)

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        async with self._lock:
            return await asyncio.to_thread(
                self._delete_session_sync, session_id, user_id
            )

    def _delete_session_sync(self, session_id: str, user_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            result = conn.execute(
                "DELETE FROM sessions WHERE session_id = ? AND user_id = ?",
                (session_id, user_id),
            )
            return result.rowcount > 0

    def _get_session_sync(self, session_id: str) -> SessionRecord | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT session_id, user_id, title, created_at, updated_at
                FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return SessionRecord(
            session_id=row["session_id"],
            user_id=row["user_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def list_sessions(
        self,
        user_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SessionSummaryRecord]:
        clean_user = user_id.strip()
        if not clean_user:
            raise ValueError("user_id cannot be empty")
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        async with self._lock:
            return await asyncio.to_thread(
                self._list_sessions_sync,
                clean_user,
                limit,
                offset,
            )

    def _list_sessions_sync(
        self,
        user_id: str,
        limit: int,
        offset: int,
    ) -> list[SessionSummaryRecord]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                    s.session_id,
                    s.user_id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    (
                        SELECT m.content
                        FROM messages m
                        WHERE m.session_id = s.session_id
                        ORDER BY m.message_id DESC
                        LIMIT 1
                    ) AS last_message
                FROM sessions s
                WHERE s.user_id = ?
                ORDER BY s.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()

        return [
            SessionSummaryRecord(
                session_id=row["session_id"],
                user_id=row["user_id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                last_message=row["last_message"],
            )
            for row in rows
        ]

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> MessageRecord:
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("content cannot be empty")
        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")

        now = _utc_now_iso()
        async with self._lock:
            message_id = await asyncio.to_thread(
                self._append_message_sync,
                session_id,
                role,
                clean_content,
                now,
            )

        return MessageRecord(
            message_id=message_id,
            session_id=session_id,
            role=role,
            content=clean_content,
            created_at=now,
        )

    def _append_message_sync(
        self,
        session_id: str,
        role: str,
        content: str,
        now: str,
    ) -> int:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            result = conn.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, now),
            )
            if result.lastrowid is None:
                raise RuntimeError("failed to persist message")
            conn.execute(
                """
                UPDATE sessions
                SET updated_at = ?
                WHERE session_id = ?
                """,
                (now, session_id),
            )
            return int(result.lastrowid)

    async def list_messages(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MessageRecord]:
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        async with self._lock:
            return await asyncio.to_thread(
                self._list_messages_sync,
                session_id,
                limit,
                offset,
            )

    def _list_messages_sync(
        self,
        session_id: str,
        limit: int,
        offset: int,
    ) -> list[MessageRecord]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT message_id, session_id, role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY message_id ASC
                LIMIT ? OFFSET ?
                """,
                (session_id, limit, offset),
            ).fetchall()

        return [
            MessageRecord(
                message_id=int(row["message_id"]),
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def get_recent_rounds(
        self,
        session_id: str,
        *,
        max_rounds: int,
    ) -> list[tuple[str, str]]:
        if max_rounds <= 0:
            return []
        messages = await self.list_messages(session_id, limit=2000, offset=0)
        rounds: list[tuple[str, str]] = []
        pending_user: str | None = None
        for message in messages:
            if message.role == "user":
                pending_user = message.content
                continue
            if message.role == "assistant" and pending_user is not None:
                rounds.append((pending_user, message.content))
                pending_user = None
        if len(rounds) > max_rounds:
            return rounds[-max_rounds:]
        return rounds
