"""REST API routes for Comobot Remote — device pairing and management."""

from __future__ import annotations

import socket
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from comobot.api.deps import get_current_device, get_current_user, get_device_manager
from comobot.api.remote.device_manager import DeviceManager
from comobot.api.remote.intent_engine import IntentEngine

router = APIRouter(prefix="/api/remote", tags=["remote"])


# --- Request / Response Models ---


class PairConfirmRequest(BaseModel):
    qr_token: str
    device_public_key: str  # Base64 X25519 public key
    device_name: str
    device_os: str  # 'ios' | 'android'


class PairResponse(BaseModel):
    qr_token: str
    server_public_key: str
    expires_at: str
    qr_data: str  # JSON string for QR code


class PairConfirmResponse(BaseModel):
    access_token: str
    refresh_token: str
    device_id: str
    server_public_key: str


class PushTokenRequest(BaseModel):
    push_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class VoiceIntentRequest(BaseModel):
    transcript: str
    context: dict | None = None


class VoiceSettingsRequest(BaseModel):
    language: str = "zh"
    sensitivity: int = 70
    auto_downfreq: bool = True
    filter_chat: bool = True
    custom_keywords: list[str] = []
    default_agent: str = "auto"
    confirm_threshold: float = 0.8
    history_retention_days: int = 30


