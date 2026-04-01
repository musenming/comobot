"""Data models for episodic memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EpisodicMemory:
    """A single episodic memory extracted from a conversation."""

    id: str  # "ep_YYYYMMDD_NNN"
    type: str  # "task" | "fact" | "preference" | "feedback"
    content: str
    confidence: float = 1.0
    source_session: str = ""
    source_channel: str = ""
    tags: list[str] = field(default_factory=list)
    file_path: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed_at: datetime | None = None
    access_count: int = 0
    status: str = "active"  # "active" | "archived" | "merged"
