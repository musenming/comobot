"""Memory injection: retrieve and inject relevant episodic memories into context.

Called during system prompt construction to enrich the agent's context
with relevant past experiences.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from comobot.agent.memory_search import MemorySearchEngine


class MemoryInjector:
    """Retrieve relevant episodic and feedback memories for injection into system prompt."""

    def __init__(
        self,
        workspace: Path,
        memory_engine: MemorySearchEngine | None = None,
        max_inject: int = 5,
    ):
        self._workspace = workspace
        self._memory_engine = memory_engine
        self._max_inject = max_inject

    def inject(self, user_message: str) -> list[str]:
        """Retrieve relevant memories and return system prompt fragments.

        Returns a list of formatted text blocks ready for system prompt injection.
        """
        parts: list[str] = []

        # 1. Load all feedback memories (always injected, no search filtering)
        feedback_text = self._load_feedback_memories()
        if feedback_text:
            parts.append(f"# User Preferences & Feedback\n\n{feedback_text}")

        # 2. Search episodic memories by relevance to user message
        if user_message and self._memory_engine:
            episodic_text = self._retrieve_episodic(user_message)
            if episodic_text:
                parts.append(f"# Relevant Past Experience\n\n{episodic_text}")

        return parts

    def _load_feedback_memories(self) -> str:
        """Load all feedback memory files from workspace/feedback/."""
        feedback_dir = self._workspace / "feedback"
        if not feedback_dir.exists():
            return ""
        entries: list[str] = []
        for p in sorted(feedback_dir.glob("*.md")):
            if p.name.startswith("."):
                continue
            try:
                content = p.read_text(encoding="utf-8")
                # Strip YAML frontmatter
                body = self._strip_frontmatter(content)
                if body.strip():
                    entries.append(f"- {body.strip()}")
            except Exception:
                continue
        return "\n".join(entries) if entries else ""

    def _retrieve_episodic(self, user_message: str) -> str:
        """Retrieve relevant episodic memories via semantic search."""
        if not self._memory_engine:
            return ""
        try:
            chunks = self._memory_engine.search(
                user_message,
                max_results=self._max_inject,
                file_filter="episodic/",
            )
            # Filter by score threshold
            chunks = [c for c in chunks if c.score >= 0.3]
            if not chunks:
                return ""
            lines: list[str] = []
            for chunk in chunks:
                lines.append(f"- [{chunk.score:.2f}] {chunk.content}")
            return "\n".join(lines)
        except Exception:
            logger.debug("Episodic memory retrieval failed")
            return ""

    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        """Strip YAML frontmatter (--- ... ---) from Markdown content."""
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                return parts[2]
        return text
