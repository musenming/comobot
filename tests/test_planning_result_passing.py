"""Tests for planning system inter-step result passing improvements."""

from __future__ import annotations

import json

import pytest

# Import the improved _try_parse_structured from loop module
from comobot.agent.loop import _try_parse_structured
from comobot.agent.planning.executor import TaskExecutor
from comobot.agent.planning.models import TaskPlan, TaskStep

# ---------------------------------------------------------------------------
# _try_parse_structured
# ---------------------------------------------------------------------------


class TestTryParseStructured:
    """Tests for the enhanced JSON parser."""

    def test_basic_fenced_json(self):
        text = 'Some content here.\n```json\n{"summary": "found 3 files", "findings": ["a", "b"]}\n```'
        result = _try_parse_structured(text)
        assert result is not None
        assert result["summary"] == "found 3 files"
        assert len(result["findings"]) == 2

    def test_nested_json(self):
        """Nested objects should parse correctly with greedy match."""
        text = '```json\n{"summary": "done", "findings": [{"key": "value"}], "meta": {"nested": true}}\n```'
        result = _try_parse_structured(text)
        assert result is not None
        assert result["summary"] == "done"
        assert result["meta"]["nested"] is True

    def test_no_json_returns_none(self):
        result = _try_parse_structured("Just plain text, no JSON here.")
        assert result is None

    def test_empty_returns_none(self):
        assert _try_parse_structured("") is None
        assert _try_parse_structured(None) is None

    def test_json_without_summary_returns_none(self):
        text = '```json\n{"key": "value"}\n```'
        result = _try_parse_structured(text)
        assert result is None

    def test_bare_json_with_summary(self):
        """Should find bare JSON with 'summary' key even without fences."""
        text = 'Some text {"summary": "hello", "findings": []} more text'
        result = _try_parse_structured(text)
        assert result is not None
        assert result["summary"] == "hello"

    def test_all_structured_fields(self):
        data = {
            "summary": "Implemented feature X",
            "findings": ["f1", "f2"],
            "actions_taken": ["wrote file.py", "ran tests"],
            "artifacts": ["/src/file.py", "https://example.com"],
        }
        text = f"Detailed text here.\n```json\n{json.dumps(data)}\n```"
        result = _try_parse_structured(text)
        assert result is not None
        assert result["actions_taken"] == ["wrote file.py", "ran tests"]
        assert result["artifacts"] == ["/src/file.py", "https://example.com"]

    def test_json_with_trailing_whitespace(self):
        text = '```json\n{"summary": "done"}\n```  \n  '
        result = _try_parse_structured(text)
        assert result is not None


# ---------------------------------------------------------------------------
# TaskExecutor — revision result preservation
# ---------------------------------------------------------------------------


