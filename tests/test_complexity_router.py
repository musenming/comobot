"""Tests for complexity router middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from comobot.agent.middleware.base import AgentContext
from comobot.agent.middleware.complexity import (
    ComplexityRouter,
    EscalationSignal,
    ToolStats,
)


class TestEscalationSignal:
    def test_is_exception(self):
        sig = EscalationSignal(reason="too many tools", completed_context="prior work")
        assert isinstance(sig, Exception)
        assert sig.reason == "too many tools"
        assert sig.completed_context == "prior work"


class TestToolStats:
    def test_defaults(self):
        stats = ToolStats()
        assert stats.tool_count == 0
        assert stats.search_count == 0
        assert stats.error_count == 0
        assert stats.iteration_count == 0


class TestComplexityRouter:
    def _make_ctx(self, content: str = "Hello") -> AgentContext:
        return AgentContext(
            message_content=content,
            session_key="test:123",
            channel="test",
            chat_id="123",
        )

    @pytest.mark.asyncio
    async def test_simple_message_stays_simple(self):
        router = ComplexityRouter()
        ctx = self._make_ctx("What is 2+2?")
        next_mw = AsyncMock(return_value=ctx)

        result = await router.process(ctx, next_mw)
        assert result.complexity == "simple"
        next_mw.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_explicit_plan_prefix(self):
        router = ComplexityRouter()
        ctx = self._make_ctx("/plan Analyze this codebase")
        next_mw = AsyncMock(return_value=ctx)

        result = await router.process(ctx, next_mw)
        assert result.complexity == "complex"
        assert result.message_content == "Analyze this codebase"

    @pytest.mark.asyncio
    async def test_explicit_think_prefix(self):
        router = ComplexityRouter()
        ctx = self._make_ctx("/think Deep analysis needed")
        next_mw = AsyncMock(return_value=ctx)

        result = await router.process(ctx, next_mw)
        assert result.complexity == "complex"
        assert result.message_content == "Deep analysis needed"

    @pytest.mark.asyncio
    async def test_explicit_deep_prefix(self):
        router = ComplexityRouter()
        ctx = self._make_ctx("/deep Compare A and B")
        next_mw = AsyncMock(return_value=ctx)

        result = await router.process(ctx, next_mw)
        assert result.complexity == "complex"

    @pytest.mark.asyncio
    async def test_planning_disabled(self):
        router = ComplexityRouter(planning_enabled=False)
        ctx = self._make_ctx("/plan Something")
        next_mw = AsyncMock(return_value=ctx)

        result = await router.process(ctx, next_mw)
        assert result.complexity == "simple"
        # Content should NOT be stripped when planning is disabled
        assert result.message_content == "/plan Something"

    def test_tool_callback_escalation_on_tool_count(self):
        router = ComplexityRouter(escalation_tool_count=3)
        ctx = self._make_ctx()
        stats, callback = router.create_tool_callback(ctx, [])

        callback("read_file", "ok", True)
        callback("write_file", "ok", True)
        # Third call should trigger escalation
        with pytest.raises(EscalationSignal):
            callback("exec", "ok", True)

    def test_tool_callback_escalation_on_search_count(self):
        router = ComplexityRouter(escalation_search_count=2)
        ctx = self._make_ctx()
        stats, callback = router.create_tool_callback(ctx, [])

        callback("web_search", "results", True)
        with pytest.raises(EscalationSignal):
            callback("memory_search", "results", True)

    def test_tool_callback_escalation_on_error_count(self):
        router = ComplexityRouter(escalation_error_count=2)
        ctx = self._make_ctx()
        stats, callback = router.create_tool_callback(ctx, [])

        callback("exec", "Error: failed", False)
        with pytest.raises(EscalationSignal):
            callback("exec", "Error: failed again", False)

    def test_tool_callback_no_escalation_below_threshold(self):
        router = ComplexityRouter(escalation_tool_count=10)
        ctx = self._make_ctx()
        stats, callback = router.create_tool_callback(ctx, [])

        for i in range(5):
            callback("read_file", "ok", True)
        # Should not raise
        assert stats.tool_count == 5

    def test_llm_self_trigger_detects_plan_mode(self):
        router = ComplexityRouter(llm_self_trigger=True)
        assert router.check_llm_self_trigger("[PLAN_MODE] This needs planning")
        assert router.check_llm_self_trigger("  [PLAN_MODE] with leading space")

    def test_llm_self_trigger_ignores_normal(self):
        router = ComplexityRouter(llm_self_trigger=True)
        assert not router.check_llm_self_trigger("Just a normal response")
        assert not router.check_llm_self_trigger(None)
        assert not router.check_llm_self_trigger("")

    def test_llm_self_trigger_disabled(self):
        router = ComplexityRouter(llm_self_trigger=False)
        assert not router.check_llm_self_trigger("[PLAN_MODE] something")

    def test_escalation_reason_formatting(self):
        router = ComplexityRouter()
        reason = router._escalation_reason(
            ToolStats(tool_count=6, search_count=4, error_count=0, iteration_count=3)
        )
        assert "6 tools" in reason
        assert "4 times" in reason

    def test_compile_completed_context(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Let me help"},
            {"role": "tool", "name": "web_search", "content": "Search results here"},
        ]
        ctx = ComplexityRouter._compile_completed_context(messages)
        assert "[web_search]" in ctx
        assert "Search results" in ctx
