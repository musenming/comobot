"""OpenClaw agent discovery and protocol endpoints.

The openclaw-weixin plugin calls GET /.well-known/openclaw to auto-discover
comobot as an OpenClaw-compatible agent before establishing the WeChat bridge.
"""

from __future__ import annotations

import importlib.metadata

from fastapi import APIRouter, Request
from loguru import logger

router = APIRouter()


def _agent_version() -> str:
    try:
        return importlib.metadata.version("comobot")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


@router.get("/.well-known/openclaw")
async def openclaw_manifest(request: Request):
    """
    OpenClaw agent discovery manifest.

    The openclaw-weixin plugin sends a GET to this endpoint to verify that the
    local process is an OpenClaw-compatible agent and to retrieve connection details.

    Returns a manifest understood by openclaw plugin ecosystem:
      - type        : always "agent"
      - name        : human-readable agent name
      - version     : comobot package version
      - vendor      : "comobot"
      - capabilities: list of supported features
      - webhook     : URL where the plugin should POST inbound WeChat messages
      - openclaw_version: protocol version (semver)
    """
    base_url = str(request.base_url).rstrip("/")
    config = getattr(request.app.state, "config", None)
    agent_name = getattr(config, "assistant_name", "Comobot") if config else "Comobot"

    wechat_cfg = None
    if config and hasattr(config, "channels"):
        wechat_cfg = getattr(config.channels, "wechat", None)

    manifest = {
        "type": "agent",
        "name": agent_name,
        "vendor": "comobot",
        "version": _agent_version(),
        "openclaw_version": "1.0",
        "capabilities": ["text", "image", "group"],
        "webhook": f"{base_url}/webhook/wechat",
        "status": "ready" if (wechat_cfg and wechat_cfg.enabled) else "disabled",
    }

    logger.debug("OpenClaw discovery request from {}", request.client)
    return manifest


@router.get("/.well-known/openclaw/health")
async def openclaw_health(request: Request):
    """Lightweight liveness probe for the openclaw-weixin plugin."""
    config = getattr(request.app.state, "config", None)
    wechat_cfg = None
    if config and hasattr(config, "channels"):
        wechat_cfg = getattr(config.channels, "wechat", None)
    enabled = bool(wechat_cfg and wechat_cfg.enabled)
    return {"ok": True, "wechat_enabled": enabled}
