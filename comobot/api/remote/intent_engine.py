"""Voice intent processing engine for Comobot Remote."""

from __future__ import annotations

import asyncio
import json
import uuid

from loguru import logger

from comobot.db.connection import Database


class IntentEngine:
    """Processes voice transcripts: intent recognition → agent routing → execution."""

    def __init__(self, db: Database):
        self.db = db
        self._processing_tasks: dict[str, asyncio.Task] = {}

    async def submit_intent(
        self, device_id: str, transcript: str, context: dict | None = None
    ) -> dict:
        """Create a voice_intent record and start async processing.

        Returns: {intent_id, status: 'pending'}
        """
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
    ) -> dict:
        """Process an intent through the agent pipeline.

        1. Use LLM to classify intent and extract entities
        2. Route to appropriate agent/session
        3. Update voice_intents record with result
        4. Notify the device via remote_manager if available
        """
        intent = await self.get_intent(intent_id)
        if not intent:
            return {"error": "Intent not found"}

        await self.db.execute(
            "UPDATE voice_intents SET status = 'processing', updated_at = datetime('now') "
            "WHERE id = ?",
            (intent_id,),
        )

        try:
            # If we have an agent loop, use it for intent classification
            if agent_loop:
                result = await self._classify_with_agent(
                    intent["transcript"], agent_loop
                )
            else:
                # Fallback: simple keyword-based classification
                result = self._classify_simple(intent["transcript"])

            await self.db.execute(
                "UPDATE voice_intents SET "
                "intent = ?, confidence = ?, agent_id = ?, status = 'completed', "
                "result = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (
                    result.get("intent", ""),
                    result.get("confidence", 0),
                    result.get("agent_id"),
                    json.dumps(result, ensure_ascii=False),
                    intent_id,
                ),
            )

            logger.info(
                "Intent processed: {} -> {} (confidence={})",
                intent_id,
                result.get("intent"),
                result.get("confidence"),
            )

            # Notify device
            if remote_manager and intent.get("device_id"):
                await remote_manager.send_encrypted(intent["device_id"], {
                    "t": "intent_update",
                    "intent_id": intent_id,
                    "status": "completed",
                    **result,
                })

            return {"intent_id": intent_id, "status": "completed", **result}

        except Exception as e:
            error_msg = str(e)
            await self.db.execute(
                "UPDATE voice_intents SET status = 'failed', error = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (error_msg, intent_id),
            )
            logger.error("Intent processing failed: {} - {}", intent_id, error_msg)

            if remote_manager and intent.get("device_id"):
                await remote_manager.send_encrypted(intent["device_id"], {
                    "t": "intent_update",
                    "intent_id": intent_id,
                    "status": "failed",
                    "error": error_msg,
                })

            return {"intent_id": intent_id, "status": "failed", "error": error_msg}

    async def _classify_with_agent(self, transcript: str, agent_loop) -> dict:
        """Use the agent's LLM to classify an intent.

        This creates a temporary session for intent classification.
        """
        # Use the agent's provider to classify
        provider = getattr(agent_loop, "provider", None)
        if not provider:
            return self._classify_simple(transcript)

        prompt = (
            "Analyze the following voice transcript and extract the user's intent.\n"
            "Return a JSON object with:\n"
            '- "intent": a short description of what the user wants\n'
            '- "confidence": a number between 0 and 1\n'
            '- "entities": any relevant entities (names, dates, etc.)\n'
            '- "agent_id": suggested agent to handle this (or null)\n\n'
            f'Transcript: "{transcript}"'
        )

        try:
            response = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=None,  # Use default model
            )
            content = response.get("content", "")
            # Try to parse JSON from response
            import json as _json

            # Find JSON in response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return _json.loads(content[start:end])
        except Exception as e:
            logger.warning("LLM intent classification failed: {}", e)

        return self._classify_simple(transcript)

    @staticmethod
    def _classify_simple(transcript: str) -> dict:
        """Simple keyword-based intent classification fallback."""
        transcript_lower = transcript.lower()

        # Simple heuristic classification
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

    async def get_intent(self, intent_id: str) -> dict | None:
        """Get a single intent record."""
        return await self.db.fetchone(
            "SELECT * FROM voice_intents WHERE id = ?", (intent_id,)
        )

    async def list_intents(
        self, device_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """List intents for a device, newest first."""
        return await self.db.fetchall(
            "SELECT * FROM voice_intents WHERE device_id = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (device_id, limit, offset),
        )

    async def cancel_intent(self, intent_id: str) -> bool:
        """Cancel a pending/processing intent."""
        cursor = await self.db.execute(
            "UPDATE voice_intents SET status = 'cancelled', updated_at = datetime('now') "
            "WHERE id = ? AND status IN ('pending', 'processing')",
            (intent_id,),
        )
        if cursor.rowcount > 0:
            # Cancel the async task if running
            task = self._processing_tasks.pop(intent_id, None)
            if task:
                task.cancel()
            logger.info("Intent cancelled: {}", intent_id)
            return True
        return False

    async def delete_intent(self, intent_id: str) -> bool:
        """Delete an intent record."""
        cursor = await self.db.execute(
            "DELETE FROM voice_intents WHERE id = ?", (intent_id,)
        )
        return cursor.rowcount > 0
