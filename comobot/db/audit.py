"""Audit logging to SQLite with optional WebSocket broadcast."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from comobot.db.connection import Database


class AuditLogger:
    """Write audit events to the audit_log table and broadcast to WS subscribers."""

    def __init__(self, db: Database):
        self.db = db
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to real-time log events. Returns an asyncio.Queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def _broadcast(self, data: dict) -> None:
        """Push log entry to all subscribers (non-blocking)."""
        for q in self._subscribers:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    async def log(
        self,
        level: str,
        module: str,
        event: str,
        detail: str | None = None,
        session_key: str | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO audit_log (level, module, event, detail, session_key) "
            "VALUES (?, ?, ?, ?, ?)",
            (level, module, event, detail, session_key),
        )
        await self._broadcast(
            {
                "level": level,
                "module": module,
                "event": event,
                "detail": detail,
                "session_key": session_key,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def info(self, module: str, event: str, **kwargs) -> None:
        await self.log("info", module, event, **kwargs)

    async def warn(self, module: str, event: str, **kwargs) -> None:
        await self.log("warn", module, event, **kwargs)

    async def error(self, module: str, event: str, **kwargs) -> None:
        await self.log("error", module, event, **kwargs)
