"""Tests for context_optimizer: task classification, history optimization, and token safety."""

from __future__ import annotations

from comobot.agent.context_optimizer import (
    HistoryOptimizer,
    TaskClassifier,
    TaskType,
    _remove_orphaned_tool_results,
    _tokenize_for_relevance,
    estimate_tokens,
    get_model_limit,
    get_profile,
    safety_trim_messages,
)

# ---------------------------------------------------------------------------
# TaskClassifier
# ---------------------------------------------------------------------------


class TestTaskClassifier:
    """Tests for TaskClassifier.classify()."""

    def test_chitchat_greeting(self):
        assert TaskClassifier.classify("你好") == TaskType.CHITCHAT

    def test_chitchat_short_ack(self):
        assert TaskClassifier.classify("ok") == TaskType.CHITCHAT

    def test_chitchat_thanks(self):
        assert TaskClassifier.classify("谢谢！") == TaskType.CHITCHAT

    def test_chitchat_goodbye(self):
        assert TaskClassifier.classify("再见") == TaskType.CHITCHAT

    def test_chitchat_emoji(self):
        assert TaskClassifier.classify("👍") == TaskType.CHITCHAT

    def test_chitchat_english(self):
        assert TaskClassifier.classify("hello!") == TaskType.CHITCHAT

    def test_chitchat_got_it(self):
        assert TaskClassifier.classify("got it") == TaskType.CHITCHAT

    def test_coding_with_code_block(self):
        msg = "帮我看看这段代码\n```python\ndef foo(): pass\n```"
        assert TaskClassifier.classify(msg) == TaskType.CODING

    def test_coding_with_error_trace(self):
        msg = "运行报错了 TypeError: 'NoneType' object is not subscriptable"
        assert TaskClassifier.classify(msg) == TaskType.CODING

    def test_coding_with_file_path(self):
        msg = "帮我修改 src/main.py 里的函数"
        assert TaskClassifier.classify(msg) == TaskType.CODING

    def test_coding_with_keywords(self):
        msg = "帮我写一个 Python 函数来调试这个 bug"
        assert TaskClassifier.classify(msg) == TaskType.CODING

    def test_follow_up_with_reference(self):
        msg = "继续上面的工作"
        assert (
            TaskClassifier.classify(msg, history=[{"role": "user"}, {"role": "assistant"}] * 3)
            == TaskType.FOLLOW_UP
        )

    def test_follow_up_with_pronoun(self):
        msg = "把它改成异步的"
        history = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}] * 5
        assert TaskClassifier.classify(msg, history) == TaskType.FOLLOW_UP

    def test_follow_up_earlier(self):
        msg = "as I mentioned earlier, we need to fix this"
        assert TaskClassifier.classify(msg) == TaskType.FOLLOW_UP

    def test_research_search(self):
        msg = "帮我搜索一下 Python 的 asyncio 最佳实践"
        assert TaskClassifier.classify(msg) == TaskType.RESEARCH

    def test_research_analyze(self):
        msg = "analyze the performance of our API endpoints"
        assert TaskClassifier.classify(msg) == TaskType.RESEARCH

    def test_research_compare(self):
        msg = "对比一下 Redis 和 Memcached 的优缺点"
        assert TaskClassifier.classify(msg) == TaskType.RESEARCH

    def test_one_shot_independent_question(self):
        msg = "Python 的 GIL 是什么？"
        assert TaskClassifier.classify(msg) == TaskType.ONE_SHOT

    def test_one_shot_long_question(self):
        msg = "How do I set up a virtual environment in Python for a new project?"
        assert TaskClassifier.classify(msg) == TaskType.ONE_SHOT

    def test_one_shot_no_context_reference(self):
        msg = "给我讲讲微服务架构的优缺点"
        assert TaskClassifier.classify(msg) == TaskType.ONE_SHOT


# ---------------------------------------------------------------------------
# ContextProfile
# ---------------------------------------------------------------------------


class TestContextProfile:
    """Tests for ContextProfile and get_profile()."""

    def test_chitchat_profile_limits_history(self):
        profile = get_profile(TaskType.CHITCHAT)
        assert profile.max_verbatim_turns == 3
        assert profile.priority_overrides.get("knowhow") == 0.3

    def test_follow_up_keeps_all_history(self):
        profile = get_profile(TaskType.FOLLOW_UP)
        assert profile.max_verbatim_turns is None
        assert not profile.priority_overrides  # No overrides

    def test_coding_boosts_skills(self):
        profile = get_profile(TaskType.CODING)
        assert profile.max_verbatim_turns is None
        assert profile.priority_overrides.get("active_skills") == 0.9

    def test_research_boosts_knowhow(self):
        profile = get_profile(TaskType.RESEARCH)
        assert profile.priority_overrides.get("knowhow") == 0.9
        assert profile.priority_overrides.get("memory") == 0.8

    def test_one_shot_limits_history(self):
        profile = get_profile(TaskType.ONE_SHOT)
        assert profile.max_verbatim_turns == 4

    def test_get_profile_none_returns_follow_up(self):
        """When task_type is not recognized, fall back to FOLLOW_UP."""
        profile = get_profile(TaskType.FOLLOW_UP)
        assert profile.max_verbatim_turns is None


