"""LiteLLM provider implementation for multi-provider support."""

import asyncio
import os
import secrets
import string
from typing import Any

from loguru import logger

# Prevent LiteLLM from fetching remote cost map on import (avoids timeout
# errors when user has no proxy / restricted network).  Must be set *before*
# ``import litellm`` because the module reads this env var at import time.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import json_repair
import litellm
from litellm import acompletion

# Suppress the "Give Feedback / Get Help" banner and debug info that LiteLLM
# prints at module level.  Must happen right after import, before any usage.
litellm.suppress_debug_info = True
litellm.drop_params = True

from comobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest  # noqa: E402
from comobot.providers.registry import (  # noqa: E402
    find_by_model,
    find_gateway,
)

# Standard chat-completion message keys.
_ALLOWED_MSG_KEYS = frozenset(
    {"role", "content", "tool_calls", "tool_call_id", "name", "reasoning_content"}
)
_ANTHROPIC_EXTRA_KEYS = frozenset({"thinking_blocks"})
# Roles accepted by LLM providers; internal roles like "process" are dropped.
_LLM_ROLES = frozenset({"system", "user", "assistant", "tool"})
_ALNUM = string.ascii_letters + string.digits


def _short_tool_id() -> str:
    """Generate a 9-char alphanumeric ID compatible with all providers (incl. Mistral)."""
    return "".join(secrets.choice(_ALNUM) for _ in range(9))


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

# Errors that should NOT be retried (permanent failures).
_NO_RETRY_TYPES = frozenset({"content_safety", "auth", "context_length"})


def _classify_error(exc: Exception) -> str | None:
    """Classify a LiteLLM exception into an error type.

    Returns one of: "content_safety", "rate_limit", "auth",
    "context_length", "network", or None (unknown).
    """
    # Order: most specific first — ContextWindowExceededError and
    # ContentPolicyViolationError are subclasses of BadRequestError.
    if isinstance(exc, litellm.ContentPolicyViolationError):
        return "content_safety"
    if isinstance(exc, litellm.ContextWindowExceededError):
        return "context_length"
    if isinstance(exc, litellm.AuthenticationError):
        return "auth"
    if isinstance(exc, litellm.RateLimitError):
        return "rate_limit"
    if isinstance(exc, litellm.UnprocessableEntityError):
        msg = str(exc).lower()
        if "sensitive" in msg or "1027" in msg:
            return "content_safety"
        return None
    if isinstance(exc, (litellm.Timeout, litellm.ServiceUnavailableError)):
        return "network"
    if isinstance(exc, litellm.APIConnectionError):
        # MiniMax content safety comes as APIConnectionError wrapping MinimaxException
        msg = str(exc).lower()
        if "sensitive" in msg or "1027" in msg:
            return "content_safety"
        return "network"
    return None


# ---------------------------------------------------------------------------


def _merge_content(a: Any, b: Any) -> Any:
    """Merge two message content values (str, list, or dict) into one."""
    if isinstance(a, str) and isinstance(b, str):
        return f"{a}\n\n{b}"

    def _to_list(c: Any) -> list:
        if isinstance(c, str):
            return [{"type": "text", "text": c}]
        if isinstance(c, list):
            return list(c)
        return [c]

    return _to_list(a) + _to_list(b)


