"""Real-time demand capture from streaming ASR transcripts.

This module is intentionally isolated so the prompt and trigger logic
can be iterated independently of the ASR pipeline and intent engine.

Architecture:
  ASR sentence_end → DemandCaptureSession.on_sentence(text, is_final)
                   → accumulates confirmed sentences
                   → when threshold met → async LLM analysis
                   → if demand found → push `demand_detected` to frontend
                   → on stream end → final analysis with full transcript
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

from loguru import logger

# ---------------------------------------------------------------------------
# Trigger thresholds (Strategy B: accumulate before calling LLM)
# ---------------------------------------------------------------------------
MIN_SENTENCES_FOR_ANALYSIS = 2  # At least N confirmed sentences before first LLM call
MIN_CHARS_FOR_ANALYSIS = 15  # OR at least N chars of confirmed text
ANALYSIS_COOLDOWN_SEC = 3.0  # Don't re-analyze more often than this
MIN_NEW_CHARS_FOR_REANALYSIS = 10  # Need at least N new chars since last analysis


# ---------------------------------------------------------------------------
# Prompt templates — edit these to iterate on demand capture quality
# ---------------------------------------------------------------------------

DEMAND_CAPTURE_SYSTEM_PROMPT = """\
你是一个实时需求捕获助手。你的任务是从用户的实时语音转录中识别是否包含可执行的需求。

重要：文本来自实时 ASR（语音转文字），质量可能很差，包括：
- 同音字/近音字错误（如"短测" = "端侧"，"艾皮艾" = "API"）
- 缺字、多字、断句错误
- 口语化表达、语气词、重复

你的判断策略：
1. 不要因为文字有错就否定需求。即使文本残缺，只要能推断出用户想让AI做某件事，就算有需求
2. 区分"闲聊/感叹/自言自语"和"希望AI执行的任务"
3. 需求举例：调研公司、生成报告、翻译内容、查数据、安排日程、发送消息、搜索信息
4. 非需求举例：纯感叹（"哇好厉害"）、打招呼（"你好"）、自言自语（"嗯让我想想"）
5. 如果不确定，倾向于判定有需求（宁可多捕获，用户可以dismiss）

