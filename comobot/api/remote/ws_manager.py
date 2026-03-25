"""Encrypted WebSocket connection manager for Comobot Remote devices."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from fastapi import WebSocket
from loguru import logger

from comobot.security.nacl_crypto import decrypt_json, encrypt_json


@dataclass
class RemoteConnection:
    """A single encrypted WebSocket connection from a mobile device."""

    ws: WebSocket
    device_id: str
    shared_key: bytes
    subscriptions: set[str] = field(default_factory=set)
    seq: int = 0


class RemoteConnectionManager:
    """Manages encrypted WebSocket connections from paired mobile devices."""

    def __init__(self):
        self.connections: dict[str, RemoteConnection] = {}

    async def connect(
        self, device_id: str, ws: WebSocket, shared_key: bytes
    ) -> RemoteConnection:
        """Accept and register an encrypted WS connection."""
        await ws.accept()
        conn = RemoteConnection(ws=ws, device_id=device_id, shared_key=shared_key)
        # Close existing connection for same device (reconnect scenario)
        if device_id in self.connections:
            try:
                await self.connections[device_id].ws.close()
            except Exception:
                pass
        self.connections[device_id] = conn
        logger.info("Remote device connected: {}", device_id)
        return conn

    def disconnect(self, device_id: str) -> None:
        """Remove a device connection."""
        if device_id in self.connections:
            del self.connections[device_id]
            logger.info("Remote device disconnected: {}", device_id)

    async def send_encrypted(self, device_id: str, payload: dict) -> bool:
        """Encrypt and send a JSON payload to a specific device.

        Returns True if sent successfully, False otherwise.
        """
        conn = self.connections.get(device_id)
        if not conn:
            return False
        try:
            conn.seq += 1
            envelope = {
                "id": f"srv_{conn.seq}_{int(time.time())}",
                "seq": conn.seq,
                "t": "encrypted",
                "c": encrypt_json(payload, conn.shared_key),
                "ts": int(time.time() * 1000),
            }
            await conn.ws.send_json(envelope)
            return True
        except Exception as e:
            logger.warning("Failed to send to device {}: {}", device_id, e)
            self.disconnect(device_id)
            return False

    async def receive_decrypted(self, conn: RemoteConnection) -> dict | None:
        """Receive and decrypt a JSON message from a device.

        Returns the decrypted payload dict, or None on error.
        """
        try:
            raw = await conn.ws.receive_text()
            envelope = json.loads(raw)
            if envelope.get("t") == "encrypted":
                return decrypt_json(envelope["c"], conn.shared_key)
            # Allow plaintext ping/pong
            return envelope
        except Exception as e:
            logger.warning("Failed to receive from device {}: {}", conn.device_id, e)
            return None

    async def broadcast_to_subscribers(self, session_key: str, data: dict) -> None:
        """Send data to all devices subscribed to a given session_key."""
        for device_id, conn in list(self.connections.items()):
            if session_key in conn.subscriptions:
                await self.send_encrypted(device_id, data)

    async def broadcast_to_all(self, data: dict) -> None:
        """Broadcast data to all connected devices."""
        for device_id in list(self.connections):
            await self.send_encrypted(device_id, data)

    def subscribe(self, device_id: str, session_key: str) -> None:
        """Subscribe a device to session updates."""
        conn = self.connections.get(device_id)
        if conn:
            conn.subscriptions.add(session_key)
            logger.debug("Device {} subscribed to {}", device_id, session_key)

    def unsubscribe(self, device_id: str, session_key: str) -> None:
        """Unsubscribe a device from session updates."""
        conn = self.connections.get(device_id)
        if conn:
            conn.subscriptions.discard(session_key)

    def get_subscriptions(self, device_id: str) -> set[str]:
        """Get session_keys a device is subscribed to."""
        conn = self.connections.get(device_id)
        return conn.subscriptions if conn else set()

    @property
    def connected_count(self) -> int:
        return len(self.connections)