def _merge_consecutive_same_role(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge consecutive messages with the same role.

    Many providers (e.g. DeepSeek, MiniMax) reject consecutive user or
    assistant messages.  This collapses them into a single message.
    """
    if not messages:
        return messages
    result: list[dict[str, Any]] = [messages[0]]
    for msg in messages[1:]:
        if msg.get("role") == result[-1].get("role") and msg["role"] in ("user", "assistant"):
            result[-1] = {
                **result[-1],
                "content": _merge_content(result[-1]["content"], msg["content"]),
            }
        else:
            result.append(msg)
    return result


def _convert_system_to_user(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert system messages to user messages.

    For providers that reject the ``system`` role (e.g. MiniMax), the system
    prompt is re-packaged as a user message.  ``cache_control`` attributes are
    stripped since they have no meaning outside the system role.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "system":
            content = msg["content"]
            if isinstance(content, list):
                content = [
                    {k: v for k, v in item.items() if k != "cache_control"}
                    if isinstance(item, dict)
                    else item
                    for item in content
                ]
            result.append({**msg, "role": "user", "content": content})
        else:
            result.append(msg)
    return result


def _strip_non_standard_keys(
    messages: list[dict[str, Any]],
    extra_keys: frozenset[str] = frozenset(),
    excluded_keys: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Drop internal roles and non-standard keys from messages.

    Internal roles like ``process`` are silently dropped so that
    provider-specific role validation never sees them.  Assistant messages
    without a ``content`` key get ``content: None`` (required by strict
    providers).
    """
    allowed = (_ALLOWED_MSG_KEYS | extra_keys) - excluded_keys
    sanitized: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") not in _LLM_ROLES:
            continue
        clean = {k: v for k, v in msg.items() if k in allowed}
        if clean.get("role") == "assistant" and "content" not in clean:
            clean["content"] = None
        sanitized.append(clean)
    return sanitized


class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for multi-provider support.

    Supports OpenRouter, Anthropic, OpenAI, Gemini, MiniMax, and many other providers through
    a unified interface.  Provider-specific logic is driven by the registry
    (see providers/registry.py) — no if-elif chains needed here.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "anthropic/claude-opus-4-5",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}

        # Detect gateway / local deployment.
        # provider_name (from config key) is the primary signal;
        # api_key / api_base are fallback for auto-detection.
        self._gateway = find_gateway(provider_name, api_key, api_base)

        # Configure environment variables
        if api_key:
            self._setup_env(api_key, api_base, default_model)

        if api_base:
            litellm.api_base = api_base

        # NOTE: suppress_debug_info and drop_params are set at module level above.

    def _setup_env(self, api_key: str, api_base: str | None, model: str) -> None:
        """Set environment variables based on detected provider."""
        spec = self._gateway or find_by_model(model)
        if not spec:
            return
        if not spec.env_key:
            # OAuth/provider-only specs (for example: openai_codex)
            return

        # Gateway/local overrides existing env; standard provider doesn't
        if self._gateway:
            os.environ[spec.env_key] = api_key
        else:
            os.environ.setdefault(spec.env_key, api_key)

        # Resolve env_extras placeholders:
        #   {api_key}  → user's API key
        #   {api_base} → user's api_base, falling back to spec.default_api_base
        effective_base = api_base or spec.default_api_base
        for env_name, env_val in spec.env_extras:
            resolved = env_val.replace("{api_key}", api_key)
            resolved = resolved.replace("{api_base}", effective_base)
            os.environ.setdefault(env_name, resolved)

    def _resolve_model(self, model: str) -> str:
        """Resolve model name by applying provider/gateway prefixes."""
        if self._gateway:
            # Gateway mode: apply gateway prefix, skip provider-specific prefixes
            prefix = self._gateway.litellm_prefix
            if self._gateway.strip_model_prefix:
                model = model.split("/")[-1]
            if prefix and not model.startswith(f"{prefix}/"):
                model = f"{prefix}/{model}"
            return model

        # Standard mode: auto-prefix for known providers
        spec = find_by_model(model)
        if spec and spec.litellm_prefix:
            model = self._canonicalize_explicit_prefix(model, spec.name, spec.litellm_prefix)
            if not any(model.startswith(s) for s in spec.skip_prefixes):
                model = f"{spec.litellm_prefix}/{model}"

        return model

    @staticmethod
    def _canonicalize_explicit_prefix(model: str, spec_name: str, canonical_prefix: str) -> str:
        """Normalize explicit provider prefixes like `github-copilot/...`."""
        if "/" not in model:
            return model
        prefix, remainder = model.split("/", 1)
        if prefix.lower().replace("-", "_") != spec_name:
            return model
        return f"{canonical_prefix}/{remainder}"

    def _supports_cache_control(self, model: str) -> bool:
        """Return True when the provider supports cache_control on content blocks."""
        if self._gateway is not None:
            return self._gateway.supports_prompt_caching
        spec = find_by_model(model)
        return spec is not None and spec.supports_prompt_caching

    def _apply_cache_control(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        """Return copies of messages and tools with cache_control injected."""
        new_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                content = msg["content"]
                if isinstance(content, str):
                    new_content = [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ]
                else:
                    new_content = list(content)
                    new_content[-1] = {**new_content[-1], "cache_control": {"type": "ephemeral"}}
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)

        new_tools = tools
        if tools:
            new_tools = list(tools)
            new_tools[-1] = {**new_tools[-1], "cache_control": {"type": "ephemeral"}}

        return new_messages, new_tools

    def _apply_model_overrides(self, model: str, kwargs: dict[str, Any]) -> None:
        """Apply model-specific parameter overrides from the registry."""
        model_lower = model.lower()
        spec = find_by_model(model)
        if spec:
            for pattern, overrides in spec.model_overrides:
                if pattern in model_lower:
                    kwargs.update(overrides)
                    return

    @staticmethod
    def _extra_msg_keys(original_model: str, resolved_model: str) -> frozenset[str]:
        """Return provider-specific extra keys to preserve in request messages."""
        spec = find_by_model(original_model) or find_by_model(resolved_model)
        if spec and spec.extra_msg_keys:
            return spec.extra_msg_keys
        # Fallback: detect Anthropic by model name for gateway scenarios
        if "claude" in original_model.lower() or resolved_model.startswith("anthropic/"):
            return _ANTHROPIC_EXTRA_KEYS
        return frozenset()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """
        Send a chat completion request via LiteLLM.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'anthropic/claude-sonnet-4-5').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        original_model = model or self.default_model
        model = self._resolve_model(original_model)

        # Resolve provider spec once — used for all adaptation decisions.
        spec = find_by_model(original_model) or find_by_model(model)
        extra_msg_keys = self._extra_msg_keys(original_model, model)

        # Provider-specific prompt caching (e.g. Anthropic)
        if self._supports_cache_control(original_model):
            messages, tools = self._apply_cache_control(messages, tools)

        # --- Message adaptation pipeline ---
        messages = LLMProvider._sanitize_empty_content(messages)
        # MiniMax does not support the system role — convert to user
        if spec and not spec.supports_system_role:
            messages = _convert_system_to_user(messages)
        messages = _merge_consecutive_same_role(messages)
        excluded_msg_keys = spec.excluded_msg_keys if spec else frozenset()
        messages = _strip_non_standard_keys(
            messages, extra_keys=extra_msg_keys, excluded_keys=excluded_msg_keys
        )

        # Clamp max_tokens to at least 1 — negative or zero values cause
        # LiteLLM to reject the request with "max_tokens must be at least 1".
        max_tokens = max(1, max_tokens)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Apply model-specific overrides (e.g. kimi-k2.5 temperature)
        self._apply_model_overrides(model, kwargs)

        # Pass api_key directly — more reliable than env vars alone
        if self.api_key:
            kwargs["api_key"] = self.api_key

        # Pass api_base for custom endpoints
        if self.api_base:
            kwargs["api_base"] = self.api_base

        # Pass extra headers (e.g. APP-Code for AiHubMix)
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers

        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
            kwargs["drop_params"] = True

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        msg_count = len(kwargs["messages"])
        tool_count = len(tools) if tools else 0
        logger.info("LLM request: model={}, messages={}, tools={}", model, msg_count, tool_count)

        try:
            response = await acompletion(**kwargs)
            result = self._parse_response(response)
            tc_count = len(result.tool_calls) if result.tool_calls else 0
            usage = result.usage or {}
            logger.info(
                "LLM response: tokens={}/{}, finish={}, tool_calls={}",
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
                result.finish_reason,
                tc_count,
            )
            return result
        except Exception as e:
            error_type = _classify_error(e)

            # Non-retryable errors — return immediately
            if error_type in _NO_RETRY_TYPES:
                logger.warning("LLM non-retryable error ({}): {}", error_type, str(e)[:200])
                return LLMResponse(
                    content=f"Error calling LLM: {str(e)}",
                    finish_reason="error",
                    error_type=error_type,
                )

            # Retryable errors (rate_limit, network) — retry up to 2 times
            if error_type in ("rate_limit", "network"):
                last_exc = e
                for attempt in range(2):
                    delay = (attempt + 1) * 1.0  # 1s, 2s
                    logger.info(
                        "LLM transient error ({}), retry {}/2 in {}s: {}",
                        error_type,
                        attempt + 1,
                        delay,
                        str(e)[:100],
                    )
                    await asyncio.sleep(delay)
                    try:
                        response = await acompletion(**kwargs)
                        result = self._parse_response(response)
                        logger.info("LLM retry {}/2 succeeded", attempt + 1)
                        return result
                    except Exception as retry_e:
                        last_exc = retry_e
                        continue

                logger.error("LLM retries exhausted ({}): {}", error_type, str(last_exc)[:200])
                return LLMResponse(
                    content=f"Error calling LLM: {str(last_exc)}",
                    finish_reason="error",
                    error_type=error_type,
                )

            # Unknown errors — no retry
            logger.error("LLM unknown error: {}", str(e)[:200])
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
                error_type=error_type,
            )

    @staticmethod
    def _get_tool_field(tc: Any, field: str, default: Any = None) -> Any:
        """Get a field from a tool_call, handling both attribute and dict access."""
        # Try attribute access first (Pydantic model: tc.id)
        val = getattr(tc, field, None)
        if val is not None:
            return val
        # Try dict access (TypedDict: tc.get("id"))
        if hasattr(tc, "get"):
            dict_val = tc.get(field)
            if dict_val is not None:
                return dict_val
        return default

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse LiteLLM response into our standard format."""
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                # Extract function.name and function.arguments
                # tc.function is itself a TypedDict/model with 'name' and 'arguments' fields
                func = self._get_tool_field(tc, "function") or {}
                func_name = self._get_tool_field(func, "name", "")
                args_raw = self._get_tool_field(func, "arguments", "")
                args = args_raw
                if isinstance(args, str):
                    args = json_repair.loads(args)

                # Prefer the original provider-assigned tool call ID (tc.id).
                # This is critical: MiniMax and other providers assign their own IDs
                # and require those exact IDs in subsequent tool result messages.
                # Fall back to a generated ID only when the provider doesn't assign one.
                raw_id = self._get_tool_field(tc, "id") or _short_tool_id()

                tool_calls.append(
                    ToolCallRequest(
                        id=raw_id,
                        name=func_name,
                        arguments=args,
                    )
                )

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        reasoning_content = getattr(message, "reasoning_content", None) or None
        thinking_blocks = getattr(message, "thinking_blocks", None) or None

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks,
        )

    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model
