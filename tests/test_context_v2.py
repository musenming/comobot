"""Tests for context engineering v2: feedback/episodic/plan layer injection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from comobot.agent.context import ContextBuilder


class TestContextBuilderV2:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        (tmp_path / "memory").mkdir()
        (tmp_path / "feedback").mkdir()
        (tmp_path / "episodic").mkdir()
        return tmp_path

    @pytest.fixture
    def builder(self, workspace):
        return ContextBuilder(workspace)

    def test_build_system_prompt_basic(self, builder):
        prompt = builder.build_system_prompt()
        assert "comobot" in prompt
        assert "Workspace" in prompt

    def test_build_system_prompt_with_plan_context(self, builder):
        prompt = builder.build_system_prompt(plan_context="Step 1: Research\nStep 2: Implement")
        assert "Current Task Plan" in prompt
        assert "Step 1: Research" in prompt

    def test_build_system_prompt_with_plan_self_trigger(self, builder):
        prompt = builder.build_system_prompt(plan_self_trigger=True)
        assert "[PLAN_MODE]" in prompt
        assert "Plan Mode Self-Trigger" in prompt

    def test_build_system_prompt_no_plan_self_trigger(self, builder):
        prompt = builder.build_system_prompt(plan_self_trigger=False)
        assert "Plan Mode Self-Trigger" not in prompt

    def test_build_system_prompt_with_memory_injector(self, workspace):
        from comobot.agent.episodic.injector import MemoryInjector

        # Write a feedback file
        (workspace / "feedback" / "fb_001.md").write_text(
            "---\ntype: feedback\n---\n\nAlways use snake_case"
        )

        builder = ContextBuilder(workspace)
        injector = MemoryInjector(workspace)
        builder.set_memory_injector(injector)

        prompt = builder.build_system_prompt(user_message="Write a function")
        assert "User Preferences" in prompt
        assert "snake_case" in prompt

    def test_build_messages_passes_plan_context(self, builder):
        messages = builder.build_messages(
            history=[],
            current_message="Do something",
            plan_context="Step 1: Research",
        )
        system_content = messages[0]["content"]
        assert "Current Task Plan" in system_content
        assert "Step 1: Research" in system_content

    def test_build_messages_passes_plan_self_trigger(self, builder):
        messages = builder.build_messages(
            history=[],
            current_message="Do something",
            plan_self_trigger=True,
        )
        system_content = messages[0]["content"]
        assert "[PLAN_MODE]" in system_content

    def test_set_memory_injector(self, builder):
        injector = MagicMock()
        injector.inject.return_value = ["# Feedback\n- Test"]
        builder.set_memory_injector(injector)
        assert builder._memory_injector is injector

        prompt = builder.build_system_prompt(user_message="Hello")
        injector.inject.assert_called_once_with("Hello")
        assert "Feedback" in prompt


class TestMemorySearchDiscovery:
    """Test that _discover_files includes episodic/ and feedback/ directories."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        (tmp_path / "memory").mkdir()
        (tmp_path / "knowhow").mkdir()
        (tmp_path / "episodic").mkdir()
        (tmp_path / "feedback").mkdir()
        return tmp_path

    def test_discover_includes_episodic(self, workspace):
        from comobot.agent.memory_search import MemorySearchEngine

        # Create episodic file
        (workspace / "episodic" / "ep_001.md").write_text("test memory")

        engine = MemorySearchEngine(workspace)
        files = engine._discover_files()
        paths = [f[0] for f in files]
        assert "episodic/ep_001.md" in paths

    def test_discover_includes_feedback(self, workspace):
        from comobot.agent.memory_search import MemorySearchEngine

        (workspace / "feedback" / "fb_001.md").write_text("test feedback")

        engine = MemorySearchEngine(workspace)
        files = engine._discover_files()
        paths = [f[0] for f in files]
        assert "feedback/fb_001.md" in paths

    def test_discover_skips_hidden_files(self, workspace):
        from comobot.agent.memory_search import MemorySearchEngine

        (workspace / "episodic" / ".hidden.md").write_text("hidden")
        (workspace / "feedback" / ".hidden.md").write_text("hidden")

        engine = MemorySearchEngine(workspace)
        files = engine._discover_files()
        paths = [f[0] for f in files]
        assert not any(".hidden" in p for p in paths)

    def test_discover_without_episodic_dir(self, tmp_path):
        from comobot.agent.memory_search import MemorySearchEngine

        (tmp_path / "memory").mkdir()
        engine = MemorySearchEngine(tmp_path)
        files = engine._discover_files()
        # Should not crash, just no episodic files
        paths = [f[0] for f in files]
        assert not any("episodic/" in p for p in paths)


