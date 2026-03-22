"""WeChat channel implementation via Tencent iLink API (pure Python, httpx)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import random
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from loguru import logger

from comobot.bus.events import OutboundMessage
from comobot.bus.queue import MessageBus
from comobot.channels.base import BaseChannel
from comobot.config.schema import WechatConfig

_AUTH_DIR = Path.home() / ".comobot" / "wechat-auth"
_CRED_FILE = _AUTH_DIR / "credentials.json"
_SYNC_BUF_FILE = _AUTH_DIR / "sync_buf.txt"
_MEDIA_DIR = Path.home() / ".comobot" / "media"

_CHANNEL_VERSION = "1.0.2"
_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
_CDN_UPLOAD_RETRIES = 3
_MAX_CONTEXT_CACHE = 1000
_POLL_TIMEOUT = 35
_SESSION_EXPIRED_CODE = -14
_SESSION_EXPIRED_SLEEP = 3600  # 1 hour
_FAILURE_BACKOFF_THRESHOLD = 3
_FAILURE_BACKOFF_SLEEP = 30
_RECONNECT_SLEEP = 5

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


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

        # Extract inline markdown images from content
        content = msg.content or ""
        extra_media: list[str] = []
        if content:
            content, extra_media = self.extract_inline_images(content)

        # Send text message
        if content and content.strip():
            await self._send_text(chat_id, context_token, content.strip())

        # Send image files
        for media_path in (msg.media or []) + extra_media:
            await self._send_image_file(chat_id, context_token, media_path)

    async def _send_text(self, chat_id: str, context_token: str, text: str) -> None:
        client_id = self._gen_client_id()
        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": chat_id,
                "client_id": client_id,
                "message_type": 2,
                "message_state": 2,
                "context_token": context_token,
                "item_list": [{"type": 1, "text_item": {"text": text}}],
            },
            "base_info": {"channel_version": _CHANNEL_VERSION},
        }
        try:
            resp = await self._api_post("/ilink/bot/sendmessage", body)
            if resp.status_code != 200:
                logger.error("wechat: sendmessage HTTP {}: {}", resp.status_code, resp.text)
                return
            data = resp.json()
            ret = data.get("ret", data.get("errcode", 0))
            if ret != 0:
                logger.error("wechat: sendmessage error (ret={}): {}", ret, data)
            else:
                logger.info("wechat: text sent to {}", chat_id)
        except Exception:
            logger.exception("wechat: sendmessage failed")

    async def _send_image_file(self, chat_id: str, context_token: str, file_path: str) -> None:
        try:
            uploaded = await self._upload_to_cdn(file_path, chat_id)
            if not uploaded:
                logger.error("wechat: CDN upload failed for {}", file_path)
                return

            aes_key_b64 = base64.b64encode(uploaded["aeskey"].encode()).decode()

            image_item: dict[str, Any] = {
                "type": 2,
                "image_item": {
                    "media": {
                        "encrypt_query_param": uploaded["download_param"],
                        "aes_key": aes_key_b64,
                        "encrypt_type": 1,
                    },
                    "mid_size": uploaded["filesize_cipher"],
                },
            }

            client_id = self._gen_client_id()
            body = {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": chat_id,
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": context_token,
                    "item_list": [image_item],
                },
                "base_info": {"channel_version": _CHANNEL_VERSION},
            }

            resp = await self._api_post("/ilink/bot/sendmessage", body)
            if resp.status_code != 200:
                logger.error("wechat: send image HTTP {}: {}", resp.status_code, resp.text[:200])
                return
            data = resp.json()
            ret = data.get("ret", data.get("errcode", 0))
            if ret != 0:
                logger.error("wechat: send image error (ret={}): {}", ret, data)
            else:
                logger.info("wechat: image sent to {} ({})", chat_id, file_path)
        except Exception:
            logger.exception("wechat: send image failed for {}", file_path)

    # ------------------------------------------------------------------
    # CDN upload (AES-128-ECB)
    # ------------------------------------------------------------------

    async def _upload_to_cdn(self, file_path: str, to_user_id: str) -> dict[str, Any] | None:
        """Upload a local file to Weixin CDN. Returns upload info dict or None."""
        if not self._http:
            return None

        plaintext = await asyncio.to_thread(Path(file_path).read_bytes)
        rawsize = len(plaintext)
        rawfilemd5 = hashlib.md5(plaintext).hexdigest()  # noqa: S324
        filesize = _aes_ecb_padded_size(rawsize)
        filekey = os.urandom(16).hex()
        aeskey = os.urandom(16)

        # 1. Get upload URL
        upload_body = {
            "filekey": filekey,
            "media_type": 1,  # IMAGE
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aeskey.hex(),
            "base_info": {"channel_version": _CHANNEL_VERSION},
        }

        resp = await self._api_post("/ilink/bot/getuploadurl", upload_body)
        if resp.status_code != 200:
            logger.error("wechat: getuploadurl HTTP {}: {}", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        upload_param = data.get("upload_param")
        if not upload_param:
            logger.error("wechat: getuploadurl missing upload_param: {}", data)
            return None

        # 2. AES-128-ECB encrypt
        ciphertext = _aes_ecb_encrypt(plaintext, aeskey)

        # 3. Upload to CDN
        cdn_url = (
            f"{_CDN_BASE_URL}/upload"
            f"?encrypted_query_param={quote(upload_param)}"
            f"&filekey={quote(filekey)}"
        )

        download_param: str | None = None
        for attempt in range(1, _CDN_UPLOAD_RETRIES + 1):
            try:
                cdn_resp = await self._http.post(
                    cdn_url,
                    content=ciphertext,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=30.0,
                )
                if cdn_resp.status_code == 200:
                    download_param = cdn_resp.headers.get("x-encrypted-param")
                    if download_param:
                        break
                    logger.error("wechat: CDN missing x-encrypted-param header attempt={}", attempt)
                else:
                    logger.warning(
                        "wechat: CDN upload attempt={} status={}", attempt, cdn_resp.status_code
                    )
            except Exception as e:
                logger.warning("wechat: CDN upload attempt={} error: {}", attempt, e)
            if attempt < _CDN_UPLOAD_RETRIES:
                await asyncio.sleep(1)

        if not download_param:
            logger.error("wechat: CDN upload failed after {} attempts", _CDN_UPLOAD_RETRIES)
            return None

        return {
            "filekey": filekey,
            "download_param": download_param,
            "aeskey": aeskey.hex(),
            "filesize_raw": rawsize,
            "filesize_cipher": filesize,
        }

    # ------------------------------------------------------------------
    # CDN download (inbound image)
    # ------------------------------------------------------------------

    async def _download_from_cdn(
        self,
        encrypt_query_param: str,
        aes_key_b64: str,
    ) -> bytes | None:
        """Download and AES-128-ECB decrypt a file from the Weixin CDN."""
        if not self._http:
            return None

        url = f"{_CDN_BASE_URL}/download?encrypted_query_param={quote(encrypt_query_param)}"

        try:
            resp = await self._http.get(url, timeout=30.0)
            if resp.status_code != 200:
                logger.error("wechat: CDN download HTTP {}", resp.status_code)
                return None

            key = _parse_aes_key(aes_key_b64)
            if not key:
                logger.error("wechat: invalid AES key for CDN download")
                return None

            return _aes_ecb_decrypt(resp.content, key)
        except Exception:
            logger.exception("wechat: CDN download/decrypt failed")
            return None

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

                new_buf = data.get("get_updates_buf") or data.get("sync_buf") or ""
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
            media_paths = await self._download_inbound_media(item_list)

            if not text and not media_paths:
                return

            # Cache context_token for replies
            if context_token:
                self._context_tokens[from_user_id] = context_token
                if len(self._context_tokens) > _MAX_CONTEXT_CACHE:
                    self._context_tokens.popitem(last=False)

            content = text or "[image]" if not text and media_paths else text

            await self._handle_message(
                sender_id=from_user_id,
                chat_id=from_user_id,
                content=content,
                media=media_paths if media_paths else None,
                metadata={"context_token": context_token},
            )
        except Exception:
            logger.exception("wechat: error processing inbound message")

    async def _download_inbound_media(self, item_list: list[dict[str, Any]]) -> list[str]:
        """Download image/file media from inbound items, return local file paths."""
        paths: list[str] = []
        for item in item_list:
            item_type = item.get("type", 0)
            if item_type == 2:  # IMAGE
                image_item = item.get("image_item", {})
                media = image_item.get("media", {})
                eqp = media.get("encrypt_query_param")
                if not eqp:
                    continue

                # Resolve AES key: image_item.aeskey (hex) or media.aes_key (b64)
                aeskey_hex = image_item.get("aeskey")
                if aeskey_hex:
                    aes_key_b64 = base64.b64encode(bytes.fromhex(aeskey_hex)).decode()
                else:
                    aes_key_b64 = media.get("aes_key", "")

                if not aes_key_b64:
                    logger.warning("wechat: inbound image missing AES key")
                    continue

                data = await self._download_from_cdn(eqp, aes_key_b64)
                if not data:
                    continue

                # Save to media dir
                _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
                fname = f"wechat_img_{int(time.time() * 1000)}_{os.urandom(4).hex()}.jpg"
                fpath = _MEDIA_DIR / fname
                await asyncio.to_thread(fpath.write_bytes, data)
                paths.append(str(fpath))
                logger.debug("wechat: saved inbound image to {}", fpath)

        return paths

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
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _gen_client_id() -> str:
        return f"comobot-{int(time.time() * 1000)}-{os.urandom(4).hex()}"

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


# ------------------------------------------------------------------
# Module-level AES-128-ECB utilities
# ------------------------------------------------------------------


def _aes_ecb_padded_size(plaintext_size: int) -> int:
    """Compute AES-128-ECB ciphertext size with PKCS7 padding."""
    return math.ceil((plaintext_size + 1) / 16) * 16


def _aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt with AES-128-ECB + PKCS7 padding."""
    padder = PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(padded) + enc.finalize()


def _aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """Decrypt AES-128-ECB + PKCS7 padding."""
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    dec = cipher.decryptor()
    padded = dec.update(ciphertext) + dec.finalize()
    unpadder = PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def _parse_aes_key(aes_key_b64: str) -> bytes | None:
    """Parse AES key from base64. Handles both raw-16-byte and hex-32-char encodings."""
    try:
        decoded = base64.b64decode(aes_key_b64)
        if len(decoded) == 16:
            return decoded
        if len(decoded) == 32:
            # hex-encoded key: base64 → hex string → raw bytes
            try:
                return bytes.fromhex(decoded.decode("ascii"))
            except (ValueError, UnicodeDecodeError):
                pass
        logger.error("wechat: unexpected AES key length: {}", len(decoded))
        return None
    except Exception:
        logger.exception("wechat: failed to parse AES key")
        return None
