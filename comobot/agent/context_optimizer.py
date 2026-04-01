"""Context optimization: task classification, history relevance scoring, and progressive compression.

Provides three capabilities that work together to build better context for the LLM:

1. **TaskClassifier** — zero-cost heuristic classification of user messages into task types
   (chitchat, one-shot, follow-up, coding, research).  Drives context composition.
2. **HistoryOptimizer** — scores conversation turns by recency + relevance, then applies
   progressive compression (verbatim / compressed / skeleton) instead of hard truncation.
3. **Token safety net** — lightweight model-limit awareness that trims only when approaching
   the model's context window.  Not the primary control — just a guardrail.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 3.5  # Fallback estimation ratio

# Fallback context window sizes (max input tokens) for models behind gateways
# where litellm.get_model_info() may fail.
_FALLBACK_MODEL_LIMITS: dict[str, int] = {
    "claude": 200_000,
    "gpt-4o": 128_000,
    "gpt-4": 128_000,
    "gpt-3.5": 16_385,
    "deepseek": 128_000,
    "gemini": 1_048_576,
    "qwen": 131_072,
    "o1": 200_000,
    "o3": 200_000,
    "o4": 200_000,
}


# ---------------------------------------------------------------------------
# Task classification
# ---------------------------------------------------------------------------


class TaskType(str, Enum):
    """Classifiable task types that drive context composition."""

    CHITCHAT = "chitchat"
    ONE_SHOT = "one_shot"
    FOLLOW_UP = "follow_up"
    CODING = "coding"
    RESEARCH = "research"


# -- Signal-detection keywords (cheap string ops, no LLM) --

_CHITCHAT_RE = re.compile(
    r"^(hi|hello|hey|你好|谢谢|thanks|thank you|ok|okay|好的|嗯|哈哈|"
    r"👍|🙏|早|晚安|good morning|good night|bye|再见|没事了|got it|"
    r"了解|明白|收到|知道了|懂了|sure|yep|yeah|yea|ya|np|no problem)[\s!！。.\?？]*$",
    re.IGNORECASE,
)

# Signals that the user is referring to prior conversation context.
_FOLLOW_UP_WORDS = frozenset(
    {
        "之前",
        "上面",
        "刚才",
        "继续",
        "接着",
        "前面",
        "上次",
        "还是那个",
        "改一下",
        "earlier",
        "above",
        "previous",
        "before",
        "continue",
        "keep going",
        "as I said",
        "like I mentioned",
        "the same",
        "go on",
        "following up",
    }
)

# Pronouns / demonstratives that reference prior context (lightweight check).
_PRONOUN_RE = re.compile(
    r"\b(it|its|this|that|these|those|them|the result|the output|the error|the file|the code)\b"
    r"|[它这那](?:[个些里面]|(?=[\u4e00-\u9fff]))"
    r"|(?:把|将|让|给)[它这那]",
    re.IGNORECASE,
)

# Coding-specific signals.
_CODE_BLOCK_RE = re.compile(r"```")
_FILE_PATH_RE = re.compile(r"[\w\-./\\]+\.\w{1,10}")  # e.g. src/main.py, ./config.json
_ERROR_TRACE_RE = re.compile(
    r"(Traceback|Error:|Exception|error\[|panic:|fatal:|FAILED|SyntaxError|TypeError"
    r"|ValueError|KeyError|ImportError|ModuleNotFoundError|AttributeError)",
    re.IGNORECASE,
)
_CODING_KEYWORDS = frozenset(
    {
        "代码",
        "函数",
        "类",
        "方法",
        "变量",
        "接口",
        "API",
        "bug",
        "报错",
        "编译",
        "运行",
        "执行",
        "脚本",
        "文件",
        "目录",
        "路径",
        "模块",
        "依赖",
        "安装",
        "配置",
        "重构",
        "调试",
        "code",
        "function",
        "class",
        "method",
        "variable",
        "interface",
        "bug",
        "error",
        "compile",
        "run",
        "execute",
        "script",
        "file",
        "directory",
        "path",
        "module",
        "dependency",
        "install",
        "config",
        "refactor",
        "debug",
        "import",
        "export",
        "deploy",
        "commit",
        "merge",
        "branch",
        "git",
        "docker",
        "pip",
        "npm",
        "yarn",
    }
)

# Research / analysis signals.
_RESEARCH_KEYWORDS = frozenset(
    {
        "搜索",
        "查找",
        "查询",
        "研究",
        "调研",
        "了解",
        "对比",
        "分析",
        "总结",
        "整理",
        "查一下",
        "帮我找",
        "有没有",
        "怎么样",
        "什么是",
        "search",
        "find",
        "look up",
        "research",
        "investigate",
        "analyze",
        "compare",
        "summarize",
        "what is",
        "how does",
        "explain",
        "tell me about",
    }
)


class TaskClassifier:
    """Classify user messages into task types using cheap heuristics."""

    @staticmethod
    def classify(message: str, history: list[dict[str, Any]] | None = None) -> TaskType:
        """Classify *message* into a :class:`TaskType`.

        The classification uses only string operations — zero LLM cost.
        """
        msg = message.strip()
        lower = msg.lower()
        hist = history or []

        # 1. Chitchat — short greetings / acknowledgements
        if _CHITCHAT_RE.match(msg):
            return TaskType.CHITCHAT
        if (
            len(msg) < 10
            and not _has_any_keyword(lower, _CODING_KEYWORDS | _RESEARCH_KEYWORDS)
            and not _has_any_keyword(lower, _FOLLOW_UP_WORDS)
            and not _PRONOUN_RE.search(msg)
        ):
            return TaskType.CHITCHAT

        # 2. Coding — strong signals
        coding_score = 0
        if _CODE_BLOCK_RE.search(msg):
            coding_score += 2
        if _ERROR_TRACE_RE.search(msg):
            coding_score += 2
        if _FILE_PATH_RE.search(msg):
            coding_score += 1
        coding_keyword_count = _count_keywords(lower, _CODING_KEYWORDS)
        if coding_keyword_count >= 2:
            coding_score += 2
        elif coding_keyword_count == 1:
            coding_score += 1
        if coding_score >= 2:
            return TaskType.CODING

        # 3. Follow-up — references to prior conversation
        follow_up_score = 0
        if _has_any_keyword(lower, _FOLLOW_UP_WORDS):
            follow_up_score += 2
        if _PRONOUN_RE.search(msg):
            follow_up_score += 1
        # Short messages in an active conversation are likely follow-ups
        if len(msg) < 50 and len(hist) > 4:
            follow_up_score += 1
        if follow_up_score >= 2:
            return TaskType.FOLLOW_UP

        # 4. Research — explicit search / analysis intent
        if _has_any_keyword(lower, _RESEARCH_KEYWORDS):
            return TaskType.RESEARCH

        # 5. Default: one-shot (independent question)
        return TaskType.ONE_SHOT


def _has_any_keyword(text: str, keywords: frozenset[str]) -> bool:
    return any(k in text for k in keywords)


def _count_keywords(text: str, keywords: frozenset[str]) -> int:
    return sum(1 for k in keywords if k in text)


# ---------------------------------------------------------------------------
# Context profiles — task-driven context composition
# ---------------------------------------------------------------------------


@dataclass
class ContextProfile:
    """Describes how context should be composed for a given task type."""

    # Max recent turns to keep in verbatim form.  None = keep all.
    max_verbatim_turns: int | None
    # Priority overrides for system prompt layers.
    # Keys are layer names (e.g. "skills_summary", "knowhow", "memory").
    # Values are the new priority or a delta ("+0.2" / "-0.1").
    priority_overrides: dict[str, float] = field(default_factory=dict)


# Default profiles per task type.
CONTEXT_PROFILES: dict[TaskType, ContextProfile] = {
    TaskType.CHITCHAT: ContextProfile(
        max_verbatim_turns=3,
        priority_overrides={
            "knowhow": 0.3,
            "skills_summary": 0.3,
            "plan_trigger": 0.0,
        },
    ),
    TaskType.ONE_SHOT: ContextProfile(
        max_verbatim_turns=4,
        priority_overrides={
            "memory": 0.7,  # Ensure long-term memory is included
        },
    ),
    TaskType.FOLLOW_UP: ContextProfile(
        max_verbatim_turns=None,  # Keep all history
        priority_overrides={},  # Use defaults
    ),
    TaskType.CODING: ContextProfile(
        max_verbatim_turns=None,  # Full history for code context
        priority_overrides={
            "active_skills": 0.9,
            "skills_summary": 0.8,
            "knowhow": 0.7,
        },
    ),
    TaskType.RESEARCH: ContextProfile(
        max_verbatim_turns=8,
        priority_overrides={
            "knowhow": 0.9,
            "memory": 0.8,
        },
    ),
}


def get_profile(task_type: TaskType) -> ContextProfile:
    """Return the :class:`ContextProfile` for *task_type*."""
    return CONTEXT_PROFILES.get(task_type, CONTEXT_PROFILES[TaskType.FOLLOW_UP])


# ---------------------------------------------------------------------------
# History optimiser — relevance scoring + progressive compression
# ---------------------------------------------------------------------------


@dataclass
class _Turn:
    """A conversation turn: one user message + its assistant response + tool interactions."""

    messages: list[dict[str, Any]]
    index: int  # Position in the original turn sequence (0 = oldest)


class HistoryOptimizer:
    """Score, compress, and arrange history for optimal LLM context."""

    # Compression thresholds
    HIGH_SCORE = 0.6
    LOW_SCORE = 0.3

    # Compression limits
    TOOL_RESULT_MAX_CHARS = 200
    ASSISTANT_TEXT_MAX_CHARS = 300
    TOOL_CALL_SUMMARY = True

    def optimize(
        self,
        history: list[dict[str, Any]],
        current_query: str,
        task_type: TaskType,
    ) -> list[dict[str, Any]]:
        """Return an optimised copy of *history* for the current query.

        The optimiser:
        1. Groups messages into conversation turns.
        2. Scores each turn by recency + relevance to *current_query*.
        3. Applies progressive compression based on score:
           - High score (>=0.6): verbatim
           - Medium score (0.3-0.6): compressed (tool results truncated, etc.)
           - Low score (<0.3): skeleton (user messages only)
        4. Always keeps the most recent N turns verbatim (N from ContextProfile).
        """
        if not history:
            return []

        profile = get_profile(task_type)
        turns = self._group_into_turns(history)

        if not turns:
            return list(history)

        # Score each turn
        scored_turns: list[tuple[_Turn, float]] = []
        for turn in turns:
            recency = turn.index / max(len(turns) - 1, 1)  # 0.0=oldest, 1.0=newest
            relevance = self._score_relevance(turn, current_query)
            score = 0.6 * recency + 0.4 * relevance
            scored_turns.append((turn, score))

        # Determine how many recent turns to always keep verbatim
        verbatim_count = profile.max_verbatim_turns
        if verbatim_count is None:
            verbatim_count = len(turns)

        result: list[dict[str, Any]] = []
        for i, (turn, score) in enumerate(scored_turns):
            is_recent = i >= len(scored_turns) - verbatim_count

            if is_recent or score >= self.HIGH_SCORE:
                # Verbatim: keep as-is
                result.extend(turn.messages)
            elif score >= self.LOW_SCORE:
                # Compressed: truncate tool results and long content
                result.extend(self._compress_turn(turn))
            else:
                # Skeleton: user messages only (preserves conversation backbone)
                result.extend(self._skeleton_turn(turn))

        return result

    @staticmethod
    def _group_into_turns(history: list[dict[str, Any]]) -> list[_Turn]:
        """Group messages into conversation turns.

        A turn starts with a ``user`` message and includes all subsequent
        non-user messages (assistant, tool) until the next user message.
        """
        turns: list[_Turn] = []
        current_msgs: list[dict[str, Any]] = []
        turn_idx = 0

        for msg in history:
            if msg.get("role") == "user" and current_msgs:
                turns.append(_Turn(messages=current_msgs, index=turn_idx))
                turn_idx += 1
                current_msgs = []
            current_msgs.append(msg)

        if current_msgs:
            turns.append(_Turn(messages=current_msgs, index=turn_idx))

        return turns

    @staticmethod
    def _score_relevance(turn: _Turn, query: str) -> float:
        """Score relevance of a turn to the current query via term overlap.

        Uses Jaccard similarity with CJK bigram support.
        Returns a value in [0.0, 1.0].
        """
        if not query:
            return 0.0

        # Extract text from all messages in the turn
        turn_text = ""
        for msg in turn.messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                turn_text += " " + content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        turn_text += " " + part.get("text", "")

        if not turn_text.strip():
            return 0.0

        query_tokens = _tokenize_for_relevance(query)
        turn_tokens = _tokenize_for_relevance(turn_text[:3000])

        if not query_tokens:
            return 0.0

        overlap = query_tokens & turn_tokens
        union = query_tokens | turn_tokens
        jaccard = len(overlap) / max(len(union), 1)

        # Map to [0.0, 1.0] — jaccard is typically 0.0-0.3, scale up
        return min(1.0, jaccard * 3.0)

    def _compress_turn(self, turn: _Turn) -> list[dict[str, Any]]:
        """Compress a turn: truncate tool results and long assistant content."""
        compressed: list[dict[str, Any]] = []
        for msg in turn.messages:
            role = msg.get("role")
            if role == "user":
                # User messages are never compressed
                compressed.append(msg)
            elif role == "tool":
                compressed.append(self._compress_tool_result(msg))
            elif role == "assistant":
                compressed.append(self._compress_assistant(msg))
            else:
                compressed.append(msg)
        return compressed

    def _compress_tool_result(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Truncate tool result content."""
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > self.TOOL_RESULT_MAX_CHARS:
            result = dict(msg)
            result["content"] = content[: self.TOOL_RESULT_MAX_CHARS] + "\n[... truncated]"
            return result
        return msg

    def _compress_assistant(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Compress assistant message: summarize tool calls, truncate text."""
        tool_calls = msg.get("tool_calls")
        content = msg.get("content", "")

        if tool_calls and self.TOOL_CALL_SUMMARY:
            # Summarize tool calls to just their names
            names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
            result = dict(msg)
            result["tool_calls"] = _summarize_tool_calls(tool_calls)
            if isinstance(content, str) and len(content) > self.ASSISTANT_TEXT_MAX_CHARS:
                result["content"] = (
                    content[: self.ASSISTANT_TEXT_MAX_CHARS] + f"\n[... truncated, called: {', '.join(names)}]"
                )
            return result

        if isinstance(content, str) and len(content) > self.ASSISTANT_TEXT_MAX_CHARS:
            result = dict(msg)
            result["content"] = content[: self.ASSISTANT_TEXT_MAX_CHARS] + "\n[... truncated]"
            return result

        return msg

    @staticmethod
    def _skeleton_turn(turn: _Turn) -> list[dict[str, Any]]:
        """Keep only user messages from a turn (conversation backbone)."""
        skeleton: list[dict[str, Any]] = []
        for msg in turn.messages:
            if msg.get("role") == "user":
                skeleton.append(msg)
            elif msg.get("role") == "assistant":
                # Keep a minimal assistant placeholder to maintain conversation structure
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                    skeleton.append(
                        {"role": "assistant", "content": f"[Used tools: {', '.join(names)}]"}
                    )
                else:
                    content = msg.get("content", "")
                    if isinstance(content, str) and content:
                        # Keep first line as a hint
                        first_line = content.split("\n")[0][:100]
                        skeleton.append({"role": "assistant", "content": f"[{first_line}...]"})
                    else:
                        skeleton.append({"role": "assistant", "content": "[...]"})
        return skeleton


def _summarize_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce tool call arguments to a minimal summary."""
    summarized = []
    for tc in tool_calls:
        func = tc.get("function", {})
        summarized.append(
            {
                "id": tc.get("id", ""),
                "type": "function",
                "function": {
                    "name": func.get("name", ""),
                    "arguments": "{}",  # Strip arguments to save tokens
                },
            }
        )
    return summarized


def _tokenize_for_relevance(text: str) -> set[str]:
    """Tokenize text for relevance scoring (Latin words + CJK bigrams)."""
    words = set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))
    cjk_runs = re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]+", text)
    for run in cjk_runs:
        for i in range(len(run) - 1):
            words.add(run[i : i + 2])
        if run:
            words.add(run)
    return words


