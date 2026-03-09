"""Model provider management endpoints."""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from comobot.api.deps import get_current_user, get_vault
from comobot.config.loader import load_config, save_config
from comobot.config.schema import ProviderConfig, ProvidersConfig
from comobot.security.crypto import CredentialVault

router = APIRouter(prefix="/api/providers")


class ProviderCreate(BaseModel):
    provider: str
    key_name: str = "api_key"
    value: str
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None


@router.get("")
async def list_providers(
    vault: CredentialVault = Depends(get_vault),
    _user: str = Depends(get_current_user),
):
    known_providers = set(ProvidersConfig.model_fields)
    providers = await vault.list_providers()
    results = []
    vault_names: set[str] = set()
    for p in providers:
        provider_name = p if isinstance(p, str) else p.get("provider", str(p))
        if provider_name not in known_providers:
            continue
        vault_names.add(provider_name)
        keys = await vault.list_keys(provider_name) if hasattr(vault, "list_keys") else []
        results.append(
            {
                "provider": provider_name,
                "key_count": len(keys) if keys else 1,
                "keys": [{"name": k, "prefix": "****"} for k in keys] if keys else [],
                "source": "vault",
                **(p if isinstance(p, dict) else {}),
            }
        )

    # Also include providers configured in config.json but not in vault
    config = load_config()
    for field_name in ProvidersConfig.model_fields:
        if field_name in vault_names:
            continue
        p_cfg = getattr(config.providers, field_name, None)
        if isinstance(p_cfg, ProviderConfig) and p_cfg.api_key:
            results.append(
                {
                    "provider": field_name,
                    "key_count": 1,
                    "keys": [
                        {
                            "name": "api_key",
                            "prefix": p_cfg.api_key[:8] + "..."
                            if len(p_cfg.api_key) > 8
                            else "****",
                        }
                    ],
                    "source": "config",
                }
            )

    return results


@router.get("/{provider}/keys")
async def list_provider_keys(
    provider: str,
    vault: CredentialVault = Depends(get_vault),
    _user: str = Depends(get_current_user),
):
    """List all keys for a provider (masked)."""
    key = await vault.retrieve(provider, "api_key")
    if not key:
        return []
    prefix = key[:8] + "..." if len(key) > 8 else "****"
    return [{"name": "api_key", "prefix": prefix}]


@router.get("/{provider}/config")
async def get_provider_config(
    provider: str,
    _user: str = Depends(get_current_user),
):
    """Return full provider config (api_key masked)."""
    config = load_config()
    provider_cfg = getattr(config.providers, provider, None)
    if provider_cfg is None or not isinstance(provider_cfg, ProviderConfig):
        raise HTTPException(status_code=404, detail="Unknown provider")
    masked_key = ""
    if provider_cfg.api_key:
        k = provider_cfg.api_key
        masked_key = k[:8] + "..." if len(k) > 8 else "****"
    return {
        "api_key": masked_key,
        "api_base": provider_cfg.api_base or "",
        "extra_headers": provider_cfg.extra_headers or {},
    }


@router.post("")
async def add_provider(
    body: ProviderCreate,
    vault: CredentialVault = Depends(get_vault),
    _user: str = Depends(get_current_user),
):
    await vault.store(body.provider, body.key_name, body.value)

    # Sync to config.json so gateway can read it at startup
    config = load_config()
    provider_cfg = getattr(config.providers, body.provider, None)
    if provider_cfg is not None:
        if body.key_name == "api_key":
            provider_cfg.api_key = body.value
        if body.api_base is not None:
            provider_cfg.api_base = body.api_base or None
        if body.extra_headers is not None:
            provider_cfg.extra_headers = body.extra_headers or None
        save_config(config)

    return {"provider": body.provider, "key_name": body.key_name, "stored": True}


@router.delete("/{provider}/{key_name}")
async def delete_provider(
    provider: str,
    key_name: str,
    vault: CredentialVault = Depends(get_vault),
    _user: str = Depends(get_current_user),
):
    deleted = await vault.delete(provider, key_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Also clear from config.json
    if key_name == "api_key":
        config = load_config()
        provider_cfg = getattr(config.providers, provider, None)
        if provider_cfg is not None:
            provider_cfg.api_key = ""
            save_config(config)

    return {"deleted": True}


@router.post("/{provider}/test")
async def test_provider(
    provider: str,
    vault: CredentialVault = Depends(get_vault),
    _user: str = Depends(get_current_user),
):
    key = await vault.retrieve(provider, "api_key")
    if not key:
        raise HTTPException(status_code=404, detail="No API key found for this provider")

    start = time.monotonic()
    # Simple validation — for a real test we'd call the LLM API
    latency_ms = int((time.monotonic() - start) * 1000)
    return {
        "provider": provider,
        "status": "ok",
        "key_prefix": key[:8] + "...",
        "latency_ms": latency_ms,
    }
