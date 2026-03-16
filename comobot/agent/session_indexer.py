"""Session indexer: converts JSONL sessions to searchable Markdown transcripts."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from comobot.utils.helpers import ensure_dir

if TYPE_CHECKING:
    from comobot.agent.memory_search import MemorySearchEngine
    from comobot.config.schema import SessionIndexConfig


@dataclass
class IndexState:
    """Tracks indexing progress for a single session file."""

    last_offset: int = 0
    last_line_count: int = 0
    indexed_at: float = 0.0


class SessionSanitizer:
    """Converts session JSONL messages to search-friendly Markdown."""

    _BASE64_RE = re.compile(r"data:[^;]+;base64,[A-Za-z0-9+/=]{100,}")
    _TOOL_RESULT_MAX = 500

    def sanitize(self, session_path: Path) -> str:
        """Convert an entire JSONL session file to Markdown."""
        messages, metadata = self._load_jsonl(session_path)
        if not messages:
            return ""

        parts: list[str] = []

        # Frontmatter
        session_key = metadata.get("key", session_path.stem)
        created_at = metadata.get("created_at", "")
        parts.append("---")
        parts.append(f"session_key: {session_key}")
        parts.append(f"created_at: {created_at}")
        parts.append(f"message_count: {len(messages)}")
        parts.append("---")
        parts.append("")
        parts.append(f"# Session: {session_key}")
        parts.append("")

        for msg in messages:
            line = self._format_message(msg)
            if line:
                parts.append(line)

        return "\n".join(parts)

    def sanitize_messages(self, messages: list[dict], session_key: str = "") -> str:
        """Convert a list of message dicts to Markdown (for incremental updates)."""
        parts: list[str] = []
        for msg in messages:
            line = self._format_message(msg)
            if line:
                parts.append(line)
        return "\n".join(parts)

    def _format_message(self, msg: dict) -> str | None:
        role = msg.get("role", "")

        # Skip tool result messages (already reflected in assistant tool_call lines)
        if role == "tool":
            return None

        content = msg.get("content", "") or ""

        # Handle multimodal content (list of content blocks)
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "image_url":
                        text_parts.append("[image]")
                elif isinstance(block, str):
                    text_parts.append(block)
            content = " ".join(text_parts)

        # Strip base64 images
        content = self._BASE64_RE.sub("[image]", content)

        # Truncate overly long content
        if len(content) > self._TOOL_RESULT_MAX:
            content = content[: self._TOOL_RESULT_MAX] + " [truncated]"

        timestamp = msg.get("timestamp", "")
        ts_prefix = f"[{timestamp[:16]}] " if timestamp else ""

        if role == "assistant" and msg.get("tool_calls"):
            tools = []
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                tools.append(fn.get("name", "unknown"))
            return f"{ts_prefix}**Assistant** [called: {', '.join(tools)}]: {content}"

        if role in ("user", "assistant"):
            return f"{ts_prefix}**{role.title()}**: {content}"

        # Skip system, reasoning_content, etc.
        return None

    @staticmethod
    def _load_jsonl(path: Path) -> tuple[list[dict], dict]:
        """Load messages and metadata from a JSONL session file."""
        messages: list[dict] = []
        metadata: dict = {}
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("_type") == "metadata":
                        metadata = obj
                    elif "role" in obj:
                        messages.append(obj)
        except OSError:
            logger.warning("Failed to read session file: {}", path)
        return messages, metadata


class SessionIndexer:
    """Incremental indexer for session transcripts."""

    def __init__(
        self,
        config: SessionIndexConfig,
        memory_engine: MemorySearchEngine | None,
        sessions_dir: Path,
        workspace: Path,
    ):
        self._config = config
        self._engine = memory_engine
        self._sessions_dir = sessions_dir
        self._workspace = workspace
        self._transcripts_dir = ensure_dir(workspace / ".session_index" / "transcripts")
        self._state_file = workspace / ".session_index" / "state.json"
        self._sanitizer = SessionSanitizer()
        self._index_state: dict[str, IndexState] = {}
        self._last_run: float = 0.0
        self._load_state()

    def _load_state(self) -> None:
        """Load index state from disk."""
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            for name, st in data.items():
                self._index_state[name] = IndexState(
                    last_offset=st.get("last_offset", 0),
                    last_line_count=st.get("last_line_count", 0),
                    indexed_at=st.get("indexed_at", 0.0),
                )
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load session index state")

    def _save_state(self) -> None:
        """Persist index state to disk."""
        data = {}
        for name, st in self._index_state.items():
            data[name] = {
                "last_offset": st.last_offset,
                "last_line_count": st.last_line_count,
                "indexed_at": st.indexed_at,
            }
        ensure_dir(self._state_file.parent)
        self._state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    async def check_and_index(self) -> None:
        """Scan session files and incrementally index changed ones."""
        if not self._config.enabled:
            return

        now = time.time()
        # Debounce
        if now - self._last_run < self._config.debounce_seconds:
            return
        self._last_run = now

        if not self._sessions_dir.exists():
            return

        changed = False
        for jsonl_path in sorted(self._sessions_dir.glob("*.jsonl")):
            # Check exclude_channels
            if self._is_excluded(jsonl_path.stem):
                continue

            state = self._index_state.get(jsonl_path.name)
            try:
                current_size = jsonl_path.stat().st_size
                current_lines = self._count_lines(jsonl_path)
            except OSError:
                continue

            if state is None:
                await self._full_index(jsonl_path, current_size, current_lines)
                changed = True
            elif self._should_reindex(state, current_size, current_lines):
                await self._incremental_index(jsonl_path, state, current_size, current_lines)
                changed = True

        if changed:
            self._save_state()
            if self._engine:
                try:
                    self._engine.reindex()
                except Exception:
                    logger.debug("Memory reindex after session indexing failed")

    def _is_excluded(self, stem: str) -> bool:
        """Check if a session file should be excluded based on channel config."""
        for channel in self._config.exclude_channels:
            if stem.startswith(channel):
                return True
        return False

    def _should_reindex(self, state: IndexState, size: int, lines: int) -> bool:
        delta_bytes = size - state.last_offset
        delta_lines = lines - state.last_line_count
        return (
            delta_bytes >= self._config.delta_threshold_bytes
            or delta_lines >= self._config.delta_threshold_lines
        )

    @staticmethod
    def _count_lines(path: Path) -> int:
        count = 0
        with path.open("rb") as f:
            for _ in f:
                count += 1
        return count

    async def _full_index(self, path: Path, size: int, lines: int) -> None:
        """Full index of a session file."""
        logger.info("Session index: full indexing {}", path.name)
        transcript = self._sanitizer.sanitize(path)
        if not transcript.strip():
            return

        safe_name = path.stem.replace(":", "_") + ".md"
        transcript_path = self._transcripts_dir / safe_name
        transcript_path.write_text(transcript, encoding="utf-8")

        self._index_state[path.name] = IndexState(
            last_offset=size,
            last_line_count=lines,
            indexed_at=time.time(),
        )

    async def _incremental_index(
        self, path: Path, state: IndexState, size: int, lines: int
    ) -> None:
        """Incremental index: read only new messages since last offset."""
        logger.info(
            "Session index: incremental indexing {} (+{} bytes)",
            path.name,
            size - state.last_offset,
        )

        new_messages = self._read_from_offset(path, state.last_offset)
        if not new_messages:
            return

        sanitized = self._sanitizer.sanitize_messages(new_messages, path.stem)
        if not sanitized.strip():
            return

        safe_name = path.stem.replace(":", "_") + ".md"
        transcript_path = self._transcripts_dir / safe_name

        if transcript_path.exists():
            with transcript_path.open("a", encoding="utf-8") as f:
                f.write("\n" + sanitized)
        else:
            # Transcript missing — do full reindex instead
            await self._full_index(path, size, lines)
            return

        state.last_offset = size
        state.last_line_count = lines
        state.indexed_at = time.time()

    @staticmethod
    def _read_from_offset(path: Path, offset: int) -> list[dict]:
        """Read JSONL messages starting from byte offset."""
        messages: list[dict] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                f.seek(offset)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "role" in obj:
                        messages.append(obj)
        except OSError:
            pass
        return messages
