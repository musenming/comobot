"""Episodic memory store: manages workspace/episodic/ Markdown files + SQLite metadata.

Follows the same pattern as KnowhowStore (comobot/knowhow/store.py).
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from comobot.agent.episodic.models import EpisodicMemory
from comobot.db.connection import Database


class EpisodicMemoryStore:
    """Manage episodic memory Markdown files and their SQLite metadata."""

    def __init__(self, workspace: Path, db: Database):
        self._dir = workspace / "episodic"
        self._dir.mkdir(exist_ok=True)
        self._db = db

    # ------------------------------------------------------------------ ID gen

    def _gen_id(self) -> str:
        """Generate ep_YYYYMMDD_NNN format ID."""
        today = datetime.date.today().strftime("%Y%m%d")
        prefix = f"ep_{today}_"
        loop_count = 1
        while True:
            candidate = f"{prefix}{loop_count:03d}"
            if not list(self._dir.glob(f"{candidate}*.md")):
                return candidate
            loop_count += 1

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to a filesystem-safe slug."""
        slug = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff-]", "_", text)
        slug = re.sub(r"_+", "_", slug).strip("_")
        return slug[:40] if slug else "memory"

    # ----------------------------------------------------------- Markdown I/O

    def _render_markdown(self, memory: EpisodicMemory) -> str:
        """Render an episodic memory as Markdown with YAML frontmatter."""
        tags_json = json.dumps(memory.tags, ensure_ascii=False)
        created = memory.created_at.isoformat(timespec="seconds")
        lines = [
            "---",
            f"id: {memory.id}",
            f"type: {memory.type}",
            f"confidence: {memory.confidence}",
            f"source_session: {memory.source_session}",
            f"source_channel: {memory.source_channel}",
            f"tags: {tags_json}",
            f"created_at: {created}",
            f"access_count: {memory.access_count}",
            f"status: {memory.status}",
            "---",
            "",
            memory.content,
        ]
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------- CRUD

    async def create(self, memory: EpisodicMemory) -> EpisodicMemory:
        """Create a new episodic memory (file + DB record)."""
        if not memory.id:
            memory.id = self._gen_id()

        slug = self._slugify(memory.content[:60])
        filename = f"{memory.id}_{slug}.md"
        file_path = self._dir / filename
        memory.file_path = f"episodic/{filename}"

        content = self._render_markdown(memory)
        file_path.write_text(content, encoding="utf-8")

        tags_json = json.dumps(memory.tags, ensure_ascii=False)
        await self._db.execute(
            "INSERT INTO episodic_memories "
            "(id, type, content, confidence, source_session, source_channel, "
            "tags, file_path, created_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                memory.id,
                memory.type,
                memory.content,
                memory.confidence,
                memory.source_session,
                memory.source_channel,
                tags_json,
                memory.file_path,
                memory.created_at.isoformat(),
                memory.status,
            ),
        )
        logger.info("Episodic memory created: {} ({})", memory.id, memory.type)
        return memory

    async def get(self, memory_id: str) -> dict[str, Any] | None:
        """Get a single episodic memory by ID."""
        row = await self._db.fetchone("SELECT * FROM episodic_memories WHERE id = ?", (memory_id,))
        if not row:
            return None
        result = dict(row)
        try:
            result["tags"] = json.loads(result.get("tags", "[]"))
        except (json.JSONDecodeError, TypeError):
            result["tags"] = []
        # Read Markdown content from file
        md_path = self._dir.parent / result.get("file_path", "")
        if md_path.exists():
            result["file_content"] = md_path.read_text(encoding="utf-8")
        return result

    async def list_all(
        self,
        type_filter: str | None = None,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List episodic memories with optional filtering."""
        sql = "SELECT * FROM episodic_memories WHERE status = ?"
        params: list[Any] = [status]
        if type_filter:
            sql += " AND type = ?"
            params.append(type_filter)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = await self._db.fetchall(sql, tuple(params))
        results = []
        for row in rows:
            d = dict(row)
            try:
                d["tags"] = json.loads(d.get("tags", "[]"))
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
            results.append(d)
        return results

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
    ) -> bool:
        """Update an episodic memory."""
        sets: list[str] = []
        params: list[Any] = []
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if tags is not None:
            sets.append("tags = ?")
            params.append(json.dumps(tags, ensure_ascii=False))
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if not sets:
            return False
        params.append(memory_id)
        await self._db.execute(
            f"UPDATE episodic_memories SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )
        return True

    async def delete(self, memory_id: str) -> bool:
        """Archive (soft-delete) an episodic memory."""
        return await self.update(memory_id, status="archived")

    async def record_access(self, memory_id: str) -> None:
        """Record that a memory was accessed (for relevance scoring)."""
        await self._db.execute(
            "UPDATE episodic_memories SET "
            "access_count = access_count + 1, "
            "last_accessed_at = datetime('now') "
            "WHERE id = ?",
            (memory_id,),
        )

    async def stats(self) -> dict[str, Any]:
        """Return memory statistics."""
        total = await self._db.fetchone(
            "SELECT COUNT(*) as total FROM episodic_memories WHERE status = 'active'"
        )
        by_type = await self._db.fetchall(
            "SELECT type, COUNT(*) as count FROM episodic_memories "
            "WHERE status = 'active' GROUP BY type"
        )
        most_used = await self._db.fetchall(
            "SELECT id, content, access_count FROM episodic_memories "
            "WHERE status = 'active' ORDER BY access_count DESC LIMIT 5"
        )
        return {
            "total": total["total"] if total else 0,
            "by_type": {r["type"]: r["count"] for r in by_type},
            "most_used": [dict(r) for r in most_used],
        }
