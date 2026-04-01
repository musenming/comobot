"""Smart retry engine with per-tool parameter adjustment strategies."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from comobot.agent.tools.reflection.models import EvalResult

if TYPE_CHECKING:
    from comobot.agent.tools.registry import ToolRegistry


class RetryStrategy(Protocol):
    """Protocol for tool-specific retry parameter adjustment."""

    def applies_to(self, tool_name: str) -> bool: ...
    def adjust_params(self, params: dict, eval_result: EvalResult, attempt: int) -> dict | None: ...


# ---------------------------------------------------------------------------
# Built-in strategies
# ---------------------------------------------------------------------------


class BroadenSearchStrategy:
    """Broaden web search queries by simplifying keywords."""

    def applies_to(self, tool_name: str) -> bool:
        return tool_name == "web_search"

    def adjust_params(self, params: dict, eval_result: EvalResult, attempt: int) -> dict | None:
        query = params.get("query", "")
        if not query:
            return None

        words = query.split()
        if len(words) <= 2:
            return None  # Already minimal, can't broaden further

        if attempt == 0:
            # First retry: drop quotation marks and special chars
            cleaned = query.replace('"', "").replace("'", "").replace("+", " ")
            if cleaned != query:
                return {**params, "query": cleaned}
            # Remove the last word (often a qualifier)
            return {**params, "query": " ".join(words[:-1])}
        elif attempt == 1:
            # Second retry: keep only core words (first 3)
            return {**params, "query": " ".join(words[:3])}
        return None


class FuzzyPathStrategy:
    """Try to find similar file paths when a file is not found."""

    def applies_to(self, tool_name: str) -> bool:
        return tool_name in ("read_file", "edit_file")

    def adjust_params(self, params: dict, eval_result: EvalResult, attempt: int) -> dict | None:
        # Only try once — the pipeline will use list_dir to find alternatives
        if attempt > 0:
            return None

        path = params.get("path", params.get("file_path", ""))
        if not path:
            return None

        # Try common path corrections
        if path.startswith("./"):
            corrected = path[2:]
        elif not path.startswith("/"):
            corrected = "./" + path
        else:
            return None  # Can't guess further without filesystem access

        key = "path" if "path" in params else "file_path"
        return {**params, key: corrected}


class RetryWithBackoffStrategy:
    """Retry with a short delay for transient failures (rate limits, timeouts)."""

    def applies_to(self, tool_name: str) -> bool:
        return tool_name == "web_fetch"

    def adjust_params(self, params: dict, eval_result: EvalResult, attempt: int) -> dict | None:
        if attempt > 1:
            return None
        # Return same params — the retry engine handles the delay
        return dict(params)


class DefaultRetryStrategy:
    """Fallback: retry with identical params (handles transient errors)."""

    def applies_to(self, tool_name: str) -> bool:
        return True

    def adjust_params(self, params: dict, eval_result: EvalResult, attempt: int) -> dict | None:
        if attempt > 0:
            return None  # Only one blind retry
        return dict(params)


# ---------------------------------------------------------------------------
# Retry engine
# ---------------------------------------------------------------------------

_DEFAULT_STRATEGIES: list[RetryStrategy] = [
    BroadenSearchStrategy(),
    FuzzyPathStrategy(),
    RetryWithBackoffStrategy(),
    DefaultRetryStrategy(),
]


class RetryEngine:
    """Manages automatic tool retries with parameter adjustment."""

    def __init__(
        self,
        registry: ToolRegistry,
        max_retries: int = 2,
        strategies: list[RetryStrategy] | None = None,
        backoff_base_s: float = 1.0,
    ):
        self._registry = registry
        self._max_retries = max_retries
        self._strategies = strategies or list(_DEFAULT_STRATEGIES)
        self._backoff_base_s = backoff_base_s

    def _find_strategy(self, tool_name: str) -> RetryStrategy | None:
        for s in self._strategies:
            if s.applies_to(tool_name):
                return s
        return None

    async def retry(
        self,
        tool_name: str,
        original_params: dict,
        eval_result: EvalResult,
    ) -> list[tuple[str, dict]]:
        """Retry a tool with adjusted params. Returns list of (result, params) attempts."""
        strategy = self._find_strategy(tool_name)
        if not strategy:
            return []

        attempts: list[tuple[str, dict]] = []
        for attempt in range(self._max_retries):
            adjusted = strategy.adjust_params(original_params, eval_result, attempt)
            if adjusted is None:
                break  # Strategy says no more retries

            # Backoff for web tools
            if eval_result.retry_hint == "retry_with_backoff" and attempt > 0:
                delay = self._backoff_base_s * (2**attempt)
                logger.debug("Retry backoff: {:.1f}s before attempt {}", delay, attempt + 1)
                await asyncio.sleep(delay)

            logger.info(
                "Retry {}/{} for '{}' with adjusted params",
                attempt + 1,
                self._max_retries,
                tool_name,
            )
            result = await self._registry.execute_raw(tool_name, adjusted)
            attempts.append((result, adjusted))

            # If this attempt looks successful, stop retrying
            if not (isinstance(result, str) and result.startswith("Error")) and result.strip():
                break

        return attempts
