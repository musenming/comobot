"""Middleware chain base classes for Agent v2 pipeline.

Implements an onion-model middleware chain: each middleware wraps the next,
allowing pre-processing and post-processing of the AgentContext.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Context object that flows through the entire middleware chain."""

    # --- Input (set before chain starts) ---
    message_content: str  # User message text
    session_key: str  # e.g. "telegram:12345"
    channel: str  # e.g. "telegram"
    chat_id: str  # e.g. "12345"

    # Session object (loaded by caller)
    session: Any = None  # comobot.session.manager.Session

    # --- Context accumulated by middlewares ---
    system_prompt_parts: list[str] = field(default_factory=list)
    injected_memories: list[dict] = field(default_factory=list)
    plan: Any = None  # planning.models.TaskPlan | None
    complexity: str = "simple"  # "simple" | "complex"
    plan_bootstrap: list[dict] | None = None  # Prior results when escalating
    escalation_reason: str | None = None

    # --- Output ---
    final_content: str | None = None
    tools_used: list[str] = field(default_factory=list)
    all_messages: list[dict] = field(default_factory=list)
    media: list[str] = field(default_factory=list)

    # --- Callbacks (set by caller) ---
    push_process: Callable[..., Awaitable[None]] | None = None
    on_progress: Callable[..., Awaitable[None]] | None = None

    # --- Metadata for inter-middleware communication ---
    metadata: dict[str, Any] = field(default_factory=dict)


class MiddlewareBase(ABC):
    """Abstract base for all middlewares in the Agent v2 pipeline."""

    @abstractmethod
    async def process(
        self, ctx: AgentContext, next_mw: Callable[[AgentContext], Awaitable[AgentContext]]
    ) -> AgentContext:
        """Process the context, optionally calling next_mw() to continue the chain."""
        ...


class MiddlewareChain:
    """Executes a list of middlewares in onion-model order.

    Each middleware wraps the next: enter in order, exit in reverse.
    """

    def __init__(self, middlewares: list[MiddlewareBase]) -> None:
        self._middlewares = middlewares

    async def execute(self, ctx: AgentContext) -> AgentContext:
        """Run the full middleware chain on the given context."""

        async def _run(index: int, ctx: AgentContext) -> AgentContext:
            if index >= len(self._middlewares):
                return ctx
            mw = self._middlewares[index]
            return await mw.process(ctx, lambda c: _run(index + 1, c))

        return await _run(0, ctx)
