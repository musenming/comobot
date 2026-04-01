"""Tests for the tool execution reflection layer."""

from typing import Any

import pytest

from comobot.agent.tools.base import Tool
from comobot.agent.tools.reflection.circuit_breaker import ToolCircuitBreaker
from comobot.agent.tools.reflection.evaluator import ToolResultEvaluator
from comobot.agent.tools.reflection.models import Action, Quality
from comobot.agent.tools.reflection.pipeline import ToolReflectionPipeline
from comobot.agent.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeTool(Tool):
    """Configurable fake tool for testing."""

    def __init__(self, tool_name: str = "fake", results: list[str] | None = None):
        self._name = tool_name
        self._results = list(results or ["ok"])
        self._call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "fake tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        idx = min(self._call_count, len(self._results) - 1)
        self._call_count += 1
        return self._results[idx]


def _make_registry(*tools: Tool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


# ===========================================================================
# Evaluator tests
# ===========================================================================


def test_evaluator_imports_without_error():
    """Verify EmptyResultChecker ordering fix — no NameError at import."""
    evaluator = ToolResultEvaluator()
    assert evaluator is not None


def test_evaluator_high_quality_on_clean_result():
    ev = ToolResultEvaluator()
    result = ev.evaluate("read_file", {"path": "x.py"}, "file contents here", 50.0)
    assert result.quality == Quality.HIGH
    assert result.suggested_action == Action.PASS
    assert result.issues == []


def test_evaluator_detects_error_prefix():
    ev = ToolResultEvaluator()
    result = ev.evaluate("exec", {}, "Error: command not found", 10.0)
    assert result.quality == Quality.FAILED
    assert result.suggested_action == Action.RETRY


def test_evaluator_detects_empty_result():
    ev = ToolResultEvaluator()
    result = ev.evaluate("web_search", {"query": "test"}, "", 100.0)
    assert result.quality == Quality.LOW
    assert any(i.code == "empty_result" for i in result.issues)


def test_evaluator_detects_search_no_results():
    ev = ToolResultEvaluator()
    result = ev.evaluate("web_search", {"query": "xyz"}, "no results found", 200.0)
    assert any(i.code == "search_no_results" for i in result.issues)


def test_evaluator_detects_file_not_found():
    ev = ToolResultEvaluator()
    result = ev.evaluate("read_file", {"path": "/x"}, "Error: no such file or directory", 5.0)
    assert any(i.code == "file_not_found" for i in result.issues)


def test_evaluator_detects_truncation():
    ev = ToolResultEvaluator()
    result = ev.evaluate("exec", {}, "some output [truncated]", 50.0)
    assert any(i.code == "truncated" for i in result.issues)
    assert result.quality == Quality.MEDIUM  # truncation is non-retryable


# ===========================================================================
# Circuit breaker tests
# ===========================================================================


def test_breaker_not_tripped_initially():
    cb = ToolCircuitBreaker()
    assert not cb.is_tripped("web_search")


def test_breaker_trips_after_consecutive_failures():
    cb = ToolCircuitBreaker(max_consecutive_failures=3)
    for _ in range(3):
        cb.record("web_search", {"query": "test"}, success=False)
    assert cb.is_tripped("web_search")


def test_breaker_resets_on_success():
    cb = ToolCircuitBreaker(max_consecutive_failures=3)
    cb.record("web_search", {"query": "a"}, success=False)
    cb.record("web_search", {"query": "b"}, success=False)
    cb.record("web_search", {"query": "c"}, success=True)
    assert not cb.is_tripped("web_search")


def test_breaker_trips_on_duplicate_calls():
    cb = ToolCircuitBreaker(max_duplicate_calls=2)
    cb.record("read_file", {"path": "/x"}, success=False)
    cb.record("read_file", {"path": "/x"}, success=False)
    assert cb.is_tripped("read_file")


def test_breaker_resets_after_cooldown():
    cb = ToolCircuitBreaker(max_consecutive_failures=2, cooldown_iterations=3)
    cb.record("exec", {"cmd": "fail"}, success=False)
    cb.record("exec", {"cmd": "fail"}, success=False)
    assert cb.is_tripped("exec")
    # Advance iterations via other tool calls
    for i in range(3):
        cb.record("other", {"i": i}, success=True)
    assert not cb.is_tripped("exec")


def test_breaker_intervention_with_alternatives():
    cb = ToolCircuitBreaker(max_consecutive_failures=1)
    cb.record("web_search", {"query": "x"}, success=False)
    msg = cb.build_intervention("web_search")
    assert "[CIRCUIT_BREAK]" in msg
    assert "web_fetch" in msg


def test_breaker_intervention_without_alternatives():
    cb = ToolCircuitBreaker(max_consecutive_failures=1)
    cb.record("unknown_tool", {}, success=False)
    msg = cb.build_intervention("unknown_tool")
    assert "[CIRCUIT_BREAK]" in msg
    assert "rephrasing" in msg


# ===========================================================================
# Pipeline tests
# ===========================================================================


@pytest.mark.asyncio
async def test_pipeline_disabled_passthrough():
    tool = FakeTool(results=["hello"])
    reg = _make_registry(tool)
    pipeline = ToolReflectionPipeline(registry=reg, enabled=False)
    result = await pipeline.execute("fake", {})
    assert result == "hello"


@pytest.mark.asyncio
async def test_pipeline_no_annotation_on_success():
    tool = FakeTool(results=["good result"])
    reg = _make_registry(tool)
    pipeline = ToolReflectionPipeline(registry=reg, enabled=True)
    result = await pipeline.execute("fake", {})
    assert result == "good result"
    assert "[REFLECTION]" not in result


@pytest.mark.asyncio
async def test_pipeline_annotates_truncated_result():
    tool = FakeTool(results=["partial output [truncated]"])
    reg = _make_registry(tool)
    pipeline = ToolReflectionPipeline(registry=reg, enabled=True)
    result = await pipeline.execute("fake", {})
    assert "[REFLECTION]" in result
    assert "truncated" in result.lower()


@pytest.mark.asyncio
async def test_pipeline_retries_on_error():
    # First call fails, second succeeds
    tool = FakeTool(results=["Error: connection timeout", "success data"])
    reg = _make_registry(tool)
    pipeline = ToolReflectionPipeline(registry=reg, enabled=True, max_retries=2)
    result = await pipeline.execute("fake", {})
    assert tool._call_count >= 2  # At least one retry happened
    assert "success data" in result


@pytest.mark.asyncio
async def test_pipeline_circuit_breaks_after_repeated_failures():
    tool = FakeTool(tool_name="web_search", results=["Error: failed"])
    reg = _make_registry(tool)
    pipeline = ToolReflectionPipeline(
        registry=reg, enabled=True, max_consecutive_failures=2, max_retries=1
    )
    # First two calls trip the breaker
    await pipeline.execute("web_search", {"query": "a"})
    await pipeline.execute("web_search", {"query": "b"})
    # Third call should be blocked
    result = await pipeline.execute("web_search", {"query": "c"})
    assert "[CIRCUIT_BREAK]" in result


# ===========================================================================
# ToolRegistry.execute_raw tests
# ===========================================================================


@pytest.mark.asyncio
async def test_execute_raw_no_hint_suffix():
    tool = FakeTool(results=["Error: something went wrong"])
    reg = _make_registry(tool)
    result = await reg.execute_raw("fake", {})
    assert result == "Error: something went wrong"
    assert "[Analyze" not in result


@pytest.mark.asyncio
async def test_execute_with_hint_suffix():
    tool = FakeTool(results=["Error: something went wrong"])
    reg = _make_registry(tool)
    result = await reg.execute("fake", {})
    assert "[Analyze the error" in result