# ---------------------------------------------------------------------------
# Token safety net — model-limit awareness
# ---------------------------------------------------------------------------


def get_model_limit(model: str | None) -> int:
    """Return the max input token limit for *model*.

    Tries ``litellm.get_model_info()`` first, falls back to a keyword-based
    static map, and ultimately defaults to 200k.
    """
    if not model:
        return 200_000

    # Try litellm (fast, cached internally)
    try:
        import litellm

        info = litellm.get_model_info(model)
        limit = info.get("max_input_tokens") or info.get("max_tokens")
        if limit and limit > 0:
            return int(limit)
    except Exception:
        pass

    # Fallback: keyword match
    model_lower = model.lower()
    for key, limit in _FALLBACK_MODEL_LIMITS.items():
        if key in model_lower:
            return limit

    return 200_000


def estimate_tokens(content: Any, model: str | None = None) -> int:
    """Estimate the token count of *content*.

    Tries ``litellm.token_counter()`` for accuracy, falls back to
    ``len(text) / 3.5``.
    """
    if model:
        try:
            import litellm

            if isinstance(content, str):
                return litellm.token_counter(model=model, text=content)
            elif isinstance(content, list):
                return litellm.token_counter(model=model, messages=content)
        except Exception:
            pass

    # Fallback: character-based estimation
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = json.dumps(content, ensure_ascii=False)
    elif isinstance(content, dict):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)

    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def safety_trim_messages(
    messages: list[dict[str, Any]],
    model: str | None,
    response_reserve: int = 8192,
) -> list[dict[str, Any]]:
    """Trim messages if they approach the model's context window limit.

    Only triggers when estimated tokens + response_reserve exceed 90% of the
    model's limit.  This is a safety net, not the primary context control.

    Trimming strategy: remove oldest non-system messages first, preserving
    conversation turn alignment.
    """
    model_limit = get_model_limit(model)
    threshold = int(model_limit * 0.90)  # Trigger at 90% of limit

    total = estimate_tokens(messages, model)
    if total + response_reserve <= threshold:
        return messages

    logger.warning(
        "Context approaching model limit ({} + {} > {} * 0.9 = {}), trimming...",
        total,
        response_reserve,
        model_limit,
        threshold,
    )

    # Separate system message from conversation
    system_msgs = [m for m in messages if m.get("role") == "system"]
    conv_msgs = [m for m in messages if m.get("role") != "system"]

    if not conv_msgs:
        return messages

    # Find the current user message (last user message) — always keep it
    last_user_idx = None
    for i in range(len(conv_msgs) - 1, -1, -1):
        if conv_msgs[i].get("role") == "user":
            last_user_idx = i
            break

    # Remove oldest conversation messages until within budget
    target = threshold - response_reserve
    trimmed = list(conv_msgs)

    while estimate_tokens(system_msgs + trimmed, model) > target and len(trimmed) > 1:
        # Don't remove the last user message
        if last_user_idx is not None and len(trimmed) <= (len(conv_msgs) - last_user_idx):
            break
        trimmed.pop(0)

    # Clean up orphaned tool results
    trimmed = _remove_orphaned_tool_results(trimmed)

    logger.info(
        "Trimmed {} messages from history (kept {})",
        len(conv_msgs) - len(trimmed),
        len(trimmed),
    )

    return system_msgs + trimmed


def _remove_orphaned_tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove tool result messages whose corresponding tool_call is not in the list."""
    # Collect all tool_call_ids from assistant messages
    valid_ids: set[str] = set()
    for msg in messages:
        for tc in msg.get("tool_calls", []):
            tc_id = tc.get("id")
            if tc_id:
                valid_ids.add(tc_id)

    return [
        msg
        for msg in messages
        if msg.get("role") != "tool" or msg.get("tool_call_id") in valid_ids
    ]
