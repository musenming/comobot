"""Memory tools: memory_search and memory_get for agent use."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from comobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from comobot.agent.memory_backend import MemoryBackend
    from comobot.agent.memory_search import MemorySearchEngine


class MemorySearchTool(Tool):
    """Semantic search over memory files (MEMORY.md + daily logs)."""

    def __init__(
        self, engine: MemorySearchEngine | None = None, *, backend: MemoryBackend | None = None
    ):
        self._engine = engine
        self._backend = backend

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return (
            "Search your memory files (MEMORY.md + daily logs) for relevant information. "
            "Uses hybrid keyword + semantic search. Use this to recall past conversations, "
            "decisions, preferences, or any stored context."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — can be a question, keyword, or phrase.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5).",
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)

        if not query.strip():
            return "Error: query cannot be empty."

        try:
            if self._backend:
                results = await self._backend.search(query, max_results=max_results)
                return self._format_backend_results(results)
            elif self._engine:
                chunks = self._engine.search(query, max_results=max_results)
                return self._format_engine_results(chunks)
            else:
                return "Error: no search backend available."
        except Exception as e:
            return f"Error searching memory: {e}"

    @staticmethod
    def _format_backend_results(results) -> str:
        if not results:
            return "No matching memories found."
        output_parts = []
        for i, r in enumerate(results, 1):
            output_parts.append(
                f"**[{i}]** `{r.file_path}` (lines {r.start_line}-{r.end_line}, "
                f"score: {r.score:.3f})\n{r.content[:700]}"
            )
        return "\n\n---\n\n".join(output_parts)

    @staticmethod
    def _format_engine_results(chunks) -> str:
        if not chunks:
            return "No matching memories found."
        output_parts = []
        for i, chunk in enumerate(chunks, 1):
            output_parts.append(
                f"**[{i}]** `{chunk.file_path}` (lines {chunk.start_line}-{chunk.end_line}, "
                f"score: {chunk.score:.3f})\n{chunk.content[:700]}"
            )
        return "\n\n---\n\n".join(output_parts)


class MemoryGetTool(Tool):
    """Read a specific memory file or line range."""

    def __init__(self, workspace: Path):
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "memory_get"

    @property
    def description(self) -> str:
        return (
            "Read a specific memory file (MEMORY.md or memory/*.md). "
            "Use after memory_search to get full context from a matched file. "
            "Returns empty text if the file doesn't exist yet."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative path to memory file, "
                        "e.g. 'memory/2026-03-11.md' or 'MEMORY.md'."
                    ),
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start reading from this line (1-based). Default: 1.",
                    "minimum": 1,
                },
                "num_lines": {
                    "type": "integer",
                    "description": "Number of lines to read. 0 = entire file (default).",
                    "minimum": 0,
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        path_str = kwargs.get("path", "")
        start_line = kwargs.get("start_line", 1)
        num_lines = kwargs.get("num_lines", 0)

        if not path_str:
            return "Error: path is required."

        # Security: only allow MEMORY.md and memory/ files
        normalized = Path(path_str).as_posix()
        if not (
            normalized == "MEMORY.md"
            or normalized == "memory/MEMORY.md"
            or normalized.startswith("memory/")
        ):
            return "Error: memory_get only reads MEMORY.md or files under memory/."

        # Prevent path traversal
        if ".." in normalized:
            return "Error: path traversal not allowed."

        abs_path = self._workspace / normalized
        if not abs_path.exists():
            return json.dumps({"text": "", "path": normalized})

        try:
            lines = abs_path.read_text(encoding="utf-8").split("\n")
        except Exception as e:
            return f"Error reading {normalized}: {e}"

        # Apply line range
        if start_line > 1:
            lines = lines[start_line - 1 :]
        if num_lines > 0:
            lines = lines[:num_lines]

        text = "\n".join(lines)
        return json.dumps({"text": text, "path": normalized}, ensure_ascii=False)