返回 JSON（不要包含 markdown 代码块标记）：
{
  "has_demand": true/false,
  "demand_summary": "用一句话描述用户的需求，修正ASR错误后的clean版本（仅当 has_demand=true 时）",
  "confidence": 0.0-1.0,
  "intent": "意图分类: generate_report/schedule_event/search_data/translate/send_message/general_query",
  "reasoning": "简要说明判断依据（用于调试）"
}\
"""

DEMAND_CAPTURE_USER_TEMPLATE = """\
{context_block}当前转录文本（实时，用户可能还在说话）:
"{transcript}"
"""


# ---------------------------------------------------------------------------
# Session: one per ASR stream, tracks sentences and triggers analysis
# ---------------------------------------------------------------------------


@dataclass
class DemandCaptureResult:
    """Result of a demand analysis."""

    has_demand: bool
    demand_summary: str
    confidence: float
    intent: str
    reasoning: str = ""


@dataclass
class DemandCaptureSession:
    """Tracks accumulated transcript for one voice stream and triggers LLM analysis.

    Usage:
        session = DemandCaptureSession(device_id, provider, on_demand)
        # Called from ASR intermediate callback:
        session.on_sentence("你好", is_final=False)   # partial — ignored
        session.on_sentence("我明天要去调研无为智能科技", is_final=True)  # accumulated
        session.on_sentence("帮我准备一份报告", is_final=True)  # triggers analysis
        # Called when ASR stream ends:
        await session.finalize()
    """

    device_id: str
    _provider: object | None = None  # LLM provider (has .chat() method)
    _on_demand: object | None = None  # async callback(DemandCaptureResult)
    _context_lines: str = ""  # recent intent context for alignment

    # Internal state
    _confirmed_sentences: list[str] = field(default_factory=list)
    _confirmed_text: str = ""
    _partial_text: str = ""
    _sentence_count: int = 0
    _last_analysis_at: float = 0.0
    _last_analysis_text_len: int = 0
    _analysis_task: asyncio.Task | None = field(default=None, repr=False)
    _latest_result: DemandCaptureResult | None = None
    _analysis_count: int = 0

    def on_sentence(self, text: str, is_final: bool) -> None:
        """Called from ASR callback. Accumulates confirmed sentences and triggers analysis."""
        if not is_final:
            self._partial_text = text
            return

        # is_final=True means a sentence has been confirmed by ASR
        # The `text` from Ali NLS is the *full accumulated text* (all sentences so far)
        self._confirmed_text = text
        self._sentence_count += 1

        logger.debug(
            "[DemandCapture] device={} sentence #{}: '{}'",
            self.device_id[:12],
            self._sentence_count,
            text[:80],
        )

        # Check if we should trigger analysis
        if self._should_analyze():
            self._trigger_analysis()

    def _should_analyze(self) -> bool:
        """Determine if accumulated text warrants LLM analysis (Strategy B)."""
        text_len = len(self._confirmed_text)

        # Must have enough content
        has_enough = (
            self._sentence_count >= MIN_SENTENCES_FOR_ANALYSIS or text_len >= MIN_CHARS_FOR_ANALYSIS
        )
        if not has_enough:
            return False

        # Cooldown: don't call LLM too frequently
        now = time.monotonic()
        if now - self._last_analysis_at < ANALYSIS_COOLDOWN_SEC:
            return False

        # Must have meaningful new content since last analysis
        new_chars = text_len - self._last_analysis_text_len
        if self._analysis_count > 0 and new_chars < MIN_NEW_CHARS_FOR_REANALYSIS:
            return False

        return True

    def _trigger_analysis(self) -> None:
        """Launch async LLM demand analysis (non-blocking)."""
        # Cancel previous analysis if still running
        if self._analysis_task and not self._analysis_task.done():
            self._analysis_task.cancel()

        text = self._confirmed_text
        self._last_analysis_at = time.monotonic()
        self._last_analysis_text_len = len(text)
        self._analysis_count += 1

        logger.info(
            "[DemandCapture] device={} triggering analysis #{} on '{}'",
            self.device_id[:12],
            self._analysis_count,
            text[:60],
        )

        self._analysis_task = asyncio.create_task(self._analyze(text))

    async def _analyze(self, transcript: str) -> None:
        """Run LLM demand analysis and invoke callback if demand found."""
        if not self._provider:
            return

        try:
            result = await _call_llm(self._provider, transcript, self._context_lines)
            self._latest_result = result

            if result.has_demand and result.confidence >= 0.6:
                logger.info(
                    "[DemandCapture] device={} DEMAND DETECTED: '{}' (conf={:.2f}, intent={})",
                    self.device_id[:12],
                    result.demand_summary[:60],
                    result.confidence,
                    result.intent,
                )
                if self._on_demand and callable(self._on_demand):
                    await self._on_demand(result)
            else:
                logger.debug(
                    "[DemandCapture] device={} no demand (has_demand={}, conf={:.2f})",
                    self.device_id[:12],
                    result.has_demand,
                    result.confidence,
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("[DemandCapture] device={} analysis failed: {}", self.device_id[:12], e)

    async def finalize(self) -> DemandCaptureResult | None:
        """Called when ASR stream ends. Does a final analysis if needed.

        Returns the latest result (may be from a mid-stream analysis or this final one).
        """
        # Wait for any in-flight analysis
        if self._analysis_task and not self._analysis_task.done():
            try:
                await asyncio.wait_for(self._analysis_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        # If we haven't analyzed yet, or have significant new text, do final analysis
        text = self._confirmed_text or self._partial_text
        if not text:
            return self._latest_result

        new_chars = len(text) - self._last_analysis_text_len
        if self._analysis_count == 0 or new_chars >= MIN_NEW_CHARS_FOR_REANALYSIS:
            if self._provider and len(text) >= MIN_CHARS_FOR_ANALYSIS:
                logger.info(
                    "[DemandCapture] device={} final analysis on '{}'",
                    self.device_id[:12],
                    text[:60],
                )
                try:
                    result = await _call_llm(self._provider, text, self._context_lines)
                    self._latest_result = result
                    if result.has_demand and result.confidence >= 0.6 and self._on_demand:
                        await self._on_demand(result)
                except Exception as e:
                    logger.warning(
                        "[DemandCapture] device={} final analysis failed: {}",
                        self.device_id[:12],
                        e,
                    )

        return self._latest_result


# ---------------------------------------------------------------------------
# LLM call helper
# ---------------------------------------------------------------------------


async def _call_llm(provider, transcript: str, context_lines: str = "") -> DemandCaptureResult:
    """Call LLM with demand capture prompt and parse structured result."""
    context_block = ""
    if context_lines:
        context_block = f"用户近期上下文:\n{context_lines}\n\n"

    user_msg = DEMAND_CAPTURE_USER_TEMPLATE.format(
        context_block=context_block,
        transcript=transcript,
    )

    response = await provider.chat(
        messages=[
            {"role": "system", "content": DEMAND_CAPTURE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        model=None,
    )

    content = response.content or ""
    start = content.find("{")
    end = content.rfind("}") + 1

    if start >= 0 and end > start:
        data = json.loads(content[start:end])
        return DemandCaptureResult(
            has_demand=bool(data.get("has_demand", False)),
            demand_summary=data.get("demand_summary", ""),
            confidence=float(data.get("confidence", 0.0)),
            intent=data.get("intent", "general_query"),
            reasoning=data.get("reasoning", ""),
        )

    # Fallback if LLM doesn't return valid JSON
    return DemandCaptureResult(
        has_demand=False,
        demand_summary="",
        confidence=0.0,
        intent="general_query",
        reasoning=f"Failed to parse LLM response: {content[:100]}",
    )


# ---------------------------------------------------------------------------
# Context helper: build context string from recent intents
# ---------------------------------------------------------------------------


async def build_context_lines(db, device_id: str, limit: int = 5) -> str:
    """Build context lines from recent intent history for this device."""
    try:
        recent = await db.fetchall(
            "SELECT transcript, demand_summary FROM voice_intents "
            "WHERE device_id = ? AND status NOT IN ('pending', 'cancelled') "
            "ORDER BY created_at DESC LIMIT ?",
            (device_id, limit),
        )
        if recent:
            lines = [
                f"- {r['demand_summary'] or r['transcript']}"[:80]
                for r in reversed(recent)
                if r["transcript"]
            ]
            if lines:
                return "\n".join(lines)
    except Exception:
        pass
    return ""
