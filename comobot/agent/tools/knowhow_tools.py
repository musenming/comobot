"""Know-how tools: search and save experience for agent use."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from comobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from comobot.agent.memory_search import MemorySearchEngine
    from comobot.knowhow.store import KnowhowStore


class KnowhowSearchTool(Tool):
    """Search past successful experiences (Know-how)."""

    def __init__(self, engine: MemorySearchEngine, store: KnowhowStore):
        self._engine = engine
        self._store = store

    @property
    def name(self) -> str:
        return "knowhow_search"

    @property
    def description(self) -> str:
        return (
            "Search past successful experiences (Know-how) for relevant procedural knowledge. "
            "Returns matched experiences with goals, steps, and outcomes."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — describe the problem or task.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results (default: 3).",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 3)

        if not query.strip():
            return "Error: query cannot be empty."

        try:
            chunks = self._engine.search(query, max_results=max_results, file_filter="knowhow/")
        except Exception as e:
            return f"Error searching Know-how: {e}"

        if not chunks:
            return "No matching Know-how found."

        # Increment usage for matched items (if store available)
        if self._store:
            for chunk in chunks:
                fname = (
                    chunk.file_path.split("/")[-1] if "/" in chunk.file_path else chunk.file_path
                )
                parts = fname.split("_", 3)
                if len(parts) >= 3:
                    kh_id = "_".join(parts[:3])
                    try:
                        await self._store.increment_usage(kh_id)
                    except Exception:
                        pass

        output_parts = []
        for i, chunk in enumerate(chunks, 1):
            output_parts.append(
                f"**[{i}]** `{chunk.file_path}` (score: {chunk.score:.3f})\n{chunk.content[:700]}"
            )

        return "\n\n---\n\n".join(output_parts)


class KnowhowSaveTool(Tool):
    """Save current conversation experience as Know-how."""

    def __init__(self, store: KnowhowStore):
        self._store = store
        self._session_key: str = ""

    def set_context(self, channel: str, chat_id: str) -> None:
        self._session_key = f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "knowhow_save"

    @property
    def description(self) -> str:
        return (
            "Save a successful experience as Know-how for future reference. "
            "Use after completing a complex task to record the approach."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Experience title (≤20 chars).",
                },
                "goal": {
                    "type": "string",
                    "description": "What the user wanted to achieve.",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key steps taken.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Classification tags (2-5).",
                },
                "outcome": {
                    "type": "string",
                    "description": "Final result.",
                },
                "tools_used": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tools used in the process.",
                },
            },
            "required": ["title", "goal", "steps", "tags"],
        }

    async def execute(self, **kwargs: Any) -> str:
        preview = {
            "title": kwargs.get("title", ""),
            "goal": kwargs.get("goal", ""),
            "steps": kwargs.get("steps", []),
            "tags": kwargs.get("tags", []),
            "outcome": kwargs.get("outcome", ""),
            "tools_used": kwargs.get("tools_used", []),
        }

        try:
            result = await self._store.create(
                preview=preview,
                raw_messages=[],
                source_session=self._session_key,
            )
            return json.dumps(
                {"status": "saved", "id": result["id"], "title": result["title"]},
                ensure_ascii=False,
            )
        except Exception as e:
            return f"Error saving Know-how: {e}"
