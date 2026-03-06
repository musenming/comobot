"""Async SQLite database connection with WAL mode."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
from loguru import logger

PRAGMAS = {
    "journal_mode": "wal",
    "busy_timeout": "5000",
    "synchronous": "normal",
    "foreign_keys": "on",
    "cache_size": "-8000",
}


class Database:
    """Async SQLite database wrapper with WAL mode and connection pooling."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        for pragma, value in PRAGMAS.items():
            await self._conn.execute(f"PRAGMA {pragma} = {value}")
        logger.debug("SQLite connected: {} (WAL mode)", self.db_path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.debug("SQLite connection closed")

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        async with self._lock:
            cursor = await self.conn.execute(sql, params)
            await self.conn.commit()
            return cursor

    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        async with self._lock:
            await self.conn.executemany(sql, params_list)
            await self.conn.commit()

    async def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = await self.conn.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = await self.conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
