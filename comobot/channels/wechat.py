"""WeChat channel via openclaw-bridge (Node.js bridge process).

Architecture mirrors the WhatsApp channel:
  - A separate Node.js process (openclaw-bridge/) speaks the OpenClaw protocol
    to the @tencent-weixin/openclaw-weixin-cli plugin, handles QR code login,
    and maintains the WeChat connection.
  - This Python channel connects to that bridge via WebSocket and exchanges
    simple JSON messages, keeping the OpenClaw protocol entirely inside Node.js.

Message flow:
  WeChat user
    → openclaw-weixin plugin
      → openclaw-bridge (Node.js, port 3002)
        ─[WebSocket]─→  WechatChannel (Python)
                          → MessageBus → AgentLoop
                          ← OutboundMessage
        ←[WebSocket]──  WechatChannel.send()
      ← openclaw-bridge forwards reply
    ← WeChat user receives reply
"""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict

from loguru import logger

from comobot.bus.events import OutboundMessage
from comobot.bus.queue import MessageBus
from comobot.channels.base import BaseChannel
from comobot.config.schema import WechatConfig


class WechatChannel(BaseChannel):
    """
    WeChat channel that connects to the openclaw-bridge Node.js process.

    The bridge handles all OpenClaw protocol details; this class only speaks
    the same simple JSON-over-WebSocket protocol used by WhatsAppChannel.

    Bridge → Python message types:
      {"type": "message", "openid": "...", "chat_id": "...", "content": "...",
       "msg_id": "...", "nickname": "...", "is_group": false, "timestamp": 0}
      {"type": "status",  "status": "connected" | "disconnected" | "qr_shown"}
      {"type": "error",   "error": "..."}

    Python → Bridge message types:
      {"type": "send", "to": "<chat_id>", "text": "..."}
    """

    name = "wechat"

    def __init__(self, config: WechatConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: WechatConfig = config
        self._ws = None
        self._connected = False
        self._processed_ids: OrderedDict[str, None] = OrderedDict()

    async def start(self) -> None:
        """Connect to the openclaw-bridge and listen for WeChat messages."""
        import websockets

        bridge_url = self.config.bridge_url
        logger.info("Connecting to openclaw-bridge at {}...", bridge_url)
        self._running = True

        while self._running:
            try:
                async with websockets.connect(bridge_url) as ws:
                    self._ws = ws

                    if self.config.bridge_token:
                        await ws.send(
                            json.dumps({"type": "auth", "token": self.config.bridge_token})
                        )

                    self._connected = True
                    logger.info("Connected to openclaw-bridge")

                    async for raw in ws:
                        try:
                            await self._handle_bridge_message(raw)
                        except Exception as e:
                            logger.error("Error handling bridge message: {}", e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                self._ws = None
                logger.warning("openclaw-bridge connection error: {}", e)
                if self._running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the WeChat channel."""
        self._running = False
        self._connected = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(self, msg: OutboundMessage) -> None:
        """Send a reply via the bridge back to WeChat."""
        if not self._ws or not self._connected:
            logger.warning("openclaw-bridge not connected, cannot send")
            return
        try:
            payload = {"type": "send", "to": msg.chat_id, "text": msg.content}
            await self._ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.error("Error sending WeChat message via bridge: {}", e)

    async def _handle_bridge_message(self, raw: str) -> None:
        """Dispatch a message received from the bridge."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from openclaw-bridge: {}", raw[:120])
            return

        msg_type = data.get("type")

        if msg_type == "message":
            openid = data.get("openid", "")
            chat_id = data.get("chat_id", openid)
            content = data.get("content", "")
            msg_id = data.get("msg_id", "")

            # Dedup
            if msg_id:
                if msg_id in self._processed_ids:
                    return
                self._processed_ids[msg_id] = None
                while len(self._processed_ids) > 1000:
                    self._processed_ids.popitem(last=False)

            await self._handle_message(
                sender_id=openid,
                chat_id=chat_id,
                content=content,
                metadata={
                    "msg_id": msg_id,
                    "nickname": data.get("nickname", ""),
                    "is_group": data.get("is_group", False),
                    "timestamp": data.get("timestamp"),
                },
            )

        elif msg_type == "status":
            status = data.get("status")
            logger.info("WeChat bridge status: {}", status)
            if status == "connected":
                self._connected = True
            elif status == "disconnected":
                self._connected = False
            elif status == "qr_shown":
                logger.info("Scan the QR code shown in the openclaw-bridge terminal to log in WeChat")

        elif msg_type == "error":
            logger.error("openclaw-bridge error: {}", data.get("error"))
