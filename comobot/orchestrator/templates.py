"""Preset workflow templates for comobot orchestrator."""

from __future__ import annotations

from typing import Any

TEMPLATES: dict[str, dict[str, Any]] = {
    "smart_customer_service": {
        "name": "Smart Customer Service",
        "description": "Receive user message -> LLM answer -> Reply to user",
        "params": [
            {
                "key": "system_prompt",
                "label": "System Prompt",
                "type": "textarea",
                "default": "You are a helpful customer service assistant.",
            },
            {"key": "model", "label": "Model", "type": "text", "default": ""},
        ],
        "build": lambda p: {
            "nodes": [
                {"id": "trigger", "type": "trigger", "data": {"trigger_type": "message"}},
                {
                    "id": "llm",
                    "type": "llm_call",
                    "data": {
                        "system_prompt": p.get("system_prompt", ""),
                        "model": p.get("model"),
                        "user_message": "{{trigger.message}}",
                    },
                },
                {
                    "id": "reply",
                    "type": "response",
                    "data": {
                        "content": "{{llm.response}}",
                        "channel": "{{trigger.channel}}",
                        "chat_id": "{{trigger.chat_id}}",
                    },
                },
            ],
            "edges": [
                {"source": "trigger", "target": "llm"},
                {"source": "llm", "target": "reply"},
            ],
        },
    },
    "scheduled_summary": {
        "name": "Scheduled Summary",
        "description": "Cron trigger -> Fetch URL -> LLM summarize -> Push to channel",
        "params": [
            {"key": "url", "label": "URL to summarize", "type": "text", "default": ""},
            {
                "key": "cron_expr",
                "label": "Cron Expression",
                "type": "text",
                "default": "0 9 * * *",
            },
            {"key": "channel", "label": "Target Channel", "type": "text", "default": "telegram"},
            {"key": "chat_id", "label": "Target Chat ID", "type": "text", "default": ""},
        ],
        "build": lambda p: {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "trigger",
                    "data": {
                        "trigger_type": "cron",
                        "cron_expr": p.get("cron_expr", "0 9 * * *"),
                    },
                },
                {
                    "id": "fetch",
                    "type": "tool",
                    "data": {
                        "tool_type": "http_request",
                        "url": p.get("url", ""),
                        "method": "GET",
                    },
                },
                {
                    "id": "llm",
                    "type": "llm_call",
                    "data": {
                        "system_prompt": "Summarize the following content concisely.",
                        "user_message": "{{tool.result}}",
                    },
                },
                {
                    "id": "reply",
                    "type": "response",
                    "data": {
                        "content": "{{llm.response}}",
                        "channel": p.get("channel", "telegram"),
                        "chat_id": p.get("chat_id", ""),
                    },
                },
            ],
            "edges": [
                {"source": "trigger", "target": "fetch"},
                {"source": "fetch", "target": "llm"},
                {"source": "llm", "target": "reply"},
            ],
        },
    },
    "message_forwarder": {
        "name": "Message Forwarder",
        "description": "Receive message -> Match condition -> Forward to target channel",
        "params": [
            {
                "key": "keywords",
                "label": "Match Keywords (comma separated)",
                "type": "text",
                "default": "",
            },
            {
                "key": "target_channel",
                "label": "Target Channel",
                "type": "text",
                "default": "telegram",
            },
            {"key": "target_chat_id", "label": "Target Chat ID", "type": "text", "default": ""},
        ],
        "build": lambda p: {
            "nodes": [
                {"id": "trigger", "type": "trigger", "data": {"trigger_type": "message"}},
                {
                    "id": "forward",
                    "type": "response",
                    "data": {
                        "content": "[Forwarded] {{trigger.message}}",
                        "channel": p.get("target_channel", "telegram"),
                        "chat_id": p.get("target_chat_id", ""),
                    },
                },
            ],
            "edges": [
                {"source": "trigger", "target": "forward"},
            ],
        },
    },
    "document_assistant": {
        "name": "Document Assistant",
        "description": "Receive file -> Parse content -> LLM analyze -> Reply",
        "params": [
            {
                "key": "analysis_prompt",
                "label": "Analysis Prompt",
                "type": "textarea",
                "default": "Analyze the following document and provide key insights.",
            },
        ],
        "build": lambda p: {
            "nodes": [
                {"id": "trigger", "type": "trigger", "data": {"trigger_type": "message"}},
                {
                    "id": "llm",
                    "type": "llm_call",
                    "data": {
                        "system_prompt": p.get("analysis_prompt", ""),
                        "user_message": "{{trigger.message}}",
                    },
                },
                {
                    "id": "reply",
                    "type": "response",
                    "data": {
                        "content": "{{llm.response}}",
                        "channel": "{{trigger.channel}}",
                        "chat_id": "{{trigger.chat_id}}",
                    },
                },
            ],
            "edges": [
                {"source": "trigger", "target": "llm"},
                {"source": "llm", "target": "reply"},
            ],
        },
    },
}


def list_templates() -> list[dict]:
    """Return template metadata (without build functions)."""
    result = []
    for key, tpl in TEMPLATES.items():
        result.append(
            {
                "id": key,
                "name": tpl["name"],
                "description": tpl["description"],
                "params": tpl["params"],
            }
        )
    return result


def build_from_template(template_id: str, params: dict) -> dict:
    """Build a workflow definition from a template with given parameters."""
    tpl = TEMPLATES.get(template_id)
    if not tpl:
        raise ValueError(f"Template '{template_id}' not found")
    return tpl["build"](params)
