"""Encrypted WebSocket connection manager for Comobot Remote devices."""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import WebSocket
from loguru import logger

from comobot.security.nacl_crypto import decrypt_json, encrypt_json

# --- Constants ---
HEARTBEAT_INTERVAL = 30  # seconds — server sends ping if idle this long
HEARTBEAT_TIMEOUT = 45  # seconds — disconnect if no message received within this
OUTBOX_MAX_SIZE = 100  # max messages to buffer per device
OUTBOX_TTL = 300  # seconds — drop outbox entries older than this


@dataclass
class OutboxEntry:
    """A buffered message for replay on reconnect."""

    seq: int
    payload: dict
    envelope: dict  # the full encrypted envelope as sent
    created_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > OUTBOX_TTL


@dataclass
class RemoteConnection:
    """A single encrypted WebSocket connection from a mobile device."""

    ws: WebSocket
    device_id: str
    shared_key: bytes
    subscriptions: set[str] = field(default_factory=set)
    seq: int = 0
    last_message_at: float = field(default_factory=time.time)


class RemoteConnectionManager:
    """Manages encrypted WebSocket connections from paired mobile devices."""

    def __init__(self):
        self.connections: dict[str, RemoteConnection] = {}
        # Per-device outbox for message replay on reconnect
        self._outboxes: dict[str, deque[OutboxEntry]] = {}

    async def connect(self, device_id: str, ws: WebSocket, shared_key: bytes) -> RemoteConnection:
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

    def disconnect(self, device_id: str, conn: RemoteConnection | None = None) -> None:
        """Remove a device connection.

        If *conn* is provided, only remove if it matches the current connection
        for this device. This prevents a stale handler from removing a newer
        reconnected connection (race condition on fast reconnect).
        """
        current = self.connections.get(device_id)
        if current is None:
            return
        if conn is not None and current is not conn:
            logger.debug(
                "Skipping disconnect for device {} — connection already replaced",
                device_id,
            )
            return
        del self.connections[device_id]
        logger.info("Remote device disconnected: {}", device_id)

    def touch(self, device_id: str) -> None:
        """Update last_message_at timestamp for a device (heartbeat tracking)."""
        conn = self.connections.get(device_id)
        if conn:
            conn.last_message_at = time.time()

    def seconds_since_last_message(self, device_id: str) -> float:
        """Return seconds since the last message was received from this device."""
        conn = self.connections.get(device_id)
        if not conn:
            return float("inf")
        return time.time() - conn.last_message_at

    async def send_encrypted(self, device_id: str, payload: dict, *, track: bool = True) -> bool:
        """Encrypt and send a JSON payload to a specific device.

        Args:
            device_id: Target device.
            payload: JSON-serializable dict to encrypt and send.
            track: If True, store the message in the outbox for replay on reconnect.
                   Set to False for ephemeral messages like pong/heartbeat.

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

            # Store in outbox for replay (skip ephemeral messages)
            if track:
                self._outbox_append(device_id, conn.seq, payload, envelope)

            return True
        except Exception as e:
            logger.warning("Failed to send to device {}: {}", device_id, e)
            self.disconnect(device_id)
            return False

    async def send_raw(self, device_id: str, data: dict) -> bool:
        """Send a plaintext (unencrypted) JSON message. Used for pong/heartbeat."""
        conn = self.connections.get(device_id)
        if not conn:
            return False
        try:
            await conn.ws.send_json(data)
            return True
        except Exception as e:
            logger.warning("Failed to send raw to device {}: {}", device_id, e)
            self.disconnect(device_id)
            return False

    async def receive_decrypted(self, conn: RemoteConnection) -> dict | None:
        """Receive and decrypt a JSON message from a device.

        Returns the decrypted payload dict, or None on error.
        """
        try:
            raw = await conn.ws.receive_text()
            envelope = json.loads(raw)
            # Update heartbeat timestamp on any received message
            conn.last_message_at = time.time()
            if envelope.get("t") == "encrypted":
                return decrypt_json(envelope["c"], conn.shared_key)
            # Allow plaintext ping/pong
            return envelope
        except Exception as e:
            logger.warning("Failed to receive from device {}: {}", conn.device_id, e)
            return None

    # --- Outbox (message replay on reconnect) ---

    def _outbox_append(self, device_id: str, seq: int, payload: dict, envelope: dict) -> None:
        """Append a sent message to the device's outbox."""
        if device_id not in self._outboxes:
            self._outboxes[device_id] = deque(maxlen=OUTBOX_MAX_SIZE)
        self._outboxes[device_id].append(OutboxEntry(seq=seq, payload=payload, envelope=envelope))

    def get_missed_messages(self, device_id: str, last_seq: int) -> list[dict]:
        """Return outbox envelopes with seq > last_seq that haven't expired."""
        outbox = self._outboxes.get(device_id)
        if not outbox:
            return []
        return [entry.envelope for entry in outbox if entry.seq > last_seq and not entry.is_expired]

    def cleanup_outbox(self, device_id: str) -> None:
        """Remove expired entries from a device's outbox."""
        outbox = self._outboxes.get(device_id)
        if not outbox:
            return
        while outbox and outbox[0].is_expired:
            outbox.popleft()
        if not outbox:
            del self._outboxes[device_id]

    # --- Subscriptions & broadcast ---

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
