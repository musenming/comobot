"""WeChat channel implementation via Tencent iLink API (pure Python, httpx)."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from comobot.bus.events import OutboundMessage
from comobot.bus.queue import MessageBus
from comobot.channels.base import BaseChannel
from comobot.config.schema import WechatConfig

_AUTH_DIR = Path.home() / ".comobot" / "wechat-auth"
_CRED_FILE = _AUTH_DIR / "credentials.json"
_SYNC_BUF_FILE = _AUTH_DIR / "sync_buf.txt"

_CHANNEL_VERSION = "1.0.2"
_MAX_CONTEXT_CACHE = 1000
_POLL_TIMEOUT = 35
_SESSION_EXPIRED_CODE = -14
_SESSION_EXPIRED_SLEEP = 3600  # 1 hour
_FAILURE_BACKOFF_THRESHOLD = 3
_FAILURE_BACKOFF_SLEEP = 30
_RECONNECT_SLEEP = 5


class WechatChannel(BaseChannel):
    """WeChat channel using Tencent iLink HTTP API."""

    name = "wechat"

    def __init__(self, config: WechatConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: WechatConfig = config
        self._http: httpx.AsyncClient | None = None
        self._token: str = ""
        self._base_url: str = config.base_url
        self._bot_id: str = ""
        self._uin: str = ""
        self._sync_buf: str = ""
        self._context_tokens: OrderedDict[str, str] = OrderedDict()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not self._load_credentials():
            logger.warning("wechat: no credentials found — run 'comobot channels login wechat'")
            return

        self._uin = base64.b64encode(str(random.randint(0, 2**32 - 1)).encode()).decode()
        self._running = True
        logger.info("wechat: starting channel (bot={})", self._bot_id)

        while self._running:
            try:
                self._http = httpx.AsyncClient(
                    timeout=httpx.Timeout(60, read=45),
                    trust_env=False,
                )
                await self._poll_loop()
            except Exception:
                logger.exception("wechat: poll loop error, reconnecting in {}s", _RECONNECT_SLEEP)
            finally:
                if self._http:
                    await self._http.aclose()
                    self._http = None
            if self._running:
                await asyncio.sleep(_RECONNECT_SLEEP)

    async def stop(self) -> None:
        self._running = False
        self._save_sync_buf()
        if self._http:
            await self._http.aclose()
            self._http = None
        logger.info("wechat: channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        logger.debug("wechat: send() called for chat_id={}", msg.chat_id)
        if not self._http:
            logger.warning("wechat: cannot send — client not connected")
            return

        chat_id = msg.chat_id
        context_token = self._context_tokens.get(chat_id, "")
        if not context_token:
            logger.warning("wechat: no context_token for chat_id={}, cannot send", chat_id)
            return

        client_id = f"comobot-{int(time.time() * 1000)}-{os.urandom(4).hex()}"
        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": chat_id,
                "client_id": client_id,
                "message_type": 2,
                "message_state": 2,
                "context_token": context_token,
                "item_list": [{"type": 1, "text_item": {"text": msg.content}}],
            },
            "base_info": {"channel_version": _CHANNEL_VERSION},
        }

        try:
            logger.debug("wechat: sending to {} with context_token={}...", chat_id, context_token[:20])
            resp = await self._api_post("/ilink/bot/sendmessage", body)
            if resp.status_code != 200:
                logger.error("wechat: sendmessage HTTP {}: {}", resp.status_code, resp.text)
                return
            data = resp.json()
            logger.debug("wechat: sendmessage response: {}", data)
            ret = data.get("ret", data.get("errcode", 0))
            if ret != 0:
                logger.error("wechat: sendmessage error (ret={}): {}", ret, data)
            else:
                logger.info("wechat: message sent to {}", chat_id)
        except Exception:
            logger.exception("wechat: sendmessage failed")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        consecutive_failures = 0

        while self._running:
            try:
                body = {
                    "base_info": {"channel_version": _CHANNEL_VERSION},
                    "get_updates_buf": self._sync_buf,
                    "timeout": _POLL_TIMEOUT,
                }
                resp = await self._api_post("/ilink/bot/getupdates", body)
                data = resp.json()

                errcode = data.get("ret", data.get("errcode", 0))

                if errcode == _SESSION_EXPIRED_CODE:
                    logger.warning(
                        "wechat: session expired (errcode={}), sleeping {}s",
                        errcode,
                        _SESSION_EXPIRED_SLEEP,
                    )
                    await asyncio.sleep(_SESSION_EXPIRED_SLEEP)
                    continue

                if errcode != 0:
                    logger.warning("wechat: getupdates errcode={}", errcode)
                    consecutive_failures += 1
                    if consecutive_failures >= _FAILURE_BACKOFF_THRESHOLD:
                        logger.warning(
                            "wechat: {} consecutive failures, backing off {}s",
                            consecutive_failures,
                            _FAILURE_BACKOFF_SLEEP,
                        )
                        await asyncio.sleep(_FAILURE_BACKOFF_SLEEP)
                    continue

                consecutive_failures = 0

                new_buf = (
                    data.get("get_updates_buf") or data.get("sync_buf") or ""
                )
                if new_buf:
                    self._sync_buf = new_buf
                    self._save_sync_buf()

                msgs = data.get("msgs") or data.get("message_list") or []
                if msgs:
                    logger.info("wechat: received {} message(s)", len(msgs))
                for msg in msgs:
                    logger.debug("wechat: inbound raw: {}", msg)
                    await self._process_inbound(msg)

            except httpx.ReadTimeout:
                # Normal for long-poll
                continue
            except Exception:
                logger.exception("wechat: poll iteration error")
                consecutive_failures += 1
                if consecutive_failures >= _FAILURE_BACKOFF_THRESHOLD:
                    await asyncio.sleep(_FAILURE_BACKOFF_SLEEP)

    # ------------------------------------------------------------------
    # Inbound processing
    # ------------------------------------------------------------------

    async def _process_inbound(self, msg: dict[str, Any]) -> None:
        try:
            from_user_id = msg.get("from_user_id", "")
            context_token = msg.get("context_token", "")
            message_type = msg.get("message_type", 0)

            # Skip bot messages (message_type 1 = user message)
            if message_type != 1:
                return

            # Skip messages from bots (bot IDs end with @im.bot)
            if from_user_id.endswith("@im.bot"):
                return

            item_list = msg.get("item_list", [])
            text = self._extract_text(item_list)
            if not text:
                return

            # Cache context_token for replies
            if context_token:
                self._context_tokens[from_user_id] = context_token
                if len(self._context_tokens) > _MAX_CONTEXT_CACHE:
                    self._context_tokens.popitem(last=False)

            await self._handle_message(
                sender_id=from_user_id,
                chat_id=from_user_id,
                content=text,
                metadata={"context_token": context_token},
            )
        except Exception:
            logger.exception("wechat: error processing inbound message")

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    async def _api_post(self, endpoint: str, body: dict[str, Any]) -> httpx.Response:
        assert self._http is not None
        url = self._base_url.rstrip("/") + endpoint
        headers = {
            "Authorization": f"Bearer {self._token}",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": self._uin,
            "Content-Type": "application/json",
        }
        return await self._http.post(url, json=body, headers=headers)

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def _load_credentials(self) -> bool:
        if not _CRED_FILE.exists():
            return False

        try:
            creds = json.loads(_CRED_FILE.read_text())
            self._token = creds.get("token", "")
            self._bot_id = creds.get("bot_id", "")
            if creds.get("base_url"):
                self._base_url = creds["base_url"]
        except Exception:
            logger.exception("wechat: failed to load credentials")
            return False

        if not self._token:
            logger.warning("wechat: credentials file exists but token is empty")
            return False

        # Load sync_buf cursor
        if _SYNC_BUF_FILE.exists():
            try:
                self._sync_buf = _SYNC_BUF_FILE.read_text().strip()
            except Exception:
                pass

        return True

    def _save_sync_buf(self) -> None:
        try:
            _AUTH_DIR.mkdir(parents=True, exist_ok=True)
            _SYNC_BUF_FILE.write_text(self._sync_buf)
        except Exception:
            logger.exception("wechat: failed to save sync_buf")

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(item_list: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for item in item_list:
            item_type = item.get("type", 0)

            if item_type == 1:
                # Text item — may include ref_msg (quoted reply)
                text_item = item.get("text_item", {})
                text = text_item.get("text", "")
                ref_msg = item.get("ref_msg")
                if ref_msg:
                    ref_text = ref_msg.get("text", "")
                    if ref_text:
                        parts.append(f"[引用: {ref_text}]")
                if text:
                    parts.append(text)

            elif item_type == 3:
                # Voice item — use transcription if available
                voice_item = item.get("voice_item", {})
                transcription = voice_item.get("text", "")
                if transcription:
                    parts.append(transcription)

        return "\n".join(parts)
