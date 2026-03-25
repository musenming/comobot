"""Push notification delivery service for Comobot Remote devices.

Uses the Expo Push API to send notifications to paired mobile devices.
"""

import logging
from typing import Any

import httpx

from ...db.core import Database

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class PushService:
    """Sends push notifications to paired mobile devices via Expo Push API."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def _get_push_tokens(self, device_ids: list[str] | None = None) -> list[str]:
        """Get push tokens for specified devices, or all active devices."""
        if device_ids:
            placeholders = ",".join("?" for _ in device_ids)
            rows = await self.db.fetch_all(
                f"SELECT push_token FROM remote_devices "
                f"WHERE id IN ({placeholders}) AND push_token IS NOT NULL AND is_active = 1",
                device_ids,
            )
        else:
            rows = await self.db.fetch_all(
                "SELECT push_token FROM remote_devices "
                "WHERE push_token IS NOT NULL AND is_active = 1"
            )
        return [row["push_token"] for row in rows]

    async def _send(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        category: str | None = None,
    ) -> None:
        """Send push notification via Expo Push API."""
        if not tokens:
            return

        messages = [
            {
                "to": token,
                "title": title,
                "body": body,
                "sound": "default",
                **({"data": data} if data else {}),
                **({"categoryId": category} if category else {}),
            }
            for token in tokens
        ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    EXPO_PUSH_URL,
                    json=messages,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Push API returned %d: %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("Failed to send push notification")

    async def notify_intent_complete(
        self,
        device_id: str,
        intent_id: str,
        transcript: str,
        result: str | None = None,
    ) -> None:
        """Notify device that a voice intent has been processed."""
        tokens = await self._get_push_tokens([device_id])
        body = result[:100] if result else "Intent processed successfully"
        await self._send(
            tokens,
            title="Intent Complete",
            body=body,
            data={"type": "intent_complete", "intent_id": intent_id},
            category="intent",
        )

    async def notify_agent_error(
        self,
        agent_id: str,
        error: str,
        device_ids: list[str] | None = None,
    ) -> None:
        """Notify devices about an agent error."""
        tokens = await self._get_push_tokens(device_ids)
        await self._send(
            tokens,
            title="Agent Error",
            body=f"Agent {agent_id}: {error[:100]}",
            data={"type": "agent_error", "agent_id": agent_id},
            category="agent",
        )

    async def notify_intervention_needed(
        self,
        session_key: str,
        draft_preview: str,
        device_ids: list[str] | None = None,
    ) -> None:
        """Notify devices that agent intervention is needed."""
        tokens = await self._get_push_tokens(device_ids)
        await self._send(
            tokens,
            title="Intervention Needed",
            body=draft_preview[:100],
            data={"type": "intervention", "session_key": session_key},
            category="intervention",
        )

    async def notify_new_message(
        self,
        session_key: str,
        preview: str,
        device_ids: list[str] | None = None,
    ) -> None:
        """Notify devices about a new message in a subscribed session."""
        tokens = await self._get_push_tokens(device_ids)
        await self._send(
            tokens,
            title="New Message",
            body=preview[:100],
            data={"type": "new_message", "session_key": session_key},
            category="message",
        )
