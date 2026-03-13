"""LLM-based Know-how extraction from conversation fragments."""

from __future__ import annotations

import json

from loguru import logger

EXTRACT_SYSTEM_PROMPT = """你是知识提取助手。请根据以下对话片段生成结构化摘要，以 JSON 格式返回：
{
  "title": "简短标题（≤20字）",
  "goal": "用户想达成什么",
  "steps": ["关键步骤1", "关键步骤2", ...],
  "tools_used": ["工具名1", ...],
  "outcome": "最终结果",
  "tags": ["标签1", "标签2"]
}

要求：
- title 简洁准确，不超过20字
- steps 按时间顺序列出关键操作步骤
- tools_used 列出对话中使用的工具名称（如有）
- tags 给出 2-5 个分类标签
- 只返回 JSON，不要其他文字
"""


async def extract_knowhow(
    messages: list[dict],
) -> dict:
    """Call LLM to extract structured Know-how summary from conversation fragments.

    Uses the same provider/model configuration as the agent (from config.json),
    including model prefix resolution, api_key, api_base, and extra_headers.

    Args:
        messages: Selected raw conversation messages.

    Returns:
        Parsed dict with title/goal/steps/tools_used/outcome/tags.
    """
    from litellm import acompletion

    from comobot.config.loader import load_config
    from comobot.providers.litellm_provider import LiteLLMProvider

    config = load_config()
    model = config.agents.defaults.model or "gpt-4o-mini"
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # Build a provider instance to resolve model prefix (e.g. "openai/MiniMax-M2.5")
    # and set up environment variables for litellm
    provider = LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )
    resolved_model = provider._resolve_model(model)

    conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages if m.get("content"))

    kwargs: dict = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": f"对话片段：\n{conversation}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }

    if provider.api_key:
        kwargs["api_key"] = provider.api_key
    if provider.api_base:
        kwargs["api_base"] = provider.api_base
    if provider.extra_headers:
        kwargs["extra_headers"] = provider.extra_headers

    resp = await acompletion(**kwargs)

    raw = resp.choices[0].message.content
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse LLM extraction response: {}", str(raw)[:200])
        result = {
            "title": "未命名经验",
            "goal": "",
            "steps": [],
            "tools_used": [],
            "outcome": "",
            "tags": [],
        }

    # Ensure all required fields exist
    for key in ("title", "goal", "steps", "tools_used", "outcome", "tags"):
        result.setdefault(key, [] if key in ("steps", "tools_used", "tags") else "")

    return result