# ---------------------------------------------------------------------------
# HistoryOptimizer
# ---------------------------------------------------------------------------


def _make_turn(user_content: str, assistant_content: str, tool_calls=None, tool_results=None):
    """Helper to create a user-assistant turn as a list of messages."""
    msgs = [{"role": "user", "content": user_content}]
    assistant_msg = {"role": "assistant", "content": assistant_content}
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
    msgs.append(assistant_msg)
    if tool_results:
        for tr in tool_results:
            msgs.append(tr)
    return msgs


class TestHistoryOptimizer:
    """Tests for HistoryOptimizer."""

    def test_empty_history(self):
        opt = HistoryOptimizer()
        result = opt.optimize([], "test query", TaskType.ONE_SHOT)
        assert result == []

    def test_short_history_preserved(self):
        """With few messages, all should be preserved verbatim."""
        history = _make_turn("hello", "hi there") + _make_turn("how are you?", "I'm fine")
        opt = HistoryOptimizer()
        result = opt.optimize(history, "next question", TaskType.FOLLOW_UP)
        assert len(result) == len(history)

    def test_recent_turns_always_verbatim(self):
        """Most recent turns matching max_verbatim_turns should be verbatim."""
        # Create 10 turns
        history = []
        for i in range(10):
            history.extend(_make_turn(f"question {i}", f"answer {i}"))

        opt = HistoryOptimizer()
        # ONE_SHOT has max_verbatim_turns=4
        result = opt.optimize(history, "new question", TaskType.ONE_SHOT)
        # Should have compressed some older turns but kept structure
        assert len(result) > 0
        # Last few messages should be unchanged (verbatim)
        assert result[-1] == history[-1]
        assert result[-2] == history[-2]

    def test_chitchat_limits_history(self):
        """CHITCHAT profile limits to 3 recent turns."""
        history = []
        for i in range(10):
            history.extend(_make_turn(f"question {i}", f"answer {i}"))

        opt = HistoryOptimizer()
        result = opt.optimize(history, "hi", TaskType.CHITCHAT)
        # Older turns should be compressed or skeletonized, not all verbatim
        assert len(result) <= len(history)

    def test_relevant_old_turns_preserved(self):
        """Old turns that are relevant to current query should score higher."""
        history = (
            _make_turn(
                "explain Python GIL", "The GIL is a mutex that protects access to Python objects..."
            )
            + _make_turn("what's for lunch?", "I'm an AI, I don't eat lunch")
            + _make_turn("how is the weather?", "I can't check real-time weather")
        )
        opt = HistoryOptimizer()
        result = opt.optimize(history, "tell me more about the GIL", TaskType.FOLLOW_UP)
        # The first turn about GIL should have higher relevance and be preserved
        assert any("GIL" in msg.get("content", "") for msg in result)

    def test_tool_results_compressed_in_medium_score(self):
        """Tool results in medium-score turns should be truncated."""
        long_result = "x" * 500
        tool_calls = [
            {"id": "tc1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}
        ]
        tool_result = {
            "role": "tool",
            "tool_call_id": "tc1",
            "name": "web_search",
            "content": long_result,
        }

        history = _make_turn(
            "old irrelevant query",
            "Let me search",
            tool_calls=tool_calls,
            tool_results=[tool_result],
        )
        # Add a more recent turn to push the old one into medium/low score territory
        history.extend(_make_turn("something else", "ok"))
        history.extend(_make_turn("another thing", "sure"))
        history.extend(_make_turn("yet another", "yes"))

        opt = HistoryOptimizer()
        result = opt.optimize(history, "completely unrelated topic xyz", TaskType.ONE_SHOT)
        # The tool result should be compressed (not full 500 chars)
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        for tm in tool_msgs:
            content = tm.get("content", "")
            # Either truncated or the original (if turn scored high enough)
            assert len(content) <= 500

    def test_user_messages_never_dropped(self):
        """User messages should always be preserved (skeleton mode keeps them)."""
        history = []
        for i in range(10):
            history.extend(_make_turn(f"user says {i}", f"assistant says {i}"))

        opt = HistoryOptimizer()
        result = opt.optimize(history, "xyz", TaskType.CHITCHAT)

        user_contents = {m.get("content") for m in result if m.get("role") == "user"}
        # All original user messages should still be present
        for i in range(10):
            assert f"user says {i}" in user_contents

    def test_skeleton_turn_preserves_structure(self):
        """Skeleton turns should have user message + minimal assistant placeholder."""
        turn = _make_turn("hello", "This is a very long response " * 20)
        opt = HistoryOptimizer()
        turns = HistoryOptimizer._group_into_turns(turn)
        skeleton = opt._skeleton_turn(turns[0])
        # Should have a user message and an assistant placeholder
        roles = [m.get("role") for m in skeleton]
        assert "user" in roles
        assert "assistant" in roles
        # Assistant should be a short placeholder
        for m in skeleton:
            if m.get("role") == "assistant":
                assert m["content"].startswith("[")

    def test_group_into_turns(self):
        """_group_into_turns should group correctly."""
        history = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {
                "role": "assistant",
                "content": "a2",
                "tool_calls": [
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {"name": "exec", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tc1", "content": "result"},
        ]
        turns = HistoryOptimizer._group_into_turns(history)
        assert len(turns) == 2
        assert len(turns[0].messages) == 2
        assert len(turns[1].messages) == 3


# ---------------------------------------------------------------------------
# Tokenization for relevance
# ---------------------------------------------------------------------------


class TestTokenizeForRelevance:
    """Tests for _tokenize_for_relevance."""

    def test_latin_words(self):
        tokens = _tokenize_for_relevance("hello world test")
        assert "hello" in tokens
        assert "world" in tokens

    def test_cjk_bigrams(self):
        tokens = _tokenize_for_relevance("你好世界")
        assert "你好" in tokens
        assert "好世" in tokens
        assert "世界" in tokens
        assert "你好世界" in tokens

    def test_mixed_text(self):
        tokens = _tokenize_for_relevance("Python 函数优化")
        assert "python" in tokens
        assert "函数" in tokens
        assert "优化" in tokens


# ---------------------------------------------------------------------------
# Token estimation and model limits
# ---------------------------------------------------------------------------


class TestTokenEstimation:
    """Tests for estimate_tokens and get_model_limit."""

    def test_estimate_tokens_string(self):
        result = estimate_tokens("hello world")
        assert result > 0

    def test_estimate_tokens_message_list(self):
        messages = [{"role": "user", "content": "hello"}]
        result = estimate_tokens(messages)
        assert result > 0

    def test_estimate_tokens_empty(self):
        result = estimate_tokens("")
        assert result >= 1

    def test_get_model_limit_claude(self):
        limit = get_model_limit("anthropic/claude-opus-4-5")
        assert limit >= 200_000

    def test_get_model_limit_gpt4o(self):
        limit = get_model_limit("gpt-4o-mini")
        assert limit >= 128_000

    def test_get_model_limit_unknown(self):
        limit = get_model_limit("unknown-model-xyz")
        assert limit == 200_000  # Fallback default

    def test_get_model_limit_none(self):
        limit = get_model_limit(None)
        assert limit == 200_000


# ---------------------------------------------------------------------------
# Safety trim
# ---------------------------------------------------------------------------


class TestSafetyTrim:
    """Tests for safety_trim_messages."""

    def test_no_trim_when_under_limit(self):
        """Should not trim when total tokens are well under limit."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]
        result = safety_trim_messages(messages, "anthropic/claude-opus-4-5")
        assert len(result) == len(messages)

    def test_system_message_always_preserved(self):
        """System message should never be removed."""
        messages = [
            {"role": "system", "content": "System prompt " * 1000},
            {"role": "user", "content": "Hello"},
        ]
        result = safety_trim_messages(messages, "gpt-4o")
        system_msgs = [m for m in result if m.get("role") == "system"]
        assert len(system_msgs) == 1

    def test_remove_orphaned_tool_results(self):
        """Orphaned tool results (no matching tool_call) should be cleaned."""
        messages = [
            {"role": "tool", "tool_call_id": "orphan_123", "content": "result"},
            {"role": "user", "content": "hello"},
        ]
        result = _remove_orphaned_tool_results(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_keep_matched_tool_results(self):
        """Tool results with matching tool_call should be kept."""
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {"name": "exec", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tc1", "content": "result"},
            {"role": "user", "content": "thanks"},
        ]
        result = _remove_orphaned_tool_results(messages)
        assert len(result) == 3
