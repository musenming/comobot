"""Complexity router middleware: detects task complexity and escalates to planning.

Three-tier detection:
1. Explicit prefix: /plan, /think, /deep -> immediate plan mode
2. Runtime escalation: monitors tool loop counters (tool_count, search_count, error_count)
3. LLM self-trigger: detects [PLAN_MODE] in first LLM response

When escalation occurs, raises EscalationSignal to interrupt the tool loop.
The signal carries completed context so no work is wasted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from comobot.agent.middleware.base import AgentContext, MiddlewareBase

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


# Explicit command prefixes that force plan mode
EXPLICIT_TRIGGERS = ("/plan ", "/think ", "/deep ")

# Search-category tool names
SEARCH_TOOLS = frozenset({"web_search", "memory_search", "knowhow_search"})


@dataclass
class EscalationSignal(Exception):  # noqa: N818
    """Raised inside the tool loop to escalate from simple to plan mode.

    Carries the reason for escalation and any results produced so far,
    so the planner can build on prior work instead of starting from scratch.
    """

    reason: str = ""
    completed_context: str = ""


@dataclass
class ToolStats:
    """Counters tracked during the agent tool loop."""

    tool_count: int = 0
    search_count: int = 0
    error_count: int = 0
    iteration_count: int = 0


class ComplexityRouter(MiddlewareBase):
    """Middleware that routes messages to simple (direct) or complex (planning) paths.

    Design: no pre-judgment LLM call. Simple messages run at zero extra cost.
    Complex tasks are detected *during* execution and escalated mid-flight.
    """

    def __init__(
        self,
        *,
        escalation_tool_count: int = 5,
        escalation_search_count: int = 3,
        escalation_error_count: int = 2,
        escalation_iteration_count: int = 8,
        llm_self_trigger: bool = True,
        planning_enabled: bool = True,
    ):
        self._thresholds = {
            "tool_count": escalation_tool_count,
            "search_count": escalation_search_count,
            "error_count": escalation_error_count,
            "iteration_count": escalation_iteration_count,
        }
        self._llm_self_trigger = llm_self_trigger
        self._planning_enabled = planning_enabled

    async def process(
        self,
        ctx: AgentContext,
        next_mw: Callable[[AgentContext], Awaitable[AgentContext]],
    ) -> AgentContext:
        """Route the message based on complexity detection."""
        if not self._planning_enabled:
            ctx.complexity = "simple"
            return await next_mw(ctx)

        content = ctx.message_content

        # Tier 1: Explicit trigger via command prefix
        for prefix in EXPLICIT_TRIGGERS:
            if content.startswith(prefix):
                ctx.complexity = "complex"
                ctx.message_content = content[len(prefix) :]
                logger.info("Complexity: explicit plan mode via '{}'", prefix.strip())
                return await next_mw(ctx)

        # Default to simple — escalation happens inside the tool loop
        ctx.complexity = "simple"
        return await next_mw(ctx)

    # ------------------------------------------------------------------
    # Tool-loop callback: called after each tool execution
    # ------------------------------------------------------------------

    def create_tool_callback(
        self,
        ctx: AgentContext,
        messages: list[dict],
    ) -> tuple[ToolStats, Callable]:
        """Create a tool-complete callback that monitors for escalation signals.

        Returns (stats, callback). The caller should invoke `callback` after
        each tool execution in _run_agent_loop.
        """
        stats = ToolStats()

        def on_tool_complete(tool_name: str, result: str, success: bool) -> None:
            stats.tool_count += 1
            stats.iteration_count += 1
            if tool_name in SEARCH_TOOLS:
                stats.search_count += 1
            if not success:
                stats.error_count += 1

            if self._should_escalate(stats):
                reason = self._escalation_reason(stats)
                # Compile completed context from messages so far
                completed = self._compile_completed_context(messages)
                raise EscalationSignal(reason=reason, completed_context=completed)

        return stats, on_tool_complete

    def check_llm_self_trigger(self, content: str | None) -> bool:
        """Check if the LLM's first response starts with [PLAN_MODE]."""
        if not self._llm_self_trigger or not content:
            return False
        return content.strip().startswith("[PLAN_MODE]")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_escalate(self, stats: ToolStats) -> bool:
        """Check if any escalation threshold has been reached."""
        for key, threshold in self._thresholds.items():
            if getattr(stats, key, 0) >= threshold:
                return True
        return False

    @staticmethod
    def _escalation_reason(stats: ToolStats) -> str:
        """Build a human-readable escalation reason."""
        reasons: list[str] = []
        if stats.tool_count >= 5:
            reasons.append(f"called {stats.tool_count} tools")
        if stats.search_count >= 3:
            reasons.append(f"searched {stats.search_count} times")
        if stats.error_count >= 2:
            reasons.append(f"encountered {stats.error_count} errors")
        if stats.iteration_count >= 8:
            reasons.append(f"ran {stats.iteration_count} iterations")
        return ", ".join(reasons) if reasons else "complexity threshold reached"

    @staticmethod
    def _compile_completed_context(messages: list[dict]) -> str:
        """Extract meaningful completed results from the message history."""
        parts: list[str] = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "tool" and isinstance(content, str) and content.strip():
                name = m.get("name", "tool")
                # Truncate very long tool results
                text = content[:500] if len(content) > 500 else content
                parts.append(f"[{name}]: {text}")
            elif role == "assistant" and isinstance(content, str) and content.strip():
                parts.append(f"[assistant]: {content[:300]}")
        return "\n".join(parts[-10:])  # Keep last 10 entries at most
