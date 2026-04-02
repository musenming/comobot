"""Voice intent processing engine for Comobot Remote.

State machine:
  pending → analyzing → pending_confirmation → confirmed → processing → completed
                      → completed (noise)     → cancelled (user/timeout)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta

from loguru import logger

from comobot.db.connection import Database

# --- Noise filter: skip LLM for short/meaningless transcripts ---
MIN_TRANSCRIPT_LENGTH = 4
NOISE_PATTERNS = frozenset(
    {"嗯", "啊", "哦", "等一下", "那个", "好的", "嗯嗯", "OK", "ok", "好", "行", "对"}
)
CONFIRMATION_TIMEOUT_SEC = 120


class IntentEngine:
    """Processes voice transcripts: intent recognition → agent routing → execution."""

    def __init__(self, db: Database):
        self.db = db
        self._processing_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit_intent(
        self, device_id: str, transcript: str, context: dict | None = None
    ) -> dict:
        """Create a voice_intent record. Returns {intent_id, status: 'pending'}."""
        intent_id = uuid.uuid4().hex
        await self.db.execute(
            "INSERT INTO voice_intents (id, device_id, transcript, status) VALUES (?, ?, ?, ?)",
            (intent_id, device_id, transcript, "pending"),
        )
        logger.info(
            "Voice intent submitted: {} (device={}, transcript='{}')",
            intent_id,
            device_id,
            transcript[:50],
        )
        return {"intent_id": intent_id, "status": "pending"}

    async def process_intent(
        self,
        intent_id: str,
        agent_loop=None,
        remote_manager=None,
        *,
        device_id: str | None = None,
    ) -> dict:
        """Multi-stage processing pipeline.

        1. Noise filter — skip LLM for meaningless utterances
        2. LLM demand extraction → demand_summary
        3. Status → pending_confirmation (wait for user)
        """
        row = await self.get_intent(intent_id)
        if not row:
            return {"intent_id": intent_id, "status": "failed", "error": "not found"}

        transcript = row["transcript"]
        device_id = device_id or row["device_id"]

        # --- Stage 1: noise filter ---
        if not self.should_analyze(transcript):
            await self._update_status(intent_id, "completed", intent="noise", confidence=1.0)
            if remote_manager and device_id:
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "intent_update",
                        "intent_id": intent_id,
                        "status": "completed",
                        "intent": "noise",
                        "confidence": 1.0,
                    },
                )
            return {"intent_id": intent_id, "status": "completed", "intent": "noise"}

        # --- Stage 2: analyzing ---
        await self._update_status(intent_id, "analyzing")
        if remote_manager and device_id:
            await remote_manager.send_encrypted(
                device_id,
                {"t": "intent_update", "intent_id": intent_id, "status": "analyzing"},
            )

        # --- Stage 2.5: LLM ASR correction + contextual alignment ---
        corrected = await self._correct_transcript(transcript, device_id, agent_loop)
        if corrected and corrected != transcript:
            logger.info("ASR correction: '{}' → '{}'", transcript[:60], corrected[:60])
            transcript = corrected
            await self.db.execute(
                "UPDATE voice_intents SET transcript = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (transcript, intent_id),
            )

        # --- Stage 3: LLM demand extraction → pending_confirmation ---
        try:
            classification = await self._extract_demand(transcript, agent_loop)
            demand_summary = classification.get("demand_summary", transcript)
            intent = classification.get("intent", "general_query")
            confidence = classification.get("confidence", 0.5)

            # Cancel this device's previous pending_confirmation (at most 1 active)
            await self._cancel_stale_confirmations(device_id, exclude=intent_id)

            await self.db.execute(
                "UPDATE voice_intents SET status = 'pending_confirmation', "
                "demand_summary = ?, intent = ?, confidence = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (demand_summary, intent, confidence, intent_id),
            )

            payload = {
                "t": "intent_update",
                "intent_id": intent_id,
                "status": "pending_confirmation",
                "intent": intent,
                "confidence": confidence,
                "demand_summary": demand_summary,
            }
            if remote_manager and device_id:
                await remote_manager.send_encrypted(device_id, payload)

            return {
                "intent_id": intent_id,
                "status": "pending_confirmation",
                "intent": intent,
                "confidence": confidence,
                "demand_summary": demand_summary,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error("Intent analysis failed for {}: {}", intent_id, error_msg)
            await self._update_status(intent_id, "failed", error=error_msg)
            if remote_manager and device_id:
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "intent_update",
                        "intent_id": intent_id,
                        "status": "failed",
                        "error": error_msg,
                    },
                )
            return {"intent_id": intent_id, "status": "failed", "error": error_msg}

    async def process_intent_with_demand(
        self,
        intent_id: str,
        *,
        demand_summary: str,
        intent_type: str,
        confidence: float,
        remote_manager=None,
        device_id: str | None = None,
    ) -> dict:
        """Fast-track: demand already captured during real-time streaming.

        Skips noise filter and LLM extraction — goes straight to pending_confirmation.
        """
        row = await self.get_intent(intent_id)
        if not row:
            return {"intent_id": intent_id, "status": "failed", "error": "not found"}

        device_id = device_id or row["device_id"]

        # Cancel previous pending_confirmation for this device
        await self._cancel_stale_confirmations(device_id, exclude=intent_id)

        await self.db.execute(
            "UPDATE voice_intents SET status = 'pending_confirmation', "
            "demand_summary = ?, intent = ?, confidence = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (demand_summary, intent_type, confidence, intent_id),
        )

        payload = {
            "t": "intent_update",
            "intent_id": intent_id,
            "status": "pending_confirmation",
            "intent": intent_type,
            "confidence": confidence,
            "demand_summary": demand_summary,
        }
        if remote_manager and device_id:
            await remote_manager.send_encrypted(device_id, payload)

        logger.info(
            "Intent {} fast-tracked to pending_confirmation: '{}' (conf={:.2f})",
            intent_id,
            demand_summary[:60],
            confidence,
        )
        return {
            "intent_id": intent_id,
            "status": "pending_confirmation",
            "intent": intent_type,
            "confidence": confidence,
            "demand_summary": demand_summary,
        }

    async def confirm_intent(self, intent_id: str) -> dict | None:
        """User confirms execution.  pending_confirmation → confirmed."""
        row = await self.db.fetchone(
            "SELECT * FROM voice_intents WHERE id = ? AND status = 'pending_confirmation'",
            (intent_id,),
        )
        if not row:
            return None

        await self.db.execute(
            "UPDATE voice_intents SET status = 'confirmed', "
            "confirmed_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
            (intent_id,),
        )
        return {**dict(row), "status": "confirmed"}

    async def cancel_pending_intent(self, intent_id: str) -> bool:
        """Cancel a pending_confirmation intent."""
        cursor = await self.db.execute(
            "UPDATE voice_intents SET status = 'cancelled', updated_at = datetime('now') "
            "WHERE id = ? AND status = 'pending_confirmation'",
            (intent_id,),
        )
        return cursor.rowcount > 0

    async def cancel_intent(self, intent_id: str) -> bool:
        """Cancel a pending/processing intent."""
        cursor = await self.db.execute(
            "UPDATE voice_intents SET status = 'cancelled', updated_at = datetime('now') "
            "WHERE id = ? AND status IN ('pending', 'processing', 'pending_confirmation')",
            (intent_id,),
        )
        if cursor.rowcount > 0:
            task = self._processing_tasks.pop(intent_id, None)
            if task:
                task.cancel()
            logger.info("Intent cancelled: {}", intent_id)
            return True
        return False

    async def expire_device_intents(self, device_id: str, remote_manager=None) -> int:
        """Expire stale pending_confirmation intents for a single device.

        Called from the per-device heartbeat loop every ~30 s.
        """
        cutoff = (datetime.utcnow() - timedelta(seconds=CONFIRMATION_TIMEOUT_SEC)).isoformat()
        expired = await self.db.fetchall(
            "SELECT id FROM voice_intents "
            "WHERE device_id = ? AND status = 'pending_confirmation' AND updated_at < ?",
            (device_id, cutoff),
        )
        if not expired:
            return 0

        for row in expired:
            await self.db.execute(
                "UPDATE voice_intents SET status = 'cancelled', updated_at = datetime('now') "
                "WHERE id = ?",
                (row["id"],),
            )
            if remote_manager:
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "intent_update",
                        "intent_id": row["id"],
                        "status": "cancelled",
                        "error": "confirmation_timeout",
                    },
                )

        logger.info("Expired {} stale intents for device {}", len(expired), device_id[:12])
        return len(expired)

    # ------------------------------------------------------------------
    # Read helpers (unchanged)
    # ------------------------------------------------------------------

    async def get_intent(self, intent_id: str) -> dict | None:
        """Get a single intent record."""
        return await self.db.fetchone("SELECT * FROM voice_intents WHERE id = ?", (intent_id,))

    async def list_intents(self, device_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """List intents for a device, newest first."""
        return await self.db.fetchall(
            "SELECT * FROM voice_intents WHERE device_id = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (device_id, limit, offset),
        )

    async def delete_intent(self, intent_id: str) -> bool:
        """Delete an intent record."""
        cursor = await self.db.execute("DELETE FROM voice_intents WHERE id = ?", (intent_id,))
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def should_analyze(transcript: str) -> bool:
        """Return False for noise/short utterances that should skip LLM."""
        cleaned = transcript.strip()
        return len(cleaned) >= MIN_TRANSCRIPT_LENGTH and cleaned not in NOISE_PATTERNS

    async def _update_status(self, intent_id: str, status: str, **extra_fields) -> None:
        """Update intent status and arbitrary extra columns."""
        sets = ["status = ?", "updated_at = datetime('now')"]
        params: list = [status]
        for k, v in extra_fields.items():
            sets.append(f"{k} = ?")
            params.append(v if not isinstance(v, dict) else json.dumps(v, ensure_ascii=False))
        params.append(intent_id)
        await self.db.execute(
            f"UPDATE voice_intents SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )

    async def _cancel_stale_confirmations(self, device_id: str, *, exclude: str = "") -> None:
        """Cancel all pending_confirmation intents for a device (except *exclude*)."""
        await self.db.execute(
            "UPDATE voice_intents SET status = 'cancelled', updated_at = datetime('now') "
            "WHERE device_id = ? AND status = 'pending_confirmation' AND id != ?",
            (device_id, exclude),
        )

    # --- ASR correction prompt (system + few-shot) ---

    _CORRECT_SYSTEM_PROMPT = """\
