"""ReAct reasoning enhancement for the agent loop.

Provides three reasoning intensity levels (none / lite / full) that are
injected into the system prompt.  The classifier picks the level based on
cheap heuristics (no LLM call), and the loop extracts ``<thought>`` blocks
for logging, progress push, and stall detection.
"""

from __future__ import annotations

import re
from enum import Enum

# ---------------------------------------------------------------------------
# Reasoning levels
# ---------------------------------------------------------------------------


class ReasoningLevel(str, Enum):
    NONE = "none"
    LITE = "lite"
    FULL = "full"


# ---------------------------------------------------------------------------
# System-prompt templates
# ---------------------------------------------------------------------------

REACT_LITE = (
    "# Reasoning\nBefore acting, briefly state in <thought> what you're about to do and why.\n"
)

REACT_FULL = """\
# Reasoning Protocol

Before EACH action, output a <thought> block:

<thought>
**Observation**: What I know so far from prior results
**Analysis**: What this means / what's missing
**Plan**: My next step and why this is the right move
**Progress**: Am I closer to the goal? Should I change approach?
</thought>

Rules:
- ALWAYS output <thought> before tool calls
- Evaluate whether previous results already answer the question — if yes, give final answer
- If a tool call failed, analyze WHY before retrying with a different approach
- If you've called 3+ tools without clear progress, reassess your strategy in <thought>
"""

PROMPT_BY_LEVEL = {
    ReasoningLevel.NONE: "",
    ReasoningLevel.LITE: REACT_LITE,
    ReasoningLevel.FULL: REACT_FULL,
}

# ---------------------------------------------------------------------------
# Signal-detection helpers (cheap string ops, no LLM)
# ---------------------------------------------------------------------------

_TASK_KEYWORDS = frozenset(
    {
        "搜索",
        "查找",
        "查询",
        "分析",
        "写",
        "改",
        "修复",
        "创建",
        "部署",
        "调试",
        "对比",
        "总结",
        "整理",
        "研究",
        "检查",
        "优化",
        "实现",
        "设计",
        "测试",
        "search",
        "find",
        "analyze",
        "write",
        "fix",
        "create",
        "deploy",
        "debug",
        "compare",
        "summarize",
        "implement",
        "design",
        "test",
        "check",
        "optimize",
        "research",
        "investigate",
        "review",
        "refactor",
        "build",
        "fetch",
        "read",
    }
)

_MULTI_STEP_WORDS = frozenset(
    {
        "然后",
        "接着",
        "之后",
        "并且",
        "同时",
        "首先",
        "最后",
        "步骤",
        "第一",
        "第二",
        "第三",
        "另外",
        "此外",
        "then",
        "after",
        "also",
        "first",
        "finally",
        "step",
        "and then",
        "next",
        "additionally",
        "moreover",
        "before that",
    }
)

_CONDITIONAL_WORDS = frozenset(
    {
        "如果",
        "否则",
        "对比",
        "比较",
        "假如",
        "万一",
        "要是",
        "除非",
        "if",
        "else",
        "otherwise",
        "compare",
        "versus",
        "vs",
        "whether",
    }
)

_CHITCHAT_RE = re.compile(
    r"^(hi|hello|hey|你好|谢谢|thanks|thank you|ok|okay|好的|嗯|哈哈|"
    r"👍|🙏|早|晚安|good morning|good night|bye|再见|没事了|got it)[\s!！。.\?？]*$",
    re.IGNORECASE,
)


def _has_task_signal(msg: str) -> bool:
    lower = msg.lower()
    return any(k in lower for k in _TASK_KEYWORDS)


def _has_multi_step_signal(msg: str) -> bool:
    lower = msg.lower()
    return any(k in lower for k in _MULTI_STEP_WORDS)


def _has_conditional_logic(msg: str) -> bool:
    lower = msg.lower()
    return any(k in lower for k in _CONDITIONAL_WORDS)


def _has_question_chain(msg: str) -> bool:
    return msg.count("?") + msg.count("？") >= 2


def _is_chitchat(msg: str) -> bool:
    return bool(_CHITCHAT_RE.match(msg.strip()))


def _history_has_tools(history: list[dict], lookback: int = 6) -> bool:
    return any(m.get("role") == "tool" for m in history[-lookback:])


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class ReasoningContext:
    """Lightweight context bag passed into the classifier."""

    __slots__ = ("in_plan_step", "explicit_trigger", "escalated")

    def __init__(
        self,
        *,
        in_plan_step: bool = False,
        explicit_trigger: bool = False,
        escalated: bool = False,
    ):
        self.in_plan_step = in_plan_step
        self.explicit_trigger = explicit_trigger
        self.escalated = escalated


def classify_reasoning_level(
    message: str,
    history: list[dict],
    context: ReasoningContext | None = None,
    default_level: str = "auto",
) -> ReasoningLevel:
    """Determine the reasoning intensity for this turn.

    ``default_level`` mirrors the config value:
      - ``"auto"`` — heuristic classification (default)
      - ``"full"`` / ``"lite"`` / ``"none"`` — force that level
    """
    # Honour explicit config override
    if default_level != "auto":
        try:
            return ReasoningLevel(default_level)
        except ValueError:
            pass  # fall through to auto

    ctx = context or ReasoningContext()

    # ---- Force FULL ----
    if ctx.in_plan_step or ctx.explicit_trigger or ctx.escalated:
        return ReasoningLevel.FULL

    # ---- Force NONE ----
    msg = message.strip()
    if len(msg) < 15 and not _has_task_signal(msg):
        return ReasoningLevel.NONE
    if _is_chitchat(msg):
        return ReasoningLevel.NONE

    # ---- Score-based ----
    score = 0
    if len(msg) > 80:
        score += 1
    if _has_multi_step_signal(msg):
        score += 1
    if _has_task_signal(msg):
        score += 1
    if _has_question_chain(msg):
        score += 1
    if _history_has_tools(history):
        score += 1
    if _has_conditional_logic(msg):
        score += 1

    return ReasoningLevel.FULL if score >= 2 else ReasoningLevel.LITE


# ---------------------------------------------------------------------------
# Thought extraction & stripping
# ---------------------------------------------------------------------------

_THOUGHT_RE = re.compile(r"<thought>(.*?)</thought>", re.DOTALL)


def extract_thought(text: str | None) -> str | None:
    """Return the first ``<thought>`` block content, or *None*."""
    if not text:
        return None
    m = _THOUGHT_RE.search(text)
    return m.group(1).strip() if m else None


def strip_thought(text: str | None) -> str | None:
    """Remove all ``<thought>`` blocks from *text*."""
    if not text:
        return text
    return _THOUGHT_RE.sub("", text).strip() or None


# ---------------------------------------------------------------------------
# Stall detection
# ---------------------------------------------------------------------------


def detect_stall(recent_thoughts: list[str], window: int = 3, threshold: float = 0.6) -> bool:
    """Return *True* if the last *window* thoughts are suspiciously similar.

    Uses Jaccard similarity on word sets — cheap and good enough.
    """
    if len(recent_thoughts) < window:
        return False
    last_n = recent_thoughts[-window:]
    word_sets = [set(t.lower().split()) for t in last_n]
    for i in range(len(word_sets) - 1):
        union = word_sets[i] | word_sets[i + 1]
        if not union:
            continue
        jaccard = len(word_sets[i] & word_sets[i + 1]) / len(union)
        if jaccard < threshold:
            return False
    return True


STALL_NUDGE = (
    "[System] You appear to be repeating similar reasoning. "
    "Reassess your approach: summarize findings so far "
    "and either try a different strategy or give your best answer."
)