# --- Helpers ---

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _get_lan_ip() -> str | None:
    """Return the machine's LAN IP by opening a UDP socket (no traffic sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def _resolve_server_url(request: Request) -> str:
    """Derive a server URL reachable from the local network.

    If the request arrived via a loopback address (localhost / 127.0.0.1),
    replace the host with the machine's LAN IP so the mobile app can connect.
    """
    base = str(request.base_url).rstrip("/")
    parsed = urlparse(base)
    host = parsed.hostname or ""
    if host in _LOOPBACK:
        lan_ip = _get_lan_ip()
        if lan_ip:
            # Rebuild netloc preserving the port
            port = parsed.port
            netloc = f"{lan_ip}:{port}" if port else lan_ip
            parsed = parsed._replace(netloc=netloc)
            return urlunparse(parsed)
    return base


# --- Pairing Endpoints ---


@router.post("/pair", response_model=PairResponse)
async def generate_pair_token(
    request: Request,
    _user: str = Depends(get_current_user),
    dm: DeviceManager = Depends(get_device_manager),
):
    """Generate a QR pairing token. Requires admin auth."""
    # Build server URL from request, replacing loopback addresses with a LAN IP
    # so the mobile app on the same network can reach the server.
    server_url = _resolve_server_url(request)
    result = await dm.create_pairing_token(server_url=server_url)
    return PairResponse(**result)


@router.post("/pair/confirm", response_model=PairConfirmResponse)
async def confirm_pair(
    body: PairConfirmRequest,
    dm: DeviceManager = Depends(get_device_manager),
):
    """Mobile confirms pairing via QR token. No auth required (token-based)."""
    result = await dm.confirm_pairing(
        token=body.qr_token,
        device_public_key=body.device_public_key,
        device_name=body.device_name,
        device_os=body.device_os,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already used pairing token",
        )
    return PairConfirmResponse(**result)


# --- Dev-only Pairing (skips QR, no admin auth) ---


@router.post("/pair/dev", response_model=PairConfirmResponse)
async def dev_pair(
    request: Request,
    dm: DeviceManager = Depends(get_device_manager),
):
    """Create a device and issue tokens in one step. Dev/testing only.

    Only available when COMOBOT_DEV_MODE=1 is set.
    """
    import os

    if not os.environ.get("COMOBOT_DEV_MODE"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev pairing is disabled in production",
        )

    from comobot.security.nacl_crypto import generate_keypair

    # Accept device public key from mobile, or generate one (for CLI testing)
    body = (
        await request.json()
        if request.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    device_pub_key = body.get("device_public_key")

    # Generate server keypair
    server_kp = generate_keypair()

    # If mobile didn't send a public key, generate a throwaway one
    if not device_pub_key:
        device_pub_key = generate_keypair().public_key_b64

    device_id = __import__("uuid").uuid4().hex
    await dm.db.execute(
        "INSERT INTO remote_devices "
        "(id, device_name, device_os, device_public_key, server_public_key, server_secret_key) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            device_id,
            "DevSimulator",
            "ios",
            device_pub_key,
            server_kp.public_key_b64,
            server_kp.secret_key_b64,
        ),
    )

    access_token = dm.auth.create_device_token(device_id)
    refresh_token = dm.auth.create_refresh_token(device_id)

    return PairConfirmResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        device_id=device_id,
        server_public_key=server_kp.public_key_b64,
    )


# --- Device Management ---


@router.get("/devices")
async def list_devices(
    _user: str = Depends(get_current_user),
    dm: DeviceManager = Depends(get_device_manager),
):
    """List all paired devices. Requires admin auth."""
    devices = await dm.list_devices()
    return {"devices": devices}


@router.delete("/devices/{device_id}")
async def remove_device(
    device_id: str,
    _user: str = Depends(get_current_user),
    dm: DeviceManager = Depends(get_device_manager),
):
    """Unbind (deactivate) a paired device. Requires admin auth."""
    removed = await dm.remove_device(device_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "ok"}


@router.post("/devices/{device_id}/push-token")
async def register_push_token(
    device_id: str,
    body: PushTokenRequest,
    device: dict = Depends(get_current_device),
    dm: DeviceManager = Depends(get_device_manager),
):
    """Register push notification token for a device. Requires device auth."""
    if device["device_id"] != device_id:
        raise HTTPException(status_code=403, detail="Cannot update another device's push token")
    updated = await dm.update_push_token(device_id, body.push_token)
    if not updated:
        raise HTTPException(status_code=404, detail="Device not found or inactive")
    return {"status": "ok"}


@router.post("/auth/refresh")
async def refresh_device_token(
    body: RefreshRequest,
    dm: DeviceManager = Depends(get_device_manager),
):
    """Refresh a device access token using a refresh token."""
    payload = dm.auth.verify_device_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    result = await dm.refresh_device_token(payload["device_id"])
    if not result:
        raise HTTPException(status_code=401, detail="Device not found or inactive")
    return result


# --- Voice Intent Endpoints ---


def _get_intent_engine(request: Request) -> IntentEngine:
    engine = getattr(request.app.state, "intent_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intent engine not available",
        )
    return engine


@router.post("/voice/intent")
async def submit_voice_intent(
    body: VoiceIntentRequest,
    request: Request,
    device: dict = Depends(get_current_device),
):
    """Submit a voice intent from the mobile app. Requires device auth."""
    engine: IntentEngine = _get_intent_engine(request)
    result = await engine.submit_intent(
        device_id=device["device_id"],
        transcript=body.transcript,
        context=body.context,
    )
    return result


@router.get("/voice/history")
async def voice_intent_history(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    device: dict = Depends(get_current_device),
):
    """Get voice intent capture history for the requesting device."""
    engine: IntentEngine = _get_intent_engine(request)
    intents = await engine.list_intents(
        device_id=device["device_id"],
        limit=limit,
        offset=offset,
    )
    return {"intents": intents}


@router.get("/voice/intents/{intent_id}")
async def get_voice_intent(
    intent_id: str,
    request: Request,
    device: dict = Depends(get_current_device),
):
    """Get a single intent detail with execution status."""
    engine: IntentEngine = _get_intent_engine(request)
    intent = await engine.get_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    if intent["device_id"] != device["device_id"]:
        raise HTTPException(status_code=403, detail="Not your intent")
    return intent


@router.delete("/voice/intents/{intent_id}")
async def delete_voice_intent(
    intent_id: str,
    request: Request,
    device: dict = Depends(get_current_device),
):
    """Cancel or delete a voice intent."""
    engine: IntentEngine = _get_intent_engine(request)
    intent = await engine.get_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    if intent["device_id"] != device["device_id"]:
        raise HTTPException(status_code=403, detail="Not your intent")

    if intent["status"] in ("pending", "processing"):
        await engine.cancel_intent(intent_id)
        return {"status": "cancelled"}
    else:
        await engine.delete_intent(intent_id)
        return {"status": "deleted"}


@router.post("/voice/settings")
async def update_voice_settings(
    body: VoiceSettingsRequest,
    device: dict = Depends(get_current_device),
):
    """Update voice hub configuration. Settings stored on device side."""
    # Settings are primarily stored on the mobile device.
    # This endpoint validates and acknowledges the settings.
    return {"status": "ok", "settings": body.model_dump()}


# ---------------------------------------------------------------------------
# Session endpoints (device auth — lightweight for mobile)
# ---------------------------------------------------------------------------


def _extract_title(row: dict) -> str:
    """Derive a human-readable title from a session_key ('channel:chat_id')."""
    key = row.get("session_key", "")
    parts = key.split(":", 1)
    return parts[1][:30] if len(parts) == 2 else key[:30]


@router.get("/sessions")
async def list_remote_sessions(
    request: Request,
    device: dict = Depends(get_current_device),
    limit: int = 50,
    offset: int = 0,
):
    """List sessions with lightweight metadata (no message bodies)."""
    db = request.app.state.db
    rows = await db.fetchall(
        "SELECT s.id, s.session_key, s.platform, s.created_at, s.updated_at, "
        "  (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count, "
        "  (SELECT m2.content FROM messages m2 WHERE m2.session_id = s.id "
        "   ORDER BY m2.id DESC LIMIT 1) AS last_message "
        "FROM sessions s ORDER BY s.updated_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return {
        "sessions": [
            {
                "session_key": r["session_key"],
                "platform": r["platform"],
                "title": _extract_title(r),
                "summary": r["last_message"][:100] if r["last_message"] else None,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "message_count": r["message_count"],
            }
            for r in rows
        ]
    }


@router.get("/sessions/{session_key:path}/messages")
async def get_remote_session_messages(
    session_key: str,
    request: Request,
    device: dict = Depends(get_current_device),
    cursor: int | None = None,
    limit: int = 30,
):
    """Cursor-based paginated messages for a session.

    *cursor* is a message.id — returns messages with id < cursor (older).
    Omit cursor to get the most recent messages.
    """
    db = request.app.state.db
    session = await db.fetchone("SELECT id FROM sessions WHERE session_key = ?", (session_key,))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_id = session["id"]

    if cursor:
        rows = await db.fetchall(
            "SELECT id, role, content, tool_calls, tool_call_id, created_at "
            "FROM messages WHERE session_id = ? AND id < ? ORDER BY id DESC LIMIT ?",
            (session_id, cursor, limit),
        )
    else:
        rows = await db.fetchall(
            "SELECT id, role, content, tool_calls, tool_call_id, created_at "
            "FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )

    rows.reverse()  # chronological order
    has_more = len(rows) == limit
    next_cursor = rows[0]["id"] if has_more and rows else None

    return {"messages": rows, "has_more": has_more, "next_cursor": next_cursor}
