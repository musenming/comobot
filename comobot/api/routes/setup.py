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
    telegram_token: str | None = None
    telegram_mode: str = "polling"
    allowed_users: list[str] | None = None
    assistant_name: str | None = None
    language: str | None = None


class SetupResponse(BaseModel):
    success: bool
    message: str


# Static provider list (mirrors ProvidersConfig fields)
_PROVIDERS: list[dict[str, Any]] = [
    {"id": "openrouter", "name": "OpenRouter（推荐）", "recommended": True, "needs_key": True},
    {"id": "openai", "name": "OpenAI", "recommended": False, "needs_key": True},
    {"id": "anthropic", "name": "Anthropic (Claude)", "recommended": False, "needs_key": True},
    {"id": "deepseek", "name": "DeepSeek", "recommended": False, "needs_key": True},
    {"id": "gemini", "name": "Google Gemini", "recommended": False, "needs_key": True},
    {"id": "dashscope", "name": "阿里云百炼 (DashScope)", "recommended": False, "needs_key": True},
    {"id": "moonshot", "name": "Moonshot (Kimi)", "recommended": False, "needs_key": True},
    {"id": "zhipu", "name": "智谱 AI (GLM)", "recommended": False, "needs_key": True},
    {
        "id": "siliconflow",
        "name": "硅基流动 (SiliconFlow)",
        "recommended": False,
        "needs_key": True,
    },
    {"id": "volcengine", "name": "火山引擎 (VolcEngine)", "recommended": False, "needs_key": True},
    {"id": "groq", "name": "Groq", "recommended": False, "needs_key": True},
    {"id": "aihubmix", "name": "AiHubMix", "recommended": False, "needs_key": True},
    {"id": "custom", "name": "自定义 OpenAI 兼容接口", "recommended": False, "needs_key": True},
    {"id": "ollama", "name": "本地模型（Ollama）", "recommended": False, "needs_key": False},
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

    if body.assistant_name:
        config.assistant_name = body.assistant_name

    if body.language:
        config.language = body.language

    save_config(config)

    return SetupResponse(success=True, message="Setup completed successfully")
