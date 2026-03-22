"""WeChat login tool — get QR code and poll for scan status."""

from __future__ import annotations

import base64
import io
import json
import os
import random
import time
from pathlib import Path
from typing import Any

from loguru import logger

from comobot.agent.tools.base import Tool

_AUTH_DIR = Path.home() / ".comobot" / "wechat-auth"
_CRED_FILE = _AUTH_DIR / "credentials.json"
_CONFIG_FILE = Path.home() / ".comobot" / "config.json"


class WechatLoginTool(Tool):
    """Tool to login WeChat via iLink QR code."""

    @property
    def name(self) -> str:
        return "wechat_login"

    @property
    def description(self) -> str:
        return (
            "Login WeChat via QR code scan. "
            "action='qr' to get the QR code, "
            "action='poll' with qrcode_token to check scan status."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["qr", "poll"],
                    "description": "'qr' to get QR code, 'poll' to check scan status",
                },
                "qrcode_token": {
                    "type": "string",
                    "description": "Token from 'qr' action, required for 'poll'",
                },
                "uin": {
                    "type": "string",
                    "description": "UIN from 'qr' action, required for 'poll'",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str = "qr", **kwargs: Any) -> str:
        if action == "qr":
            return await self._get_qr()
        elif action == "poll":
            token = kwargs.get("qrcode_token", "")
            uin = kwargs.get("uin", "")
            auto_restart = kwargs.get("auto_restart", True)
            if not token or not uin:
                return "Error: qrcode_token and uin are required for poll action."
            return await self._poll_status(token, uin, auto_restart=auto_restart)
        return f"Unknown action: {action}"

    async def _get_qr(self) -> str:
        import httpx

        base_url = self._load_base_url()
        uin = base64.b64encode(str(random.randint(0, 2**32 - 1)).encode()).decode()

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{base_url}/ilink/bot/get_bot_qrcode",
                    params={"bot_type": "3"},
                    headers={"X-WECHAT-UIN": uin},
                )
                data = resp.json()
        except Exception as e:
            logger.exception("wechat_login: failed to get QR code")
            return f"获取二维码失败: {e}"

        qrcode_token = data.get("qrcode", "")
        if not qrcode_token:
            return f"二维码获取失败，API 返回: {data}"

        # Try to extract scannable content
        qr_content = qrcode_token
        qrcode_img_raw = data.get("qrcode_img_content", "")
        extracted = self._extract_qr_content(qrcode_img_raw)
        if extracted:
            qr_content = extracted

        # Prefer image QR for web frontend, fallback to ASCII
        image_qr = self._image_qr(qr_content)
        if image_qr:
            qr_display = image_qr
        else:
            qr_display = f"```\n{self._ascii_qr(qr_content)}\n```"

        return (
            f"请用微信扫描以下二维码登录：\n\n"
            f"{qr_display}\n\n"
            f"扫码后请告诉我，我会帮你检查登录状态。\n"
            f"QRCODE_TOKEN={qrcode_token}\n"
            f"UIN={uin}"
        )

    async def _poll_status(self, qrcode_token: str, uin: str, *, auto_restart: bool = True) -> str:
        import asyncio

        import httpx

        base_url = self._load_base_url()

        try:
            async with httpx.AsyncClient(timeout=45) as client:
                for _ in range(30):
                    try:
                        resp = await client.get(
                            f"{base_url}/ilink/bot/get_qrcode_status",
                            params={"qrcode": qrcode_token},
                            headers={"X-WECHAT-UIN": uin},
                            timeout=45,
                        )
                        data = resp.json()
                    except httpx.ReadTimeout:
                        continue

                    status = data.get("status", "")

                    if status == "confirmed":
                        return self._handle_confirmed(data, base_url, auto_restart=auto_restart)

                    if status == "expired":
                        return "二维码已过期，请重新发起「登录微信」。"

                    if status == "scanned":
                        return "已扫码，等待确认中... 请在微信上点击确认，然后再让我检查一次状态。"

                    await asyncio.sleep(2)

            return "等待超时，请重新发起「登录微信」。"
        except Exception as e:
            logger.exception("wechat_login: poll failed")
            return f"轮询状态失败: {e}"

    def _handle_confirmed(self, data: dict, base_url: str, *, auto_restart: bool = True) -> str:
        bot_token = data.get("bot_token", "")
        bot_id = data.get("bot_id", "")
        user_id = data.get("user_id", "")

        if not bot_token:
            return "登录已确认但未收到 bot_token，请重试。"

        # Save credentials
        _AUTH_DIR.mkdir(parents=True, exist_ok=True)
        creds = {
            "token": bot_token,
            "base_url": base_url,
            "bot_id": bot_id,
            "user_id": user_id,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _CRED_FILE.write_text(json.dumps(creds, indent=2, ensure_ascii=False))

        # Enable in config
        self._enable_wechat_config()

        # Auto-restart gateway (skip during setup flow)
        if auto_restart:
            self._schedule_gateway_restart()

        return (
            f"✅ 微信登录成功！\n"
            f"Bot ID: {bot_id}\n"
            f"凭证已保存至: {_CRED_FILE}\n"
            f"Gateway 即将自动重启以使微信通道生效…"
        )

    @staticmethod
    def _load_base_url() -> str:
        if _CONFIG_FILE.exists():
            try:
                data = json.loads(_CONFIG_FILE.read_text())
                url = data.get("channels", {}).get("wechat", {}).get("base_url", "")
                if url:
                    return url.rstrip("/")
            except Exception:
                pass
        return "https://ilinkai.weixin.qq.com"

    @staticmethod
    def _schedule_gateway_restart() -> None:
        """Schedule a gateway restart after a short delay."""
        import asyncio
        import signal
        import subprocess
        import sys

        async def _restart():
            await asyncio.sleep(3)  # let the response reach the frontend first
            comobot_bin = sys.executable.replace("/python", "/comobot")
            if not Path(comobot_bin).exists():
                comobot_bin = "comobot"
            port = int(os.environ.get("COMOBOT_PORT", "18790"))
            cmd = [comobot_bin, "gateway", "--port", str(port)]
            from comobot.utils.log_sanitizer import SanitizedFileWriter

            log_dir = Path.home() / ".comobot" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            lf = SanitizedFileWriter(str(log_dir / "gateway.log"))
            subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=lf,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info("wechat_login: spawned new gateway, terminating current process")
            os.kill(os.getpid(), signal.SIGTERM)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_restart())
            logger.info("wechat_login: gateway restart scheduled in 3s")
        except RuntimeError:
            logger.warning("wechat_login: no running event loop, skip auto-restart")

    @staticmethod
    def _enable_wechat_config() -> None:
        try:
            data = {}
            if _CONFIG_FILE.exists():
                data = json.loads(_CONFIG_FILE.read_text())

            channels = data.setdefault("channels", {})
            wechat = channels.setdefault("wechat", {})
            wechat["enabled"] = True
            if not wechat.get("allow_from"):
                wechat["allow_from"] = ["*"]

            _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            logger.info("wechat_login: enabled wechat in config")
        except Exception:
            logger.exception("wechat_login: failed to update config")

    @staticmethod
    def _ascii_qr(data: str) -> str:
        try:
            import qrcode as qr_lib

            qr = qr_lib.QRCode(border=1, error_correction=qr_lib.constants.ERROR_CORRECT_L)
            qr.add_data(data)
            qr.make(fit=True)
            buf = io.StringIO()
            qr.print_ascii(out=buf, invert=True)
            return buf.getvalue()
        except ImportError:
            return f"[无法生成二维码，请安装: pip install qrcode]\nQR 内容: {data}"

    @staticmethod
    def _image_qr(data: str) -> str | None:
        """Generate QR code as PNG image, save to media dir, return markdown link."""
        try:
            import qrcode as qr_lib

            qr = qr_lib.QRCode(
                border=2,
                error_correction=qr_lib.constants.ERROR_CORRECT_L,
                box_size=10,
            )
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            media_dir = Path.home() / ".comobot" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            filename = f"wechat_qr_{int(time.time())}.png"
            filepath = media_dir / filename
            img.save(str(filepath))

            return f"![微信登录二维码](/api/media/{filename})"
        except Exception:
            logger.exception("wechat_login: failed to generate QR image")
            return None

    @staticmethod
    def _extract_qr_content(raw: str) -> str | None:
        if not raw:
            return None
        if raw.startswith(("http://", "https://")):
            return raw
        for decode_fn in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                img_data = decode_fn(raw)
                if len(img_data) < 100:
                    continue
                if img_data[:4] not in (b"\x89PNG", b"\xff\xd8\xff", b"GIF8"):
                    continue
                from PIL import Image
                from pyzbar.pyzbar import decode as decode_qr

                img = Image.open(io.BytesIO(img_data))
                results = decode_qr(img)
                if results:
                    return results[0].data.decode()
            except Exception:
                continue
        return None
