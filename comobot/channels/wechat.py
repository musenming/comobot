"""WeChat channel via OpenClaw WeChat plugin (@tencent-weixin/openclaw-weixin-cli)."""

from __future__ import annotations

import asyncio

import httpx
from loguru import logger

from comobot.bus.events import OutboundMessage
from comobot.bus.queue import MessageBus
from comobot.channels.base import BaseChannel
from comobot.config.schema import WechatConfig


class WechatChannel(BaseChannel):
    """
    WeChat channel that integrates with the OpenClaw WeChat plugin.

    Message flow:
      Inbound:  openclaw-weixin plugin  --(POST /webhook/wechat)--> WechatChannel._handle_message()
      Outbound: WechatChannel.send()  --(POST http://localhost:<plugin_port>/send)--> plugin -> WeChat

    The plugin auto-discovers comobot via GET /.well-known/openclaw and then
    forwards WeChat messages to the /webhook/wechat endpoint.
    """

    name = "wechat"

    def __init__(self, config: WechatConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: WechatConfig = config
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Start the WeChat channel (webhook-driven, no persistent connection needed)."""
        self._running = True
        self._http = httpx.AsyncClient(timeout=10.0)
        plugin_url = f"http://localhost:{self.config.plugin_port}"
        logger.info("WeChat channel started. Plugin outbound URL: {}", plugin_url)
        logger.info(
            "Waiting for openclaw-weixin plugin to connect via POST /webhook/wechat ..."
        )

        # Keep alive so the channel task stays running alongside the gateway
        while self._running:
            await asyncio.sleep(30)

    async def stop(self) -> None:
        """Stop the WeChat channel."""
        self._running = False
        if self._http:
            await self._http.aclose()
            self._http = None
        logger.info("WeChat channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """Send a reply back to the openclaw-weixin plugin, which delivers it to WeChat."""
        if not self._http:
            logger.warning("WeChat channel not started, cannot send")
            return

        plugin_send_url = f"http://localhost:{self.config.plugin_port}/send"
        payload: dict = {"to": msg.chat_id, "content": msg.content}
        if msg.reply_to:
            payload["reply_to"] = msg.reply_to

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.config.token:
            headers["X-Openclaw-Token"] = self.config.token

        try:
            resp = await self._http.post(plugin_send_url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "WeChat plugin returned HTTP {} for send request", resp.status_code
                )
        except httpx.RequestError as e:
            logger.error("Failed to reach openclaw-weixin plugin at {}: {}", plugin_send_url, e)

    async def handle_webhook(self, data: dict) -> None:
        """
        Process an inbound message posted by the openclaw-weixin plugin.

        Expected payload keys (from plugin):
          - openid  : WeChat user openid (used as sender_id)
          - chat_id : conversation id (group id or openid for 1-on-1)
          - content : message text
          - msg_id  : (optional) deduplicated message id
          - nickname: (optional) display name
        """
        openid = data.get("openid", "")
        chat_id = data.get("chat_id", openid)
        content = data.get("content", "")
        msg_id = data.get("msg_id", "")

        if not openid or not content:
            logger.warning("WeChat webhook: missing openid or content in payload")
            return

        logger.debug("WeChat inbound from openid={} chat_id={}", openid, chat_id)

        await self._handle_message(
            sender_id=openid,
            chat_id=chat_id,
            content=content,
            metadata={
                "msg_id": msg_id,
                "nickname": data.get("nickname", ""),
                "is_group": data.get("is_group", False),
                "source": "openclaw-weixin",
            },
        )
