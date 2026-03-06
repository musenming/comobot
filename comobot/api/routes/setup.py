"""Setup wizard endpoint (first-time initialization)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from comobot.api.deps import get_auth, get_vault
from comobot.config.loader import load_config, save_config
from comobot.security.auth import AuthManager
from comobot.security.crypto import CredentialVault

router = APIRouter(prefix="/api/setup")


class SetupStatusResponse(BaseModel):
    setup_complete: bool


class SetupRequest(BaseModel):
    admin_username: str = "admin"
    admin_password: str
    provider: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    telegram_token: str | None = None
    telegram_mode: str = "polling"
    allowed_users: list[str] | None = None


class SetupResponse(BaseModel):
    success: bool
    message: str


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(auth: AuthManager = Depends(get_auth)):
    complete = await auth.is_setup_complete()
    return SetupStatusResponse(setup_complete=complete)


@router.post("", response_model=SetupResponse)
async def setup(
    body: SetupRequest,
    auth: AuthManager = Depends(get_auth),
    vault: CredentialVault = Depends(get_vault),
):
    if await auth.is_setup_complete():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setup already completed",
        )

    if len(body.admin_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    await auth.create_admin(body.admin_username, body.admin_password)
    await auth.ensure_jwt_secret()

    # Store credentials in encrypted vault
    if body.provider and body.api_key:
        await vault.store(body.provider, "api_key", body.api_key)

    if body.telegram_token:
        await vault.store("telegram", "bot_token", body.telegram_token)

    # Also update config.json so gateway can read settings at startup
    config = load_config()

    if body.provider and body.api_key:
        provider_cfg = getattr(config.providers, body.provider, None)
        if provider_cfg is not None:
            provider_cfg.api_key = body.api_key
            if body.api_base:
                provider_cfg.api_base = body.api_base

    if body.telegram_token:
        config.channels.telegram.enabled = True
        config.channels.telegram.token = body.telegram_token
        config.channels.telegram.mode = body.telegram_mode
        if body.allowed_users:
            config.channels.telegram.allow_from = body.allowed_users

    save_config(config)

    return SetupResponse(success=True, message="Setup completed successfully")
