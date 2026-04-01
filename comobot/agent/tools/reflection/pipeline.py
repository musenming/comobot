"""Tool reflection pipeline: evaluate, retry, circuit-break, annotate."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from comobot.agent.tools.reflection.circuit_breaker import ToolCircuitBreaker
from comobot.agent.tools.reflection.evaluator import ToolResultEvaluator
from comobot.agent.tools.reflection.models import Action, EvalResult, Quality
from comobot.agent.tools.reflection.retry import RetryEngine

if TYPE_CHECKING:
    from comobot.agent.tools.registry import ToolRegistry


class ToolReflectionPipeline:
    """Orchestrates tool result evaluation, retry, circuit-breaking, and annotation.

    Sits between the agent loop and ToolRegistry. When enabled, every tool
    execution goes through: pre-check → execute → evaluate → retry → record → annotate.
    When disabled, delegates directly to registry.execute().
    """

    def __init__(
        self,
        registry: ToolRegistry,
        enabled: bool = True,
        max_retries: int = 2,
        max_consecutive_failures: int = 3,
        max_duplicate_calls: int = 2,
        cooldown_iterations: int = 5,
    ):
        self._registry = registry
        self._enabled = enabled
        self._evaluator = ToolResultEvaluator()
        self._retry_engine = RetryEngine(registry, max_retries=max_retries)
        self._breaker = ToolCircuitBreaker(
            max_consecutive_failures=max_consecutive_failures,
            max_duplicate_calls=max_duplicate_calls,
            cooldown_iterations=cooldown_iterations,
        )

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """Execute a tool with reflection (evaluate, retry, circuit-break, annotate)."""
        if not self._enabled:
            return await self._registry.execute(name, params)

        # 1. Circuit breaker pre-check
        if self._breaker.is_tripped(name):
            logger.info("Tool '{}' is circuit-broken, returning intervention", name)
            return self._breaker.build_intervention(name)

        # 2. Execute (raw, no hint suffix)
        t0 = time.monotonic()
        result = await self._registry.execute_raw(name, params)
        elapsed_ms = (time.monotonic() - t0) * 1000

        # 3. Evaluate
        eval_result = self._evaluator.evaluate(name, params, result, elapsed_ms)

        # 4. Retry if needed
        retried = False
        if eval_result.suggested_action == Action.RETRY and eval_result.retryable:
            attempts = await self._retry_engine.retry(name, params, eval_result)
            if attempts:
                retried = True
                result, _ = attempts[-1]
                eval_result = self._evaluator.evaluate(name, params, result, elapsed_ms)

        # 5. Record in circuit breaker
        success = eval_result.quality >= Quality.MEDIUM
        self._breaker.record(name, params, success)

        # 6. Annotate
        return self._annotate(result, eval_result, retried)

    def _annotate(self, result: str, eval_result: EvalResult, retried: bool) -> str:
        """Append reflection annotations to the tool result."""
        if eval_result.quality == Quality.HIGH:
            return result

        issues_text = "; ".join(i.message for i in eval_result.issues)

        if retried and eval_result.quality < Quality.MEDIUM:
            return (
                f"{result}\n\n"
                f"[REFLECTION] Retry attempted but quality remains {eval_result.quality.name}. "
                f"Issues: {issues_text}.\n"
                f"Try a fundamentally different approach."
            )

        if eval_result.suggested_action == Action.ANNOTATE:
            return (
                f"{result}\n\n"
                f"[REFLECTION] Quality: {eval_result.quality.name}. Issues: {issues_text}.\n"
                f"Consider verifying this result or trying an alternative approach."
            )

        # For RETRY action that succeeded (quality >= MEDIUM after retry), or other cases
        if eval_result.quality < Quality.HIGH:
            return (
                f"{result}\n\n"
                f"[REFLECTION] Quality: {eval_result.quality.name}. Issues: {issues_text}.\n"
                f"Analyze the error above and try a different approach."
            )

        return result
