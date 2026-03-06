"""SQLite-backed session manager for comobot."""

from __future__ import annotations

import json
from typing import Any

from comobot.db.connection import Database
from comobot.session.manager import Session


class SQLiteSessionManager:
    """Session manager using SQLite for persistence."""

    def __init__(self, db: Database):
        self.db = db
        self._cache: dict[str, Session] = {}

    async def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]

        session = await self._load(key)
        if session is None:
            session = Session(key=key)
            await self.db.execute("INSERT INTO sessions (session_key) VALUES (?)", (key,))

        self._cache[key] = session
        return session

    async def _load(self, key: str) -> Session | None:
        row = await self.db.fetchone(
            "SELECT id, session_key, created_at, updated_at, last_consolidated "
            "FROM sessions WHERE session_key = ?",
            (key,),
        )
        if not row:
            return None

        msgs = await self.db.fetchall(
            "SELECT role, content, tool_calls, tool_call_id, created_at "
            "FROM messages WHERE session_id = ? ORDER BY id",
            (row["id"],),
        )

        messages = []
        for m in msgs:
            entry: dict[str, Any] = {
                "role": m["role"],
                "content": m["content"] or "",
                "timestamp": m["created_at"],
            }
            if m["tool_calls"]:
                entry["tool_calls"] = json.loads(m["tool_calls"])
            if m["tool_call_id"]:
                entry["tool_call_id"] = m["tool_call_id"]
            messages.append(entry)

        return Session(
            key=key,
            messages=messages,
            last_consolidated=row["last_consolidated"] or 0,
        )

    async def save(self, session: Session) -> None:
        row = await self.db.fetchone(
            "SELECT id FROM sessions WHERE session_key = ?", (session.key,)
        )
        if not row:
            cursor = await self.db.execute(
                "INSERT INTO sessions (session_key, last_consolidated) VALUES (?, ?)",
                (session.key, session.last_consolidated),
            )
            session_id = cursor.lastrowid
        else:
            session_id = row["id"]
            await self.db.execute(
                "UPDATE sessions SET updated_at = datetime('now'), "
                "last_consolidated = ? WHERE id = ?",
                (session.last_consolidated, session_id),
            )

        await self.db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))

        for msg in session.messages:
            tool_calls = json.dumps(msg["tool_calls"]) if "tool_calls" in msg else None
            await self.db.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    msg["role"],
                    msg.get("content", ""),
                    tool_calls,
                    msg.get("tool_call_id"),
                ),
            )

        self._cache[session.key] = session

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    async def list_sessions(self) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT session_key, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        )
        return [
            {
                "key": r["session_key"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
