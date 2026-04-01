"""Tests for planning engine: models, planner, executor, reflector."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from comobot.agent.planning.models import TaskPlan, TaskStep


class TestTaskStep:
    def test_defaults(self):
        step = TaskStep(id="step_1", description="Do something")
        assert step.agent_type == "general"
        assert step.status == "pending"
        assert step.dependencies == []
        assert step.result is None

    def test_custom_fields(self):
        step = TaskStep(
            id="step_2",
            description="Research topic",
            agent_type="researcher",
            dependencies=["step_1"],
            tools_hint=["web_search"],
        )
        assert step.agent_type == "researcher"
        assert step.dependencies == ["step_1"]


class TestTaskPlan:
    def test_empty_plan(self):
        plan = TaskPlan(goal="Test goal")
        assert plan.steps == []
        assert plan.status == "planning"
        assert plan.is_complete
        assert plan.current_step_index == 0

    def test_current_step_index(self):
        plan = TaskPlan(
            goal="Test",
            steps=[
                TaskStep(id="s1", description="A", status="done"),
                TaskStep(id="s2", description="B", status="pending"),
                TaskStep(id="s3", description="C", status="pending"),
            ],
        )
        assert plan.current_step_index == 1

    def test_is_complete(self):
        plan = TaskPlan(
            goal="Test",
            steps=[
                TaskStep(id="s1", description="A", status="done"),
                TaskStep(id="s2", description="B", status="done"),
            ],
        )
        assert plan.is_complete

    def test_not_complete_with_pending(self):
        plan = TaskPlan(
            goal="Test",
            steps=[
                TaskStep(id="s1", description="A", status="done"),
                TaskStep(id="s2", description="B", status="pending"),
            ],
        )
        assert not plan.is_complete

    def test_summary(self):
        plan = TaskPlan(
            goal="Build feature",
            steps=[
                TaskStep(id="s1", description="Research", status="done"),
                TaskStep(id="s2", description="Implement", status="pending", dependencies=["s1"]),
            ],
        )
        text = plan.summary()
        assert "Build feature" in text
        assert "[done] s1: Research" in text
        assert "(depends: s1)" in text


class TestTaskPlanner:
    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.chat = AsyncMock()
        return provider

    @pytest.mark.asyncio
    async def test_plan_parses_json(self, mock_provider):
        from comobot.agent.planning.planner import TaskPlanner

        mock_provider.chat.return_value = MagicMock(
            content=json.dumps({
                "goal": "Research and implement",
                "steps": [
                    {
                        "id": "step_1",
                        "description": "Research the topic",
                        "agent_type": "researcher",
                        "dependencies": [],
                        "tools_hint": ["web_search"],
                    },
                    {
                        "id": "step_2",
                        "description": "Write code",
                        "agent_type": "coder",
                        "dependencies": ["step_1"],
                        "tools_hint": ["write_file"],
                    },
                ],
            })
        )

        planner = TaskPlanner(mock_provider, max_steps=6)
        plan = await planner.plan("Research and implement feature X")

        assert plan.goal == "Research and implement"
        assert len(plan.steps) == 2
        assert plan.steps[0].agent_type == "researcher"
        assert plan.steps[1].dependencies == ["step_1"]
        assert plan.status == "executing"

    @pytest.mark.asyncio
    async def test_plan_fallback_on_bad_json(self, mock_provider):
        from comobot.agent.planning.planner import TaskPlanner

        mock_provider.chat.return_value = MagicMock(content="I can't parse this")
        planner = TaskPlanner(mock_provider)
        plan = await planner.plan("Do something")

        assert len(plan.steps) == 1
        assert plan.steps[0].agent_type == "general"

    @pytest.mark.asyncio
    async def test_plan_fallback_on_exception(self, mock_provider):
        from comobot.agent.planning.planner import TaskPlanner

        mock_provider.chat.side_effect = RuntimeError("API error")
        planner = TaskPlanner(mock_provider)
        plan = await planner.plan("Do something")

        assert len(plan.steps) == 1

    @pytest.mark.asyncio
    async def test_plan_with_markdown_json(self, mock_provider):
        from comobot.agent.planning.planner import TaskPlanner

        mock_provider.chat.return_value = MagicMock(
            content='```json\n{"goal": "Test", "steps": [{"id": "step_1", "description": "Do it"}]}\n```'
        )
        planner = TaskPlanner(mock_provider)
        plan = await planner.plan("Test task")
        assert len(plan.steps) == 1
        assert plan.steps[0].id == "step_1"

    @pytest.mark.asyncio
    async def test_plan_respects_max_steps(self, mock_provider):
        from comobot.agent.planning.planner import TaskPlanner

        steps = [{"id": f"step_{i}", "description": f"Step {i}"} for i in range(10)]
        mock_provider.chat.return_value = MagicMock(
            content=json.dumps({"goal": "Big task", "steps": steps})
        )
        planner = TaskPlanner(mock_provider, max_steps=3)
        plan = await planner.plan("Big task")
        assert len(plan.steps) == 3

    @pytest.mark.asyncio
    async def test_plan_with_bootstrap(self, mock_provider):
        from comobot.agent.planning.planner import TaskPlanner

        mock_provider.chat.return_value = MagicMock(
            content=json.dumps({
                "goal": "Continue work",
                "steps": [{"id": "step_1", "description": "Finish up"}],
            })
        )
        planner = TaskPlanner(mock_provider)
        _ = await planner.plan("Continue", bootstrap="Prior search results here")
        # Verify bootstrap was included in the call
        call_args = mock_provider.chat.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "Prior search results here" in user_msg


class TestTaskExecutor:
    @pytest.mark.asyncio
    async def test_execute_single_step(self):
        from comobot.agent.planning.executor import TaskExecutor

        async def run_step(step, plan, prior):
            return f"Result of {step.id}"

        provider = MagicMock()
        executor = TaskExecutor(provider, run_step_fn=run_step)
        plan = TaskPlan(
            goal="Simple",
            steps=[TaskStep(id="s1", description="Do it")],
        )
        result = await executor.execute(plan)
        assert result.steps[0].status == "done"
        assert result.steps[0].result == "Result of s1"

    @pytest.mark.asyncio
    async def test_execute_parallel_steps(self):
        from comobot.agent.planning.executor import TaskExecutor

        call_order = []

        async def run_step(step, plan, prior):
            call_order.append(step.id)
            return f"Done {step.id}"

        provider = MagicMock()
        executor = TaskExecutor(provider, run_step_fn=run_step)
        plan = TaskPlan(
            goal="Parallel",
            steps=[
                TaskStep(id="s1", description="A"),
                TaskStep(id="s2", description="B"),
            ],
        )
        result = await executor.execute(plan)
        assert all(s.status == "done" for s in result.steps)
        assert set(call_order) == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_execute_with_dependencies(self):
        from comobot.agent.planning.executor import TaskExecutor

        execution_order = []

        async def run_step(step, plan, prior):
            execution_order.append(step.id)
            return f"Result {step.id}"

        provider = MagicMock()
        executor = TaskExecutor(provider, run_step_fn=run_step)
        plan = TaskPlan(
            goal="Sequential",
            steps=[
                TaskStep(id="s1", description="First"),
                TaskStep(id="s2", description="Second", dependencies=["s1"]),
            ],
        )
        result = await executor.execute(plan)
        assert execution_order.index("s1") < execution_order.index("s2")
        assert result.steps[1].status == "done"

    @pytest.mark.asyncio
    async def test_execute_handles_step_failure(self):
        from comobot.agent.planning.executor import TaskExecutor

        async def run_step(step, plan, prior):
            if step.id == "s2":
                raise RuntimeError("Tool failed")
            return "ok"

        provider = MagicMock()
        executor = TaskExecutor(provider, run_step_fn=run_step)
        plan = TaskPlan(
            goal="Failure test",
            steps=[
                TaskStep(id="s1", description="OK"),
                TaskStep(id="s2", description="Fail"),
            ],
        )
        result = await executor.execute(plan)
        assert result.steps[0].status == "done"
        assert result.steps[1].status == "failed"
        assert "Tool failed" in result.steps[1].error

    @pytest.mark.asyncio
    async def test_topological_levels(self):
        from comobot.agent.planning.executor import TaskExecutor

        steps = [
            TaskStep(id="s1", description="A"),
            TaskStep(id="s2", description="B"),
            TaskStep(id="s3", description="C", dependencies=["s1", "s2"]),
            TaskStep(id="s4", description="D", dependencies=["s3"]),
        ]
        levels = TaskExecutor._topological_levels(steps)
        assert len(levels) == 3
        level_ids = [[s.id for s in level] for level in levels]
        assert set(level_ids[0]) == {"s1", "s2"}
        assert level_ids[1] == ["s3"]
        assert level_ids[2] == ["s4"]

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        from comobot.agent.planning.executor import TaskExecutor

        progress_calls = []

        async def on_progress(plan):
            progress_calls.append(plan.status)

        async def run_step(step, plan, prior):
            return "ok"

        provider = MagicMock()
        executor = TaskExecutor(provider, run_step_fn=run_step, on_progress=on_progress)
        plan = TaskPlan(
            goal="Progress",
            steps=[TaskStep(id="s1", description="A")],
        )
        await executor.execute(plan)
        assert len(progress_calls) >= 1


class TestReflector:
    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.chat = AsyncMock()
        return provider

    @pytest.mark.asyncio
    async def test_reflect_satisfied(self, mock_provider):
        from comobot.agent.planning.reflector import Reflector
        from comobot.providers.base import LLMResponse

        # Three LLM calls: reflector evaluation + synthesis + plan_summary
        mock_provider.chat.side_effect = [
            MagicMock(
                content=json.dumps({
                    "satisfied": True,
                    "summary": "All steps completed successfully.",
                    "revisions": [],
                })
            ),
            LLMResponse(content="Synthesized: Done.", finish_reason="stop"),
            LLMResponse(content="Plan executed step s1 successfully.", finish_reason="stop"),
        ]
        reflector = Reflector(mock_provider)
        plan = TaskPlan(
            goal="Test",
            steps=[TaskStep(id="s1", description="Do it", status="done", result="Done")],
        )
        result = await reflector.reflect(plan)
        assert result.satisfied
        assert "Synthesized" in result.summary  # synthesis replaces brief summary
        assert result.plan_summary == "Plan executed step s1 successfully."
        assert mock_provider.chat.await_count == 3

    @pytest.mark.asyncio
    async def test_reflect_needs_revision(self, mock_provider):
        from comobot.agent.planning.reflector import Reflector

        mock_provider.chat.return_value = MagicMock(
            content=json.dumps({
                "satisfied": False,
                "summary": "Step 1 missed key info.",
                "revisions": ["s1"],
            })
        )
        reflector = Reflector(mock_provider)
        plan = TaskPlan(
            goal="Test",
            steps=[TaskStep(id="s1", description="Research", status="done", result="Partial")],
        )
        result = await reflector.reflect(plan)
        assert not result.satisfied
        assert result.revisions == ["s1"]

    @pytest.mark.asyncio
    async def test_reflect_max_revisions_reached(self, mock_provider):
        from comobot.agent.planning.reflector import Reflector
        from comobot.providers.base import LLMResponse

        reflector = Reflector(mock_provider, max_revisions=2)
        plan = TaskPlan(
            goal="Test",
            revision_count=2,
            steps=[TaskStep(id="s1", description="A", status="done", result="R")],
        )
        # Max revisions reached: synthesis + plan_summary = two LLM calls
        mock_provider.chat.side_effect = None
        mock_provider.chat.return_value = LLMResponse(
            content="Synthesized result.", finish_reason="stop"
        )
        result = await reflector.reflect(plan)
        assert result.satisfied  # Auto-accept when max reached
        assert result.summary == "Synthesized result."
        assert mock_provider.chat.await_count == 2  # synthesis + plan_summary

    @pytest.mark.asyncio
    async def test_reflect_handles_llm_error(self, mock_provider):
        from comobot.agent.planning.reflector import Reflector

        mock_provider.chat.side_effect = RuntimeError("API down")
        reflector = Reflector(mock_provider)
        plan = TaskPlan(
            goal="Test",
            steps=[TaskStep(id="s1", description="A", status="done", result="Result text")],
        )
        result = await reflector.reflect(plan)
        assert result.satisfied
        assert "Result text" in result.summary
