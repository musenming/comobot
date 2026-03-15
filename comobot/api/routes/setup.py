"""Setup wizard endpoint (first-time initialization)."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from comobot.api.deps import get_auth, get_vault
from comobot.config.loader import load_config, save_config
from comobot.security.auth import AuthManager
from comobot.security.crypto import CredentialVault

router = APIRouter(prefix="/api/setup")


class SetupStatusResponse(BaseModel):
    setup_complete: bool


class ProviderInfo(BaseModel):
    id: str
    name: str
    recommended: bool
    needs_key: bool
    fields: list[dict[str, Any]] = []


class ValidateKeyRequest(BaseModel):
    provider: str
    api_key: str


class ValidateKeyResponse(BaseModel):
    valid: bool
    message: str


class SetupRequest(BaseModel):
    admin_username: str = "admin"
    admin_password: str
    provider: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    provider_config: dict[str, str] | None = None  # Generic provider config fields
    # Legacy telegram fields (kept for backward compatibility)
    telegram_token: str | None = None
    telegram_mode: str = "polling"
    # Generic channel config
    channel_type: str | None = None
    channel_config: dict[str, str | list[str]] | None = None
    allowed_users: list[str] | None = None
    assistant_name: str | None = None
    language: str | None = None


class SetupResponse(BaseModel):
    success: bool
    message: str


# Provider config field definitions (what each provider needs in setup)
_KEY_FIELD = {"key": "api_key", "label": "API Key", "type": "secret", "required": True}
_BASE_FIELD = {"key": "api_base", "label": "API Base URL", "type": "text"}
_BASE_FIELD_REQ = {"key": "api_base", "label": "API Base URL", "type": "text", "required": True}

# Static provider list (mirrors ProvidersConfig fields)
_PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "openrouter",
        "name": "OpenRouter（推荐）",
        "recommended": True,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD, _BASE_FIELD],
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD, _BASE_FIELD],
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "dashscope",
        "name": "阿里云百炼 (DashScope)",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "moonshot",
        "name": "Moonshot (Kimi)",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "zhipu",
        "name": "智谱 AI (GLM)",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "siliconflow",
        "name": "硅基流动 (SiliconFlow)",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "volcengine",
        "name": "火山引擎 (VolcEngine)",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "groq",
        "name": "Groq",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "aihubmix",
        "name": "AiHubMix",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "minimax",
        "name": "MiniMax",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD],
    },
    {
        "id": "custom",
        "name": "自定义 OpenAI 兼容接口",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD, _BASE_FIELD_REQ],
    },
    {
        "id": "vllm",
        "name": "vLLM",
        "recommended": False,
        "needs_key": True,
        "fields": [_KEY_FIELD, _BASE_FIELD_REQ],
    },
    {
        "id": "ollama",
        "name": "本地模型（Ollama）",
        "recommended": False,
        "needs_key": False,
        "fields": [
            {
                "key": "api_base",
                "label": "API Base URL",
                "type": "text",
                "default": "http://localhost:11434/v1",
            }
        ],
    },
]

# Provider-to-litellm prefix mapping for key validation
_PROVIDER_MODEL_MAP: dict[str, str] = {
    "openrouter": "openrouter/openai/gpt-4o-mini",
    "openai": "openai/gpt-4o-mini",
    "anthropic": "anthropic/claude-haiku-4-5-20251001",
    "deepseek": "deepseek/deepseek-chat",
    "gemini": "gemini/gemini-1.5-flash",
    "dashscope": "openai/qwen-turbo",
    "moonshot": "openai/moonshot-v1-8k",
    "zhipu": "openai/glm-4-flash",
    "siliconflow": "openai/Qwen/Qwen2.5-7B-Instruct",
    "volcengine": "openai/doubao-lite-4k",
    "groq": "groq/llama-3.1-8b-instant",
    "aihubmix": "openai/gpt-4o-mini",
    "minimax": "minimax/MiniMax-Text-01",
    "custom": "openai/gpt-4o-mini",
}

_PROVIDER_BASE_MAP: dict[str, str] = {
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
    "aihubmix": "https://aihubmix.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(auth: AuthManager = Depends(get_auth)):
    complete = await auth.is_setup_complete()
    return SetupStatusResponse(setup_complete=complete)


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers():
    return [ProviderInfo(**p) for p in _PROVIDERS]


@router.get("/channels")
async def list_setup_channels():
    """List available channels with their config fields for setup wizard."""
    from comobot.api.routes.channels import CHANNEL_CONFIG_FIELDS, CHANNEL_TYPES

    results = []
    for ch in CHANNEL_TYPES:
        fields = CHANNEL_CONFIG_FIELDS.get(ch, [])
        results.append({"id": ch, "name": ch.capitalize(), "fields": fields})
    return results


@router.post("/validate-key", response_model=ValidateKeyResponse)
async def validate_key(body: ValidateKeyRequest):
    if body.provider == "ollama":
        return ValidateKeyResponse(valid=True, message="本地模型无需验证 API Key")

    model = _PROVIDER_MODEL_MAP.get(body.provider)
    if not model:
        return ValidateKeyResponse(valid=False, message=f"未知的提供商：{body.provider}")

    try:
        import litellm  # type: ignore

        litellm.suppress_debug_info = True
        api_base = _PROVIDER_BASE_MAP.get(body.provider)

        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: litellm.completion(
                    model=model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                    api_key=body.api_key,
                    api_base=api_base,
                ),
            ),
            timeout=10.0,
        )
        return ValidateKeyResponse(valid=True, message="验证成功")
    except asyncio.TimeoutError:
        return ValidateKeyResponse(valid=False, message="验证超时，请检查网络连接")
    except Exception as e:
        msg = str(e)
        if "401" in msg or "auth" in msg.lower() or "invalid" in msg.lower():
            return ValidateKeyResponse(valid=False, message="API Key 无效，请检查后重试")
        if "insufficient" in msg.lower() or "balance" in msg.lower() or "quota" in msg.lower():
            return ValidateKeyResponse(valid=False, message="API Key 余额不足")
        return ValidateKeyResponse(valid=False, message="验证失败：" + msg[:120])


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

    # Store credentials in encrypted vault & update config
    config = load_config()

    # --- Provider setup ---
    api_key = body.api_key
    api_base = body.api_base
    # If provider_config dict is provided, extract fields from it
    if body.provider_config:
        api_key = api_key or body.provider_config.get("api_key", "")
        api_base = api_base or body.provider_config.get("api_base", "")

    if body.provider and api_key:
        await vault.store(body.provider, "api_key", api_key)

    if body.provider:
        provider_cfg = getattr(config.providers, body.provider, None)
        if provider_cfg is not None:
            if api_key:
                provider_cfg.api_key = api_key
            if api_base:
                provider_cfg.api_base = api_base

    # --- Channel setup (generic) ---
    # Support new generic channel_type + channel_config
    if body.channel_type and body.channel_config:
        from comobot.api.routes.channels import CHANNEL_CONFIG_FIELDS, VAULT_TO_CONFIG_MAP

        ch_cfg = getattr(config.channels, body.channel_type, None)
        fields = CHANNEL_CONFIG_FIELDS.get(body.channel_type, [])
        field_types = {f["key"]: f.get("type") for f in fields}
        mapping = VAULT_TO_CONFIG_MAP.get(body.channel_type, {})

        for key, value in body.channel_config.items():
            if not value:
                continue
            # Store secrets in vault
            if field_types.get(key) in ("secret", "text") and isinstance(value, str):
                if field_types.get(key) == "secret":
                    await vault.store(body.channel_type, key, value)
                # Sync to config
                if ch_cfg is not None:
                    attr = mapping.get(key, key)
                    if hasattr(ch_cfg, attr):
                        if isinstance(value, list):
                            setattr(ch_cfg, attr, value)
                        else:
                            setattr(ch_cfg, attr, str(value))
            elif field_types.get(key) == "tags" and ch_cfg is not None:
                attr = mapping.get(key, key)
                if hasattr(ch_cfg, attr):
                    setattr(ch_cfg, attr, value if isinstance(value, list) else [])
            elif field_types.get(key) == "select" and ch_cfg is not None:
                attr = mapping.get(key, key)
                if hasattr(ch_cfg, attr):
                    if isinstance(getattr(ch_cfg, attr), bool):
                        setattr(ch_cfg, attr, str(value).lower() == "true")
                    else:
                        setattr(ch_cfg, attr, str(value))

        if ch_cfg is not None:
            ch_cfg.enabled = True

    # Legacy: telegram_token support for backward compatibility
    elif body.telegram_token:
        await vault.store("telegram", "bot_token", body.telegram_token)
        config.channels.telegram.enabled = True
        config.channels.telegram.token = body.telegram_token
        config.channels.telegram.mode = body.telegram_mode
        if body.allowed_users:
            config.channels.telegram.allow_from = body.allowed_users

    if body.assistant_name:
        config.assistant_name = body.assistant_name

    if body.language:
        config.language = body.language

    save_config(config)

    return SetupResponse(success=True, message="Setup completed successfully")
