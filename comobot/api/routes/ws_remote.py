"""Dedicated WebSocket endpoint for Comobot Remote mobile devices."""

from __future__ import annotations

import base64

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from comobot.api.remote.ws_manager import RemoteConnectionManager
from comobot.security.nacl_crypto import compute_shared_key

router = APIRouter()

# Global remote connection manager instance
remote_manager = RemoteConnectionManager()


def get_remote_manager() -> RemoteConnectionManager:
    """Get the global RemoteConnectionManager instance."""
    return remote_manager


@router.websocket("/ws/remote")
async def ws_remote(websocket: WebSocket):
    """Dedicated mobile WebSocket endpoint with encrypted transport.

    Auth: JWT token in query param (?token=...)
    After auth, all messages are NaCl-encrypted via the shared key from pairing.

    Commands:
      - subscribe(session_key)    — subscribe to real-time session updates
      - unsubscribe(session_key)  — unsubscribe from session
      - send_message(session_key, content) — send message to a session
      - agent_command(agent_id, command)   — pause/resume agent
      - voice_intent(transcript, context)  — submit voice intent
      - intervene(session_key, action, content) — descend mode intervention
      - sync(last_seq)            — reconnection sync
      - ping                      — keepalive
    """
    # --- Auth phase ---
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    app = websocket.app
    auth = app.state.auth
    payload = auth.verify_device_token(token)
    if not payload or payload.get("type") != "device":
        await websocket.close(code=4001, reason="Invalid token")
        return

    device_id = payload["device_id"]

    # --- Look up device and compute shared key ---
    dm = getattr(app.state, "device_manager", None)
    if not dm:
        await websocket.close(code=4003, reason="Service unavailable")
        return

    device = await dm.get_device(device_id)
    if not device or not device["is_active"]:
        await websocket.close(code=4001, reason="Device not found or inactive")
        return

    try:
        shared_key = compute_shared_key(
            our_secret=base64.b64decode(device["server_secret_key"]),
            their_public=base64.b64decode(device["device_public_key"]),
        )
    except Exception as e:
        logger.error("Failed to compute shared key for device {}: {}", device_id, e)
        await websocket.close(code=4002, reason="Encryption error")
        return

    # --- Establish encrypted connection ---
    conn = await remote_manager.connect(device_id, websocket, shared_key)
    await dm.touch_device(device_id)

    # Send welcome message
    await remote_manager.send_encrypted(
        device_id,
        {
            "t": "welcome",
            "device_id": device_id,
            "server_version": "1.0",
        },
    )

    try:
        while True:
            msg = await remote_manager.receive_decrypted(conn)
            if msg is None:
                break
            await _handle_command(app, device_id, msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WS error for device {}: {}", device_id, e)
    finally:
        remote_manager.disconnect(device_id)


async def _handle_command(app, device_id: str, msg: dict) -> None:
    """Route a decrypted command from a mobile device."""
    cmd = msg.get("cmd")
    if not cmd:
        return

    if cmd == "ping":
        await remote_manager.send_encrypted(device_id, {"t": "pong"})

    elif cmd == "subscribe":
        session_key = msg.get("session_key")
        if session_key:
            remote_manager.subscribe(device_id, session_key)
            # Fetch recent messages for the session
            db = app.state.db
            session = await db.fetchone(
                "SELECT id FROM sessions WHERE session_key = ?", (session_key,)
            )
            if session:
                messages = await db.fetchall(
                    "SELECT id, role, content, tool_calls, created_at "
                    "FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 50",
                    (session["id"],),
                )
                messages.reverse()
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "subscribed",
                        "session_key": session_key,
                        "messages": messages,
                    },
                )
            else:
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "error",
                        "detail": f"Session not found: {session_key}",
                    },
                )

    elif cmd == "unsubscribe":
        session_key = msg.get("session_key")
        if session_key:
            remote_manager.unsubscribe(device_id, session_key)
            await remote_manager.send_encrypted(
                device_id,
                {
                    "t": "unsubscribed",
                    "session_key": session_key,
                },
            )

    elif cmd == "send_message":
        session_key = msg.get("session_key")
        content = msg.get("content")
        if session_key and content:
            # Inject message via the message bus if available
            bus = getattr(app.state, "bus", None)
            if bus:
                from comobot.bus import InboundMessage

                await bus.publish(
                    InboundMessage(
                        session_key=session_key,
                        text=content,
                        sender="remote",
                        channel="mobile",
                    )
                )
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "message_sent",
                        "session_key": session_key,
                    },
                )
            else:
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "error",
                        "detail": "Message bus not available",
                    },
                )

    elif cmd == "voice_intent":
        transcript = msg.get("transcript")
        context = msg.get("context")
        if transcript:
            intent_engine = getattr(app.state, "intent_engine", None)
            if intent_engine:
                result = await intent_engine.submit_intent(device_id, transcript, context)
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "intent_submitted",
                        **result,
                    },
                )
            else:
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "error",
                        "detail": "Intent engine not available",
                    },
                )

    elif cmd == "agent_command":
        agent_id = msg.get("agent_id")
        command = msg.get("command")  # "pause" | "resume"
        if agent_id and command:
            # Delegate to agent management (to be expanded)
            await remote_manager.send_encrypted(
                device_id,
                {
                    "t": "agent_command_ack",
                    "agent_id": agent_id,
                    "command": command,
                    "status": "ok",
                },
            )

    elif cmd == "intervene":
        session_key = msg.get("session_key")
        action = msg.get("action")  # "approve" | "edit" | "reject"
        content = msg.get("content")
        if session_key and action:
            # Look for intervention callback on the agent loop
            agent = getattr(app.state, "agent", None)
            if agent and hasattr(agent, "register_intervention_response"):
                agent.register_intervention_response(session_key, action, content or "")
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "intervene_ack",
                        "session_key": session_key,
                        "action": action,
                    },
                )

    elif cmd == "sync":
        last_seq = msg.get("last_seq", 0)
        await remote_manager.send_encrypted(
            device_id,
            {
                "t": "sync_ack",
                "last_seq": last_seq,
                "status": "ok",
            },
        )

    else:
        await remote_manager.send_encrypted(
            device_id,
            {
                "t": "error",
                "detail": f"Unknown command: {cmd}",
            },
        )
