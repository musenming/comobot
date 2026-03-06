"""Multi-key rotation and load balancing for LLM providers."""

from __future__ import annotations

import random
import time
from typing import Literal


class KeyRotator:
    """Rotates API keys using configurable strategies."""

    def __init__(
        self,
        keys: list[str],
        strategy: Literal["round_robin", "random", "least_used"] = "round_robin",
        cooldown_seconds: int = 60,
    ):
        self._keys = keys
        self._strategy = strategy
        self._cooldown_seconds = cooldown_seconds
        self._index = 0
        self._usage_count: dict[int, int] = {i: 0 for i in range(len(keys))}
        self._cooldowns: dict[int, float] = {}

    @property
    def has_keys(self) -> bool:
        return len(self._keys) > 0

    def next_key(self) -> str:
        """Get the next available API key based on strategy."""
        if not self._keys:
            raise RuntimeError("No API keys configured")

        available = self._available_indices()
        if not available:
            raise RuntimeError("All API keys are in cooldown")

        if self._strategy == "round_robin":
            idx = self._round_robin(available)
        elif self._strategy == "random":
            idx = random.choice(available)
        elif self._strategy == "least_used":
            idx = min(available, key=lambda i: self._usage_count[i])
        else:
            idx = available[0]

        self._usage_count[idx] += 1
        return self._keys[idx]

    def mark_cooldown(self, key: str) -> None:
        """Mark a key for cooldown (e.g., after 429 response)."""
        try:
            idx = self._keys.index(key)
            self._cooldowns[idx] = time.monotonic() + self._cooldown_seconds
        except ValueError:
            pass

    def _available_indices(self) -> list[int]:
        """Return indices of keys not in cooldown."""
        now = time.monotonic()
        return [
            i
            for i in range(len(self._keys))
            if i not in self._cooldowns or self._cooldowns[i] <= now
        ]

    def _round_robin(self, available: list[int]) -> int:
        """Round-robin through available indices."""
        for _ in range(len(self._keys)):
            idx = self._index % len(self._keys)
            self._index += 1
            if idx in available:
                return idx
        return available[0]
