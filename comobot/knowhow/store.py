"""Know-how store: manages workspace/knowhow/ Markdown files + SQLite metadata."""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from comobot.db.connection import Database


class KnowhowStore:
    """Manage Know-how Markdown files and their SQLite metadata index."""

    def __init__(self, workspace: Path, db: Database):
        self._dir = workspace / "knowhow"
        self._dir.mkdir(exist_ok=True)
        self._db = db

    def _gen_id(self) -> str:
        """Generate kh_YYYYMMDD_NNN format ID."""
        today = datetime.date.today().strftime("%Y%m%d")
        prefix = f"kh_{today}_"
        # Synchronous — we'll use a simple approach
        loop_count = 1
        while True:
            candidate = f"{prefix}{loop_count:03d}"
            # Check file existence as a quick uniqueness test
            matches = list(self._dir.glob(f"{candidate}_*.md"))
            if not matches:
                return candidate
            loop_count += 1

    @staticmethod
    def _slugify(title: str) -> str:
        """Convert title to filesystem-safe slug."""
        # Keep alphanumeric, CJK characters, hyphens, underscores
        slug = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff-]", "_", title)
        slug = re.sub(r"_+", "_", slug).strip("_")
        return slug[:50] if slug else "untitled"

    def _render_markdown(
        self, kh_id: str, preview: dict, raw_messages: list[dict], source_session: str = ""
    ) -> str:
        """Render a Know-how Markdown file with frontmatter."""
        now = datetime.datetime.now().isoformat(timespec="seconds")
        tags_json = json.dumps(preview.get("tags", []), ensure_ascii=False)
        steps = preview.get("steps", [])
        tools = preview.get("tools_used", [])
        msg_ids = preview.get("source_messages", [])

        lines = [
            "---",
            f"id: {kh_id}",
            f"title: {preview.get('title', '')}",
            f"tags: {tags_json}",
            f"goal: {preview.get('goal', '')}",
            f"source_session: {source_session}",
            f"source_messages: {json.dumps(msg_ids)}",
            f"created_at: {now}",
            f"updated_at: {now}",
            "status: active",
            "---",
            "",
            f"# {preview.get('title', '')}",
            "",
            "## 目标",
            preview.get("goal", ""),
            "",
            "## 关键步骤",
        ]
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")

        if tools:
            lines += ["", "## 使用工具"]
            for t in tools:
                lines.append(f"- `{t}`")

        if preview.get("outcome"):
            lines += ["", "## 结果", preview["outcome"]]

        # Raw conversation snapshot
        if raw_messages:
            lines += ["", "## 原始对话片段"]
            for m in raw_messages:
                role = m.get("role", "unknown")
                content = (m.get("content") or "")[:500]
                lines.append(f"> {role}: {content}")

        return "\n".join(lines) + "\n"

    async def create(
        self,
        preview: dict,
        raw_messages: list[dict],
        source_session: str = "",
        message_ids: list[int] | None = None,
    ) -> dict:
        """Create a new Know-how entry (file + DB record)."""
        kh_id = self._gen_id()
        slug = self._slugify(preview.get("title", ""))
        filename = f"{kh_id}_{slug}.md"
        file_path = self._dir / filename

        if message_ids:
            preview["source_messages"] = message_ids

        content = self._render_markdown(kh_id, preview, raw_messages, source_session)
        file_path.write_text(content, encoding="utf-8")

        tags_json = json.dumps(preview.get("tags", []), ensure_ascii=False)
        msg_ids_json = json.dumps(message_ids or [])

        await self._db.execute(
            "INSERT INTO knowhow (id, title, tags, goal, file_path, source_session, "
            "source_messages, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
            (
                kh_id,
                preview.get("title", ""),
                tags_json,
                preview.get("goal", ""),
                f"knowhow/{filename}",
                source_session,
                msg_ids_json,
            ),
        )

        logger.info("Know-how created: {} ({})", kh_id, preview.get("title", ""))
        return {
            "id": kh_id,
            "title": preview.get("title", ""),
            "tags": preview.get("tags", []),
            "goal": preview.get("goal", ""),
            "file_path": f"knowhow/{filename}",
            "source_session": source_session,
            "status": "active",
            "usage_count": 0,
        }

    async def get(self, knowhow_id: str) -> dict[str, Any] | None:
        """Get a single Know-how entry by ID."""
        row = await self._db.fetchone("SELECT * FROM knowhow WHERE id = ?", (knowhow_id,))
        if not row:
            return None
        result = dict(row)
        # Read Markdown content
        md_path = self._dir.parent / result["file_path"]
        if md_path.exists():
            result["content"] = md_path.read_text(encoding="utf-8")
        else:
            result["content"] = ""
        # Parse tags from JSON
        try:
            result["tags"] = json.loads(result.get("tags", "[]"))
        except (json.JSONDecodeError, TypeError):
            result["tags"] = []
        return result

    async def list_all(
        self,
        status: str = "active",
        tags: list[str] | None = None,
        sort: str = "updated_at",
    ) -> list[dict]:
        """List Know-how entries with optional filtering."""
        sql = "SELECT * FROM knowhow WHERE status = ?"
        params: list[Any] = [status]
        if tags:
            for tag in tags:
                sql += " AND tags LIKE ?"
                params.append(f'%"{tag}"%')

        if sort == "usage_count":
            sql += " ORDER BY usage_count DESC"
        else:
            sql += " ORDER BY updated_at DESC"

        rows = await self._db.fetchall(sql, tuple(params))
        results = []
        for row in rows or []:
            item = dict(row)
            try:
                item["tags"] = json.loads(item.get("tags", "[]"))
            except (json.JSONDecodeError, TypeError):
                item["tags"] = []
            # Add upgrade suggestion for high-usage items
            if item.get("usage_count", 0) >= 10:
                item["suggest_upgrade"] = True
            results.append(item)
        return results

    async def update(self, knowhow_id: str, **fields: Any) -> dict | None:
        """Update a Know-how entry's metadata."""
        row = await self._db.fetchone("SELECT * FROM knowhow WHERE id = ?", (knowhow_id,))
        if not row:
            return None

        allowed = {"title", "tags", "status"}
        updates = []
        params: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "tags" and isinstance(value, list):
                value = json.dumps(value, ensure_ascii=False)
            updates.append(f"{key} = ?")
            params.append(value)

        if not updates:
            return dict(row)

        updates.append("updated_at = datetime('now')")
        params.append(knowhow_id)
        await self._db.execute(
            f"UPDATE knowhow SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )

        # Re-fetch updated record
        return await self.get(knowhow_id)

    async def delete(self, knowhow_id: str) -> bool:
        """Delete a Know-how entry (DB record + Markdown file)."""
        row = await self._db.fetchone("SELECT file_path FROM knowhow WHERE id = ?", (knowhow_id,))
        if not row:
            return False

        # Delete file
        md_path = self._dir.parent / row["file_path"]
        if md_path.exists():
            md_path.unlink()

        # Delete DB record
        await self._db.execute("DELETE FROM knowhow WHERE id = ?", (knowhow_id,))
        logger.info("Know-how deleted: {}", knowhow_id)
        return True

    async def increment_usage(self, knowhow_id: str) -> None:
        """Increment usage_count when a Know-how is retrieved."""
        await self._db.execute(
            "UPDATE knowhow SET usage_count = usage_count + 1 WHERE id = ?",
            (knowhow_id,),
        )
