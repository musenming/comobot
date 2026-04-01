"""Episodic memory system for Agent v2.

Provides automatic extraction, storage, and retrieval of
task/fact/preference/feedback memories from conversations.
"""

from comobot.agent.episodic.models import EpisodicMemory
from comobot.agent.episodic.store import EpisodicMemoryStore

__all__ = ["EpisodicMemory", "EpisodicMemoryStore"]
