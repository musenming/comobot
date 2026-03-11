"""Memory system for persistent agent memory.

Two-layer architecture:
- MEMORY.md: curated long-term memory (always loaded into context)
- memory/YYYY-MM-DD.md: daily logs (today + yesterday loaded at session start)

Consolidation writes to daily log files instead of a single HISTORY.md.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from comobot.utils.helpers import ensure_dir

if TYPE_CHECKING:
    from comobot.providers.base import LLMProvider
    from comobot.session.manager import Session


_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "daily_entry": {
                        "type": "string",
                        "description": "Summary of events/decisions/topics for today's daily log. "
                        "2-5 sentences. Include detail useful for search.",
                    },
                    "memory_update": {
                        "type": "string",
                        "description": "Full updated long-term memory as markdown. Include all existing "
                        "facts plus new ones. Return unchanged if nothing new.",
                    },
                },
                "required": ["daily_entry", "memory_update"],
            },
        },
    }
]

_MEMORY_FLUSH_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "flush_memory",
            "description": "Write durable memories before context compaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "daily_notes": {
                        "type": "string",
                        "description": "Notes to append to today's daily log. Empty string if nothing to save.",
                    },
                    "memory_updates": {
                        "type": "string",
                        "description": "Updates to MEMORY.md. Empty string if no changes needed.",
                    },
                },
                "required": ["daily_notes"],
            },
        },
    }
]


class MemoryStore:
    """Two-layer memory: MEMORY.md (long-term facts) + daily logs (YYYY-MM-DD.md)."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        # Legacy HISTORY.md — still readable for backward compat
        self.history_file = self.memory_dir / "HISTORY.md"

    # ── Long-term memory ──────────────────────────────────────────

    def read_long_term(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    # ── Daily logs ────────────────────────────────────────────────

    def _daily_log_path(self, d: date | None = None) -> Path:
        """Get path for a daily log file."""
        d = d or date.today()
        return self.memory_dir / f"{d.isoformat()}.md"

    def append_daily(self, entry: str, d: date | None = None) -> None:
        """Append an entry to today's daily log."""
        path = self._daily_log_path(d)
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def read_daily(self, d: date | None = None) -> str:
        """Read a daily log file."""
        path = self._daily_log_path(d)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def get_recent_daily_context(self, days: int = 2) -> str:
        """Get daily logs for today and yesterday (or more days)."""
        parts = []
        today = date.today()
        for i in range(days):
            d = today - timedelta(days=i)
            content = self.read_daily(d)
            if content.strip():
                label = "Today" if i == 0 else ("Yesterday" if i == 1 else d.isoformat())
                parts.append(f"### {label} ({d.isoformat()})\n{content.strip()}")
        return "\n\n".join(parts)

    # ── Legacy HISTORY.md compat ──────────────────────────────────

    def append_history(self, entry: str) -> None:
        """Append to legacy HISTORY.md (kept for backward compat)."""
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    # ── Context building ──────────────────────────────────────────

    def get_memory_context(self) -> str:
        """Build memory context for the system prompt."""
        parts = []

        long_term = self.read_long_term()
        if long_term:
            parts.append(f"## Long-term Memory\n{long_term}")

        daily = self.get_recent_daily_context()
        if daily:
            parts.append(f"## Recent Daily Logs\n{daily}")

        return "\n\n".join(parts)

    # ── Consolidation ─────────────────────────────────────────────

    async def consolidate(
        self,
        session: Session,
        provider: LLMProvider,
        model: str,
        *,
        archive_all: bool = False,
        memory_window: int = 50,
    ) -> bool:
        """Consolidate old messages into MEMORY.md + daily log via LLM tool call.

        Returns True on success (including no-op), False on failure.
        """
        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info("Memory consolidation (archive_all): {} messages", len(session.messages))
        else:
            keep_count = memory_window // 2
            if len(session.messages) <= keep_count:
                return True
            if len(session.messages) - session.last_consolidated <= 0:
                return True
            old_messages = session.messages[session.last_consolidated : -keep_count]
            if not old_messages:
                return True
            logger.info(
                "Memory consolidation: {} to consolidate, {} keep", len(old_messages), keep_count
            )

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(
                f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}"
            )

        current_memory = self.read_long_term()
        today_log = self.read_daily()
        prompt = f"""Process this conversation and call the save_memory tool with your consolidation.

Write a summary to the daily log and update long-term memory with durable facts.

## Current Long-term Memory (MEMORY.md)
{current_memory or "(empty)"}

## Today's Daily Log ({date.today().isoformat()})
{today_log or "(empty)"}

## Conversation to Process
{chr(10).join(lines)}"""

        try:
            response = await provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a memory consolidation agent. Call the save_memory tool. "
                            "Write a concise daily_entry summarizing events/decisions. "
                            "Update memory_update with any new durable facts (preferences, context, etc)."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=_SAVE_MEMORY_TOOL,
                model=model,
            )

            if not response.has_tool_calls:
                logger.warning("Memory consolidation: LLM did not call save_memory, skipping")
                return False

            args = response.tool_calls[0].arguments
            if isinstance(args, str):
                args = json.loads(args)
            if not isinstance(args, dict):
                logger.warning(
                    "Memory consolidation: unexpected arguments type {}", type(args).__name__
                )
                return False

            # Write daily log entry
            if entry := args.get("daily_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                timestamp = datetime.now().strftime("[%H:%M]")
                self.append_daily(f"{timestamp} {entry}")

            # Update long-term memory
            if update := args.get("memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_memory:
                    self.write_long_term(update)

            session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
            logger.info(
                "Memory consolidation done: {} messages, last_consolidated={}",
                len(session.messages),
                session.last_consolidated,
            )
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return False

    # ── Pre-compaction memory flush ───────────────────────────────

    async def memory_flush(
        self,
        session: Session,
        provider: LLMProvider,
        model: str,
    ) -> bool:
        """Trigger a silent agent turn to save durable memories before compaction.

        Returns True if flush was performed, False if skipped/failed.
        """
        # Get recent unconsolidated messages for context
        recent = session.messages[-20:] if len(session.messages) > 20 else session.messages
        lines = []
        for m in recent:
            if not m.get("content"):
                continue
            lines.append(
                f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}: {m['content'][:200]}"
            )

        if not lines:
            return False

        prompt = (
            "Session nearing compaction. Review recent conversation and store any durable memories.\n\n"
            "## Recent Messages\n"
            + chr(10).join(lines)
            + "\n\nCall flush_memory with any notes worth keeping. "
            "daily_notes for today's log, memory_updates for MEMORY.md changes. "
            "Use empty strings if nothing to save."
        )

        try:
            response = await provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a memory flush agent. Save important context before compaction.",
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=_MEMORY_FLUSH_TOOL,
                model=model,
            )

            if not response.has_tool_calls:
                logger.debug("Memory flush: LLM chose not to save anything")
                return True

            args = response.tool_calls[0].arguments
            if isinstance(args, str):
                args = json.loads(args)
            if not isinstance(args, dict):
                return False

            if notes := args.get("daily_notes"):
                if isinstance(notes, str) and notes.strip():
                    timestamp = datetime.now().strftime("[%H:%M]")
                    self.append_daily(f"{timestamp} [flush] {notes}")

            if updates := args.get("memory_updates"):
                if isinstance(updates, str) and updates.strip():
                    current = self.read_long_term()
                    if updates != current:
                        self.write_long_term(updates)

            logger.info("Memory flush completed")
            return True
        except Exception:
            logger.exception("Memory flush failed")
            return False
