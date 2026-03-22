"""Webhook endpoints for channel integrations."""

from fastapi import APIRouter, Header, HTTPException, Request, status
from loguru import logger

router = APIRouter(prefix="/webhook")


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
