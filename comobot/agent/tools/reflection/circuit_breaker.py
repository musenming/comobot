"""Per-tool circuit breaker: detects repeated failures and forces strategy shifts."""

from __future__ import annotations

from loguru import logger

from comobot.agent.tools.reflection.models import BreakerState, ToolCallRecord

# Default tool alternative mapping
_TOOL_ALTERNATIVES: dict[str, list[str]] = {
    "web_search": ["web_fetch", "read_file", "exec"],
    "web_fetch": ["web_search", "exec"],
    "read_file": ["list_dir", "exec"],
    "edit_file": ["write_file"],
    "exec": ["read_file", "write_file"],
    "memory_search": ["knowhow_search"],
    "knowhow_search": ["memory_search"],
}


class ToolCircuitBreaker:
    """Per-tool circuit breaker that detects loops and forces strategy changes.

    Detection modes:
    - Consecutive failures: same tool fails N times in a row
    - Duplicate calls: same tool + same params called N times
    - Category exhaustion: all tools in a category tripped

    When tripped, the breaker blocks the tool and injects a structured
    intervention message guiding the LLM to use alternatives.
    """

    def __init__(
        self,
        max_consecutive_failures: int = 3,
        max_duplicate_calls: int = 2,
        cooldown_iterations: int = 5,
        alternatives: dict[str, list[str]] | None = None,
    ):
        self._max_consecutive_failures = max_consecutive_failures
        self._max_duplicate_calls = max_duplicate_calls
        self._cooldown_iterations = cooldown_iterations
        self._alternatives = alternatives or dict(_TOOL_ALTERNATIVES)
        self._tool_states: dict[str, BreakerState] = {}
        self._call_history: list[ToolCallRecord] = []
        self._current_iteration: int = 0

    def record(self, tool_name: str, params: dict, success: bool) -> None:
        """Record a tool call and update breaker state."""
        self._current_iteration += 1
        params_hash = ToolCallRecord.hash_params(params)
        self._call_history.append(
            ToolCallRecord(
                tool_name=tool_name,
                params_hash=params_hash,
                success=success,
            )
        )

        state = self._tool_states.setdefault(tool_name, BreakerState())
        state.total_calls += 1

        if success:
            state.consecutive_failures = 0
            return

        state.consecutive_failures += 1

        # Check duplicate calls (same tool + same params)
        dup_count = sum(
            1
            for r in self._call_history
            if r.tool_name == tool_name and r.params_hash == params_hash
        )
        state.duplicate_count = dup_count

        if dup_count >= self._max_duplicate_calls:
            self._trip(tool_name, state, f"duplicate calls ({dup_count}x)")
        elif state.consecutive_failures >= self._max_consecutive_failures:
            self._trip(tool_name, state, f"{state.consecutive_failures} consecutive failures")

    def _trip(self, tool_name: str, state: BreakerState, reason: str) -> None:
        """Trip the breaker for a tool."""
        if not state.tripped:
            state.tripped = True
            state.tripped_at_iteration = self._current_iteration
            logger.warning("Circuit breaker tripped for '{}': {}", tool_name, reason)

    def is_tripped(self, tool_name: str) -> bool:
        """Check if a tool's circuit breaker is tripped."""
        state = self._tool_states.get(tool_name)
        if not state or not state.tripped:
            return False
        # Auto-reset after cooldown
        if (self._current_iteration - state.tripped_at_iteration) >= self._cooldown_iterations:
            self.reset(tool_name)
            return False
        return True

    def build_intervention(self, tool_name: str) -> str:
        """Build a structured intervention message when a tool is circuit-broken."""
        alternatives = [
            alt for alt in self._alternatives.get(tool_name, []) if not self.is_tripped(alt)
        ]
        if alternatives:
            return (
                f"[CIRCUIT_BREAK] Tool '{tool_name}' is temporarily blocked "
                f"after repeated failures.\n"
                f"Suggested alternatives: {', '.join(alternatives)}\n"
                f"Please try a different approach to accomplish your goal."
            )
        return (
            f"[CIRCUIT_BREAK] Tool '{tool_name}' is temporarily blocked "
            f"after repeated failures.\n"
            f"Consider rephrasing your approach or skipping this step."
        )

    def reset(self, tool_name: str) -> None:
        """Reset the circuit breaker state for a tool."""
        if tool_name in self._tool_states:
            self._tool_states[tool_name] = BreakerState()
            logger.debug("Circuit breaker reset for '{}'", tool_name)