你是一个语音识别(ASR)纠错专家。你的输入是阿里云NLS实时转录的原始文本，可能包含：
- 同音字/近音字错误（最常见）
- 中英混合时英文单词被听成中文
- 专有名词、公司名、人名识别错误
- 口语化的语气词、重复、不完整的句子
- 标点符号错误或缺失

纠错规则：
1. 修正同音字、近音字错误，使语义通顺
2. 如果上下文提到了相关领域术语，优先用领域术语替换听起来相似的错误词
3. 英文单词被错误转成中文时，还原为英文（如"艾皮艾" → "API"）
4. 保留用户原意和说话风格，不要润色或改写
5. 如果文本已经正确，原样返回
6. 只返回纠错后的文本，不要添加任何解释或引号"""

    _CORRECT_FEW_SHOTS = [
        {"role": "user", "content": '转录: "我想调研一下无为智能科技这家公司的背景"'},
        {"role": "assistant", "content": "我想调研一下无为智能科技这家公司的背景"},
        {"role": "user", "content": '转录: "帮我把这个短测模型部署到线上"'},
        {"role": "assistant", "content": "帮我把这个端侧模型部署到线上"},
        {"role": "user", "content": '转录: "用赛扣的艾皮艾查一下今天的天气"'},
        {"role": "assistant", "content": "用psycho的API查一下今天的天气"},
        {"role": "user", "content": '转录: "我明天要去北京开个会一然后安排一下行程"'},
        {"role": "assistant", "content": "我明天要去北京开个会，然后安排一下行程"},
        {"role": "user", "content": '转录: "帮我生成一份关于大模型在教育领域应用的报告"'},
        {"role": "assistant", "content": "帮我生成一份关于大模型在教育领域应用的报告"},
    ]

    async def _correct_transcript(self, transcript: str, device_id: str, agent_loop) -> str | None:
        """LLM-based ASR correction with contextual alignment.

        Uses recent intent history for context so the LLM can infer domain-specific
        terms (e.g. "短测模型" → "端侧模型" when discussing tech architecture).
        Returns corrected text, or None if LLM unavailable.
        """
        provider = getattr(agent_loop, "provider", None) if agent_loop else None
        if not provider:
            return None

        # Gather recent context from this device's intent history
        context_block = ""
        try:
            recent = await self.db.fetchall(
                "SELECT transcript, demand_summary FROM voice_intents "
                "WHERE device_id = ? AND status NOT IN ('pending', 'cancelled') "
                "ORDER BY created_at DESC LIMIT 5",
                (device_id,),
            )
            if recent:
                summaries = [
                    r["demand_summary"] or r["transcript"]
                    for r in reversed(recent)
                    if r["transcript"]
                ]
                if summaries:
                    context_block = (
                        "用户近期上下文（可用于推断领域术语）:\n"
                        + "\n".join(f"- {s[:80]}" for s in summaries)
                        + "\n\n"
                    )
        except Exception:
            pass  # context is optional, don't fail

        messages: list[dict] = [
            {"role": "system", "content": self._CORRECT_SYSTEM_PROMPT},
            *self._CORRECT_FEW_SHOTS,
            {
                "role": "user",
                "content": f'{context_block}转录: "{transcript}"',
            },
        ]

        try:
            response = await provider.chat(messages=messages, model=None)
            corrected = (response.content or "").strip().strip('"').strip("'")
            # Sanity check: correction shouldn't be wildly different in length
            if corrected and 0.3 < len(corrected) / max(len(transcript), 1) < 2.5:
                return corrected
            return transcript
        except Exception as e:
            logger.warning("LLM ASR correction failed: {}", e)
            return None

    async def _extract_demand(self, transcript: str, agent_loop) -> dict:
        """LLM demand extraction → {demand_summary, intent, confidence, entities, agent_id}."""
        provider = getattr(agent_loop, "provider", None) if agent_loop else None
        if not provider:
            result = self._classify_simple(transcript)
            result["demand_summary"] = transcript
            return result

        prompt = (
            "分析以下语音转录文本，提取用户的需求。文本已经过ASR纠错处理。\n"
            "返回 JSON 对象（不要包含 markdown 代码块标记），包含以下字段：\n"
            '- "demand_summary": 用一句话概括用户想做什么（中文）\n'
            '- "intent": 意图分类（如 generate_report, schedule_event, '
            "search_data, translate, general_query）\n"
            '- "confidence": 置信度 0-1\n'
            '- "entities": 相关实体（名称、日期等）\n'
            '- "agent_id": 建议处理的 agent（或 null）\n\n'
            f'转录文本: "{transcript}"'
        )

        try:
            response = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=None,
            )
            content = response.content or ""
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except Exception as e:
            logger.warning("LLM demand extraction failed: {}", e)

        result = self._classify_simple(transcript)
        result["demand_summary"] = transcript
        return result

    @staticmethod
    def _classify_simple(transcript: str) -> dict:
        """Simple keyword-based intent classification fallback."""
        transcript_lower = transcript.lower()

        if any(w in transcript_lower for w in ["调研", "报告", "分析", "研究"]):
            return {
                "intent": "generate_report",
                "confidence": 0.7,
                "entities": {"topic": transcript},
                "agent_id": None,
            }
        elif any(w in transcript_lower for w in ["日程", "会议", "提醒", "安排"]):
            return {
                "intent": "schedule_event",
                "confidence": 0.7,
                "entities": {"event": transcript},
                "agent_id": None,
            }
        elif any(w in transcript_lower for w in ["查", "搜索", "找", "股价", "数据"]):
            return {
                "intent": "search_data",
                "confidence": 0.6,
                "entities": {"query": transcript},
                "agent_id": None,
            }
        elif any(w in transcript_lower for w in ["翻译", "translate"]):
            return {
                "intent": "translate",
                "confidence": 0.8,
                "entities": {"text": transcript},
                "agent_id": None,
            }
        else:
            return {
                "intent": "general_query",
                "confidence": 0.5,
                "entities": {"text": transcript},
                "agent_id": None,
            }
