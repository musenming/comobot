"""ASR provider management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from comobot.api.deps import get_current_user
from comobot.config.loader import load_config, save_config
from comobot.config.schema import ASRProviderConfig

router = APIRouter(prefix="/api/asr")


def _mask_secret(s: str) -> str:
    """Mask a secret string for display."""
    if not s:
        return ""
    return s[:8] + "..." if len(s) > 8 else "****"


def _is_real_secret(val: str) -> bool:
    """Check if a value is a real secret (not a masked placeholder)."""
    return bool(val) and "..." not in val and "****" not in val


class ASRProviderCreate(BaseModel):
    provider: str  # provider name (key)
    mode: str = "rest"  # "rest" or "ali_nls"
    api_key: str = ""
    api_base: str = ""
    app_key: str = ""  # ali_nls: AppKey from console
    access_key_id: str = ""  # ali_nls: Alibaba Cloud AK ID
    access_key_secret: str = ""  # ali_nls: Alibaba Cloud AK Secret
    model: str = ""
    language: str | None = None


class ASRActiveUpdate(BaseModel):
    provider: str  # active provider name, or "" to disable
    enabled: bool = True


@router.get("")
async def list_asr_providers(_user: str = Depends(get_current_user)):
    """List all configured ASR providers and the active one."""
    config = load_config()
    asr = config.asr
    providers = []
    for name, p in asr.providers.items():
        providers.append(
            {
                "provider": name,
                "mode": p.mode,
                "api_key": _mask_secret(p.api_key),
                "api_base": p.api_base,
                "app_key": p.app_key,
                "access_key_id": _mask_secret(p.access_key_id),
                "access_key_secret": _mask_secret(p.access_key_secret),
                "model": p.model,
                "language": p.language,
                "active": name == asr.provider,
            }
        )
    return {
        "enabled": asr.enabled,
        "active_provider": asr.provider,
        "providers": providers,
    }


@router.get("/{provider}/config")
async def get_asr_provider_config(
    provider: str,
    _user: str = Depends(get_current_user),
):
    """Return ASR provider config (secrets masked)."""
    config = load_config()
    p = config.asr.providers.get(provider)
    if not p:
        raise HTTPException(status_code=404, detail="ASR provider not found")
    return {
        "mode": p.mode,
        "api_key": _mask_secret(p.api_key),
        "api_base": p.api_base,
        "app_key": p.app_key,
        "access_key_id": _mask_secret(p.access_key_id),
        "access_key_secret": _mask_secret(p.access_key_secret),
        "model": p.model,
        "language": p.language,
    }


@router.post("")
async def add_asr_provider(
    body: ASRProviderCreate,
    _user: str = Depends(get_current_user),
):
    """Add or update an ASR provider."""
    config = load_config()
    existing = config.asr.providers.get(body.provider)

    # Preserve existing secrets if the submitted value is masked
    api_key = (
        body.api_key if _is_real_secret(body.api_key) else (existing.api_key if existing else "")
    )
    ak_id = (
        body.access_key_id
        if _is_real_secret(body.access_key_id)
        else (existing.access_key_id if existing else "")
    )
    ak_secret = (
        body.access_key_secret
        if _is_real_secret(body.access_key_secret)
        else (existing.access_key_secret if existing else "")
    )

    config.asr.providers[body.provider] = ASRProviderConfig(
        mode=body.mode,
        api_key=api_key,
        api_base=body.api_base,
        app_key=body.app_key,
        access_key_id=ak_id,
        access_key_secret=ak_secret,
        model=body.model,
        language=body.language or None,
    )

    # Auto-enable and set active if this is the first provider
    if not config.asr.provider:
        config.asr.provider = body.provider
        config.asr.enabled = True

    save_config(config)

    # Invalidate cached provider instance so new config takes effect
    asr_service = getattr(config, "_asr_service_ref", None)
    if asr_service:
        asr_service.invalidate_provider(body.provider)

    return {"provider": body.provider, "stored": True}


@router.put("/active")
async def set_active_asr(
    body: ASRActiveUpdate,
    _user: str = Depends(get_current_user),
):
    """Set the active ASR provider."""
    config = load_config()
    if body.provider and body.provider not in config.asr.providers:
        raise HTTPException(status_code=404, detail="ASR provider not found")
    config.asr.provider = body.provider
    config.asr.enabled = body.enabled
    save_config(config)
    return {"active_provider": body.provider, "enabled": body.enabled}


@router.delete("/{provider}")
async def delete_asr_provider(
    provider: str,
    _user: str = Depends(get_current_user),
):
    """Delete an ASR provider."""
    config = load_config()
    if provider not in config.asr.providers:
        raise HTTPException(status_code=404, detail="ASR provider not found")
    del config.asr.providers[provider]
    # Clear active if it was the deleted one
    if config.asr.provider == provider:
        config.asr.provider = ""
        if not config.asr.providers:
            config.asr.enabled = False
    save_config(config)
    return {"deleted": True}


@router.post("/{provider}/test")
async def test_asr_provider(
    provider: str,
    _user: str = Depends(get_current_user),
):
    """Test an ASR provider connectivity.

    - REST mode: tries GET /models on the api_base.
    - ali_nls mode: tries to obtain a token via AK/SK.
    """
    config = load_config()
    p = config.asr.providers.get(provider)
    if not p:
        raise HTTPException(status_code=404, detail="ASR provider not found")

    if p.mode == "ali_nls":
        return await _test_ali_nls(provider, p)
    return await _test_rest(provider, p)


async def _test_rest(provider: str, p: ASRProviderConfig) -> dict:
    """Test a REST ASR provider."""
    if not p.api_key:
        raise HTTPException(status_code=400, detail="No API key configured")

    import httpx

    api_base = p.api_base.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{api_base}/models",
                headers={"Authorization": f"Bearer {p.api_key}"},
            )
            if resp.status_code in (200, 404):
                return {"provider": provider, "status": "ok", "detail": "API reachable"}
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"ASR API returned {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Connection failed: {e}")
    return {"provider": provider, "status": "ok"}


async def _test_ali_nls(provider: str, p: ASRProviderConfig) -> dict:
    """Test an Ali NLS provider by obtaining a token."""
    if not p.access_key_id or not p.access_key_secret:
        if p.api_key:
            return {
                "provider": provider,
                "status": "ok",
                "detail": "Static token configured (cannot verify validity)",
            }
        raise HTTPException(
            status_code=400,
            detail="Ali NLS requires access_key_id and access_key_secret",
        )

    try:
        from comobot.asr.token_manager import TokenManager

        mgr = TokenManager(p.access_key_id, p.access_key_secret)
        token = await mgr.get_token()
        return {
            "provider": provider,
            "status": "ok",
            "detail": f"Token obtained: {token[:16]}...",
            "app_key": p.app_key or "(not set)",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Token creation failed: {e}")
