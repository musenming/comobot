"""Data models for the tool reflection layer."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import IntEnum, auto


class Quality(IntEnum):
    """Tool result quality level."""

    FAILED = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Action(IntEnum):
    """Suggested action after evaluation."""

    PASS = auto()
    ANNOTATE = auto()
    RETRY = auto()
    CIRCUIT_BREAK = auto()


@dataclass
class Issue:
    """A single quality issue detected by a checker."""

    code: str  # e.g. "empty_result", "file_not_found"
    message: str
    retryable: bool = False
    retry_hint: str | None = None  # Guidance for the retry strategy


@dataclass
class EvalResult:
    """Result of evaluating a tool execution."""

    quality: Quality = Quality.HIGH
    issues: list[Issue] = field(default_factory=list)
    suggested_action: Action = Action.PASS

    @property
    def retryable(self) -> bool:
        return any(i.retryable for i in self.issues)

    @property
    def retry_hint(self) -> str | None:
        for i in self.issues:
            if i.retry_hint:
                return i.retry_hint
        return None


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation."""

    tool_name: str
    params_hash: str
    success: bool
    timestamp: float = field(default_factory=time.monotonic)

    @staticmethod
    def hash_params(params: dict) -> str:
        raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode()).hexdigest()[:12]


@dataclass
class BreakerState:
    """Per-tool circuit breaker state."""

    consecutive_failures: int = 0
    total_calls: int = 0
    duplicate_count: int = 0
    tripped: bool = False
    tripped_at_iteration: int = 0  # Iteration when breaker tripped
