"""REST API routes for Comobot Remote — device pairing and management."""

from __future__ import annotations

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


# --- Pairing Endpoints ---


@router.post("/pair", response_model=PairResponse)
async def generate_pair_token(
    request: Request,
    _user: str = Depends(get_current_user),
    dm: DeviceManager = Depends(get_device_manager),
):
    """Generate a QR pairing token. Requires admin auth."""
    # Build server URL from request so the mobile app knows where to connect
    server_url = str(request.base_url).rstrip("/")
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