class TestContextLayerRelevance:
    """Tests for _estimate_relevance and _budget_trim."""

    def test_estimate_relevance_exact_match(self):
        from comobot.agent.context import ContextBuilder

        content = "Python async programming with asyncio"
        user_msg = "Python async programming"
        score = ContextBuilder._estimate_relevance(content, user_msg)
        assert 0.3 <= score <= 0.9

    def test_estimate_relevance_no_overlap(self):
        from comobot.agent.context import ContextBuilder

        content = "The weather is sunny today"
        user_msg = "Python async asyncio"
        score = ContextBuilder._estimate_relevance(content, user_msg)
        # No overlap → jaccard=0 → score=0.3 (minimum)
        assert score == 0.3

    def test_estimate_relevance_cjk(self):
        from comobot.agent.context import ContextBuilder

        content = "张三和李四在讨论人工智能技术"
        user_msg = "张三 人工智能"
        score = ContextBuilder._estimate_relevance(content, user_msg)
        assert 0.3 <= score <= 0.9

    def test_budget_trim_preserves_high_priority(self):
        from comobot.agent.context import ContextBuilder, _ContextLayer

        layers = [
            _ContextLayer("identity", "I am comobot." * 500, priority=1.0),
            _ContextLayer("feedback", "User feedback." * 500, priority=1.0),
            _ContextLayer("memory", "Some memory." * 500, priority=0.3),
        ]
        # Very tight budget — only identity fits
        result = ContextBuilder._budget_trim(layers, max_tokens=200)
        names = [lay.name for lay in result]
        # identity and feedback both have priority=1.0 so neither can be dropped
        assert "identity" in names
        assert "feedback" in names
        # memory has low priority, should be trimmed first
        assert "memory" not in names

    def test_budget_trim_no_trim_when_under_budget(self):
        from comobot.agent.context import ContextBuilder, _ContextLayer

        layers = [
            _ContextLayer("identity", "I am comobot.", priority=1.0),
            _ContextLayer("memory", "Some memory.", priority=0.3),
        ]
        result = ContextBuilder._budget_trim(layers, max_tokens=10000)
        assert len(result) == 2

    def test_budget_trim_drops_lowest_priority_first(self):
        from comobot.agent.context import ContextBuilder, _ContextLayer

        big_text = "x" * 3000
        layers = [
            _ContextLayer("identity", big_text, priority=1.0),
            _ContextLayer("skills", big_text, priority=0.4),
            _ContextLayer("memory", big_text, priority=0.2),
            _ContextLayer("knowhow", big_text, priority=0.3),
        ]
        # 4 x 3000 chars ≈ 3428 tokens; budget = 2000 tokens
        # Should drop memory (0.2) and knowhow (0.3), keep identity (1.0) and skills (0.4)
        result = ContextBuilder._budget_trim(layers, max_tokens=2000)
        names = [lay.name for lay in result]
        assert "identity" in names
        assert "skills" in names
        # memory and knowhow are lowest priority
        assert "memory" not in names
        assert "knowhow" not in names


class TestSubagentResult:
    def test_from_text_with_json_block(self):
        from comobot.agent.subagent import SubagentResult

        text = """Here is the detailed analysis.
The system processes data efficiently.

```json
{
  "summary": "System processes data efficiently",
  "findings": ["Fast", "Reliable"],
  "actions_taken": ["Analyzed data"],
  "artifacts": ["/tmp/output.json"]
}
```"""
        result = SubagentResult.from_text(text)
        assert result.summary == "System processes data efficiently"
        assert result.findings == ["Fast", "Reliable"]
        assert result.actions_taken == ["Analyzed data"]
        assert result.artifacts == ["/tmp/output.json"]
        assert "detailed analysis" in result.detail

    def test_from_text_fallback_on_no_json(self):
        from comobot.agent.subagent import SubagentResult

        text = "Just plain text result without JSON."
        result = SubagentResult.from_text(text)
        assert result.detail == text
        assert result.summary == text[:200]

    def test_format_for_announce(self):
        from comobot.agent.subagent import SubagentResult

        result = SubagentResult(
            summary="Task done",
            findings=["Finding 1", "Finding 2"],
            actions_taken=["Action 1"],
            artifacts=["/path/file.py"],
            detail="Detailed explanation",
        )
        formatted = result.format_for_announce()
        assert "Summary: Task done" in formatted
        assert "Finding 1" in formatted
        assert "Action 1" in formatted
        assert "Artifacts:" in formatted
        assert "/path/file.py" in formatted


class TestTryParseStructured:
    def test_parse_json_fenced_block(self):
        from comobot.agent.loop import _try_parse_structured

        text = """Step result text.

```json
{
  "summary": "Analysis complete",
  "findings": ["Key insight"]
}
```"""
        result = _try_parse_structured(text)
        assert result is not None
        assert result["summary"] == "Analysis complete"
        assert result["findings"] == ["Key insight"]

    def test_no_json_returns_none(self):
        from comobot.agent.loop import _try_parse_structured

        text = "Just plain text with no JSON"
        assert _try_parse_structured(text) is None

    def test_empty_returns_none(self):
        from comobot.agent.loop import _try_parse_structured

        assert _try_parse_structured("") is None
        assert _try_parse_structured(None) is None
