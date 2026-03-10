"""Channel management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from comobot.api.deps import get_channels, get_current_user, get_db, get_vault
from comobot.channels.manager import ChannelManager
from comobot.config.loader import load_config, save_config
from comobot.db.connection import Database
from comobot.security.crypto import CredentialVault

router = APIRouter(prefix="/api/channels")

CHANNEL_TYPES = [
    "telegram",
    "discord",
    "slack",
    "feishu",
    "dingtalk",
    "email",
    "whatsapp",
    "qq",
    "matrix",
    "mochat",
]

CHANNEL_CONFIG_FIELDS: dict[str, list[dict]] = {
    "telegram": [
        {"key": "bot_token", "label": "Bot Token", "type": "secret", "required": True},
        {
            "key": "mode",
            "label": "Mode",
            "type": "select",
            "options": ["polling", "webhook"],
            "default": "polling",
        },
        {"key": "webhook_url", "label": "Webhook URL", "type": "text"},
        {"key": "allow_from", "label": "Allowed Users", "type": "tags"},
    ],
    "discord": [
        {"key": "bot_token", "label": "Bot Token", "type": "secret", "required": True},
        {"key": "guild_id", "label": "Guild ID", "type": "text"},
    ],
    "slack": [
        {"key": "bot_token", "label": "Bot Token", "type": "secret", "required": True},
        {"key": "app_token", "label": "App Token", "type": "secret"},
        {"key": "signing_secret", "label": "Signing Secret", "type": "secret"},
    ],
    "feishu": [
        {"key": "app_id", "label": "App ID", "type": "text", "required": True},
        {"key": "app_secret", "label": "App Secret", "type": "secret", "required": True},
        {"key": "allow_from", "label": "Allowed Users", "type": "tags"},
        {
            "key": "ssl_verify",
            "label": "SSL Verify",
            "type": "select",
            "options": ["true", "false"],
            "default": "true",
        },
    ],
    "dingtalk": [
        {"key": "app_key", "label": "App Key", "type": "text", "required": True},
        {"key": "app_secret", "label": "App Secret", "type": "secret", "required": True},
    ],
    "email": [
        {"key": "imap_server", "label": "IMAP Server", "type": "text", "required": True},
        {"key": "smtp_server", "label": "SMTP Server", "type": "text", "required": True},
        {"key": "email", "label": "Email", "type": "text", "required": True},
        {"key": "password", "label": "Password", "type": "secret", "required": True},
    ],
    "whatsapp": [
        {"key": "phone_number", "label": "Phone Number", "type": "text", "required": True},
    ],
    "qq": [
        {"key": "app_id", "label": "App ID", "type": "text", "required": True},
        {"key": "token", "label": "Token", "type": "secret", "required": True},
    ],
    "matrix": [
        {"key": "homeserver", "label": "Homeserver URL", "type": "text", "required": True},
        {"key": "access_token", "label": "Access Token", "type": "secret", "required": True},
    ],
    "mochat": [],
}


# Mapping: vault key -> config schema attribute (where they differ)
VAULT_TO_CONFIG_MAP: dict[str, dict[str, str]] = {
    "telegram": {"bot_token": "token"},
    "dingtalk": {"app_key": "client_id", "app_secret": "client_secret"},
    "email": {"email": "imap_username", "password": "imap_password"},
    "qq": {"token": "secret"},
    "discord": {"bot_token": "token"},
}


class ChannelConfigUpdate(BaseModel):
    config: dict[str, str | list[str]]


@router.get("")
async def list_channels(
    vault: CredentialVault = Depends(get_vault),
    _user: str = Depends(get_current_user),
):
    """List available channels with configuration status."""
    config = load_config()
    results = []
    for ch in CHANNEL_TYPES:
        configured = False
        fields = CHANNEL_CONFIG_FIELDS.get(ch, [])
        required_fields = [f["key"] for f in fields if f.get("required")]

        # Check vault first
        if required_fields:
            first_key = await vault.retrieve(ch, required_fields[0])
            configured = bool(first_key)

        # Fallback: check config.json
        if not configured:
            ch_cfg = getattr(config.channels, ch, None)
            if ch_cfg is not None:
                mapping = VAULT_TO_CONFIG_MAP.get(ch, {})
                for rk in required_fields:
                    attr = mapping.get(rk, rk)
                    if getattr(ch_cfg, attr, ""):
                        configured = True
                        break

        enabled = False
        ch_cfg = getattr(config.channels, ch, None)
        if ch_cfg is not None:
            enabled = getattr(ch_cfg, "enabled", False)

        results.append(
            {
                "name": ch,
                "type": ch,
                "configured": configured,
                "enabled": enabled,
                "status": "online" if configured else "offline",
                "fields": fields,
            }
        )
    return results


@router.post("/reload")
async def reload_channels(
    channels: ChannelManager = Depends(get_channels),
    _user: str = Depends(get_current_user),
):
    """Reload channel configuration from disk and start/stop channels as needed."""
    new_config = load_config()
    channels.config = new_config
    result = await channels.reload_channels(new_config)
    return {"reloaded": True, **result}


@router.get("/{channel_type}/config")
async def get_channel_config(
    channel_type: str,
    vault: CredentialVault = Depends(get_vault),
    _user: str = Depends(get_current_user),
):
    """Get channel config with secrets masked."""
    if channel_type not in CHANNEL_TYPES:
        raise HTTPException(status_code=404, detail="Unknown channel type")

    fields = CHANNEL_CONFIG_FIELDS.get(channel_type, [])
    app_config = load_config()
    ch_cfg = getattr(app_config.channels, channel_type, None)
    mapping = VAULT_TO_CONFIG_MAP.get(channel_type, {})

    config: dict[str, str | list[str]] = {}
    for f in fields:
        if f.get("type") == "tags":
            # List fields: read directly from config object
            if ch_cfg is not None:
                attr = mapping.get(f["key"], f["key"])
                config[f["key"]] = list(getattr(ch_cfg, attr, []) or [])
            else:
                config[f["key"]] = []
            continue
        # Select fields with boolean config attributes: read directly
        if f.get("type") == "select" and ch_cfg is not None:
            attr = mapping.get(f["key"], f["key"])
            val = getattr(ch_cfg, attr, None)
            if isinstance(val, bool):
                config[f["key"]] = "true" if val else "false"
                continue
        value = await vault.retrieve(channel_type, f["key"])
        # Fallback to config.json
        if not value and ch_cfg is not None:
            attr = mapping.get(f["key"], f["key"])
            value = str(getattr(ch_cfg, attr, "") or "")
        if value and f.get("type") == "secret":
            config[f["key"]] = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
        else:
            config[f["key"]] = value or ""
    return {"type": channel_type, "config": config, "fields": fields}


@router.put("/{channel_type}/config")
async def update_channel_config(
    channel_type: str,
    body: ChannelConfigUpdate,
    vault: CredentialVault = Depends(get_vault),
    channels: ChannelManager = Depends(get_channels),
    _user: str = Depends(get_current_user),
):
    """Update channel configuration."""
    if channel_type not in CHANNEL_TYPES:
        raise HTTPException(status_code=404, detail="Unknown channel type")

    app_config = load_config()
    ch_cfg = getattr(app_config.channels, channel_type, None)
    mapping = VAULT_TO_CONFIG_MAP.get(channel_type, {})
    config_changed = False

    fields = CHANNEL_CONFIG_FIELDS.get(channel_type, [])
    field_types = {f["key"]: f.get("type") for f in fields}

    for key, value in body.config.items():
        # Handle list (tags) fields directly on config object
        if field_types.get(key) == "tags":
            if ch_cfg is not None:
                attr = mapping.get(key, key)
                if hasattr(ch_cfg, attr):
                    setattr(ch_cfg, attr, value if isinstance(value, list) else [])
                    config_changed = True
            continue
        # Handle select fields with boolean config attributes
        if field_types.get(key) == "select" and ch_cfg is not None:
            attr = mapping.get(key, key)
            if hasattr(ch_cfg, attr) and isinstance(getattr(ch_cfg, attr), bool):
                setattr(ch_cfg, attr, str(value).lower() == "true")
                config_changed = True
                continue
        if value and "****" not in str(value):
            await vault.store(channel_type, key, str(value))
            # Sync to config.json
            if ch_cfg is not None:
                attr = mapping.get(key, key)
                if hasattr(ch_cfg, attr):
                    setattr(ch_cfg, attr, str(value))
                    config_changed = True

    # Auto-enable channel when configured via UI
    if config_changed and ch_cfg is not None:
        ch_cfg.enabled = True
        save_config(app_config)

        # Auto-reload: start the channel if not already running
        was_running = channel_type in channels.channels
        channels.config = app_config
        if not was_running:
            await channels.start_channel(channel_type)

    return {"updated": True, "type": channel_type}


@router.post("/{channel_type}/test")
async def test_channel(
    channel_type: str,
    vault: CredentialVault = Depends(get_vault),
    _user: str = Depends(get_current_user),
):
    """Test channel connectivity."""
    if channel_type not in CHANNEL_TYPES:
        raise HTTPException(status_code=404, detail="Unknown channel type")

    fields = CHANNEL_CONFIG_FIELDS.get(channel_type, [])
    required = [f["key"] for f in fields if f.get("required")]
    for key in required:
        val = await vault.retrieve(channel_type, key)
        if not val:
            raise HTTPException(status_code=400, detail=f"Missing required field: {key}")

    return {"type": channel_type, "status": "ok", "message": "Configuration valid"}


@router.get("/allowed-users")
async def list_allowed_users(
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    return await db.fetchall("SELECT * FROM allowed_users ORDER BY channel, user_id")


@router.post("/allowed-users")
async def add_allowed_user(
    channel: str,
    user_id: str,
    alias: str | None = None,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    await db.execute(
        "INSERT OR REPLACE INTO allowed_users (channel, user_id, alias) VALUES (?, ?, ?)",
        (channel, user_id, alias),
    )
    return {"added": True}


@router.delete("/allowed-users/{channel}/{user_id}")
async def remove_allowed_user(
    channel: str,
    user_id: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    await db.execute(
        "DELETE FROM allowed_users WHERE channel = ? AND user_id = ?",
        (channel, user_id),
    )
    return {"deleted": True}
