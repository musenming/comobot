"""Webhook endpoints for channel integrations."""

from fastapi import APIRouter, Header, HTTPException, Request, status
from loguru import logger

router = APIRouter(prefix="/webhook")


@router.post("/wechat")
async def wechat_webhook(
    request: Request,
    x_openclaw_token: str | None = Header(None),
):
    """
    Receive inbound WeChat messages forwarded by the openclaw-weixin plugin.

    The plugin POSTs JSON payloads with the following structure:
      {
        "openid":    "<wechat user openid>",
        "chat_id":   "<group id or openid>",
        "content":   "<message text>",
        "msg_id":    "<dedup id>",          // optional
        "nickname":  "<display name>",      // optional
        "is_group":  false                  // optional
      }
    """
    # Token verification
    channels = getattr(request.app.state, "channels", None)
    wechat_channel = channels.get_channel("wechat") if channels else None

    if wechat_channel:
        expected_token = wechat_channel.config.token
        if expected_token and x_openclaw_token != expected_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid X-Openclaw-Token",
            )

    body = await request.json()
    logger.debug("WeChat webhook payload: {}", body)

    if wechat_channel:
        await wechat_channel.handle_webhook(body)
    else:
        logger.warning("WeChat webhook received but wechat channel is not running")

    return {"ok": True}


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    """Receive Telegram webhook updates."""
    # Verify secret token if configured
    expected_secret = getattr(request.app.state, "telegram_secret_token", None)
    if expected_secret:
        if x_telegram_bot_api_secret_token != expected_secret:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid secret token",
            )

    body = await request.json()
    logger.debug("Telegram webhook update: {}", body)

    # Process the update through the Telegram channel handler
    telegram_handler = getattr(request.app.state, "telegram_webhook_handler", None)
    if telegram_handler:
        await telegram_handler(body)

    return {"ok": True}