class TestExecutorRevisionResults:
    """Tests that completed step results are preserved across revision rounds."""

    @pytest.mark.asyncio
    async def test_revision_preserves_prior_results(self):
        """Non-revised steps should have their results available to revised steps."""
        step1 = TaskStep(id="step_1", description="Research")
        step2 = TaskStep(id="step_2", description="Analyze", dependencies=["step_1"])

        plan = TaskPlan(goal="test", steps=[step1, step2])

        # First execution: both steps succeed
        call_log: list[tuple[str, dict]] = []

        async def run_step(step, plan, prior_results):
            call_log.append((step.id, dict(prior_results)))
            return f"Result of {step.id}"

        executor = TaskExecutor(provider=None, run_step_fn=run_step)
        await executor.execute(plan)

        assert step1.status == "done"
        assert step2.status == "done"
        assert step1.result == "Result of step_1"

        # Now simulate revision: reset step_2 to pending, keep step_1 as done
        step2.status = "pending"
        step2.result = None
        call_log.clear()

        await executor.execute(plan)

        # step_2 should have received step_1's result even though step_1 didn't re-run
        assert len(call_log) == 1  # Only step_2 ran
        assert call_log[0][0] == "step_2"
        assert "step_1" in call_log[0][1]
        assert call_log[0][1]["step_1"] == "Result of step_1"

    @pytest.mark.asyncio
    async def test_failed_step_result_in_prior(self):
        """Failed step results should appear in prior_results with [FAILED] prefix."""
        step1 = TaskStep(id="step_1", description="Might fail")
        step2 = TaskStep(id="step_2", description="Depends on step_1", dependencies=["step_1"])

        plan = TaskPlan(goal="test", steps=[step1, step2])

        call_count = 0

        async def run_step(step, plan, prior_results):
            nonlocal call_count
            call_count += 1
            if step.id == "step_1":
                raise RuntimeError("Network timeout")
            # step_2 should see the failure
            return f"step_2 got: {prior_results.get('step_1', 'nothing')}"

        executor = TaskExecutor(provider=None, run_step_fn=run_step)
        await executor.execute(plan)

        assert step1.status == "failed"
        assert step2.status == "done"
        assert "[FAILED]" in step2.result
        assert "Network timeout" in step2.result

    @pytest.mark.asyncio
    async def test_parallel_steps_no_interference(self):
        """Steps at the same topological level should run in parallel without sharing results."""
        step1 = TaskStep(id="step_1", description="Research A")
        step2 = TaskStep(id="step_2", description="Research B")
        step3 = TaskStep(id="step_3", description="Combine", dependencies=["step_1", "step_2"])

        plan = TaskPlan(goal="test", steps=[step1, step2, step3])

        execution_order: list[str] = []

        async def run_step(step, plan, prior_results):
            execution_order.append(step.id)
            if step.id == "step_3":
                # Should have both prior results
                assert "step_1" in prior_results
                assert "step_2" in prior_results
            return f"Result of {step.id}"

        executor = TaskExecutor(provider=None, run_step_fn=run_step)
        await executor.execute(plan)

        # step_1 and step_2 should run before step_3
        assert execution_order.index("step_3") > execution_order.index("step_1")
        assert execution_order.index("step_3") > execution_order.index("step_2")


# ---------------------------------------------------------------------------
# TaskStep structured_result field
# ---------------------------------------------------------------------------


class TestTaskStepStructuredResult:
    """Tests for the new structured_result field on TaskStep."""

    def test_structured_result_default_none(self):
        step = TaskStep(id="step_1", description="test")
        assert step.structured_result is None

    def test_structured_result_can_be_set(self):
        step = TaskStep(id="step_1", description="test")
        step.structured_result = {"summary": "done", "findings": ["a"]}
        assert step.structured_result["summary"] == "done"

    def test_structured_result_preserved_after_status_change(self):
        step = TaskStep(id="step_1", description="test")
        step.structured_result = {"summary": "done"}
        step.status = "done"
        assert step.structured_result is not None


# ---------------------------------------------------------------------------
# Topological levels (edge case coverage)
# ---------------------------------------------------------------------------


class TestTopologicalLevels:
    """Tests for DAG execution ordering."""

    def test_linear_chain(self):
        steps = [
            TaskStep(id="s1", description="first"),
            TaskStep(id="s2", description="second", dependencies=["s1"]),
            TaskStep(id="s3", description="third", dependencies=["s2"]),
        ]
        levels = TaskExecutor._topological_levels(steps)
        assert len(levels) == 3
        assert levels[0][0].id == "s1"
        assert levels[1][0].id == "s2"
        assert levels[2][0].id == "s3"

    def test_diamond_dependency(self):
        """Diamond: s1 -> s2, s1 -> s3, s2+s3 -> s4."""
        steps = [
            TaskStep(id="s1", description="start"),
            TaskStep(id="s2", description="left", dependencies=["s1"]),
            TaskStep(id="s3", description="right", dependencies=["s1"]),
            TaskStep(id="s4", description="join", dependencies=["s2", "s3"]),
        ]
        levels = TaskExecutor._topological_levels(steps)
        assert len(levels) == 3
        level_ids = [[s.id for s in level] for level in levels]
        assert level_ids[0] == ["s1"]
        assert set(level_ids[1]) == {"s2", "s3"}
        assert level_ids[2] == ["s4"]

    def test_all_independent(self):
        steps = [
            TaskStep(id="s1", description="a"),
            TaskStep(id="s2", description="b"),
            TaskStep(id="s3", description="c"),
        ]
        levels = TaskExecutor._topological_levels(steps)
        assert len(levels) == 1
        assert len(levels[0]) == 3
