"""Device pairing and lifecycle management for Comobot Remote."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from loguru import logger

from comobot.db.connection import Database
from comobot.security.auth import AuthManager
from comobot.security.nacl_crypto import generate_keypair


class DeviceManager:
    """Manages remote device pairing via QR code and device lifecycle."""

    PAIRING_TOKEN_TTL_MINUTES = 5

    def __init__(self, db: Database, auth: AuthManager):
        self.db = db
        self.auth = auth

    async def create_pairing_token(self, server_url: str = "") -> dict:
        """Generate a QR pairing token with a temporary server keypair.

        Args:
            server_url: The server URL to include in QR data so the mobile app
                        knows where to connect (e.g. "http://192.168.1.10:18790").

        Returns dict with: token, server_public_key, expires_at, qr_data
        """
        keypair = generate_keypair()
        token = f"qr_{uuid.uuid4().hex}"
        expires_at = datetime.utcnow() + timedelta(minutes=self.PAIRING_TOKEN_TTL_MINUTES)
        expires_str = expires_at.isoformat()

        await self.db.execute(
            "INSERT INTO pairing_tokens (token, server_public_key, server_secret_key, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token, keypair.public_key_b64, keypair.secret_key_b64, expires_str),
        )

        qr_data: dict = {
            "v": 1,
            "token": token,
            "pk": keypair.public_key_b64,
        }
        if server_url:
            qr_data["server"] = server_url

        logger.info("Created pairing token (expires {})", expires_str)
        return {
            "qr_token": token,
            "server_public_key": keypair.public_key_b64,
            "expires_at": expires_str,
            "qr_data": json.dumps(qr_data),
        }

    async def confirm_pairing(
        self,
        token: str,
        device_public_key: str,
        device_name: str,
        device_os: str,
    ) -> dict | None:
        """Validate pairing token and create device record.

        Returns dict with: access_token, refresh_token, device_id, server_public_key
        Or None if the token is invalid/expired/used.
        """
        row = await self.db.fetchone("SELECT * FROM pairing_tokens WHERE token = ?", (token,))
        if not row:
            logger.warning("Pairing failed: token not found")
            return None
        if row["used"]:
            logger.warning("Pairing failed: token already used")
            return None

        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.utcnow() > expires_at:
            logger.warning("Pairing failed: token expired")
            return None

        # Mark token as used
        await self.db.execute("UPDATE pairing_tokens SET used = 1 WHERE token = ?", (token,))

        # Create device record
        device_id = uuid.uuid4().hex
        await self.db.execute(
            "INSERT INTO remote_devices "
            "(id, device_name, device_os, device_public_key, server_public_key, server_secret_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                device_id,
                device_name,
                device_os,
                device_public_key,
                row["server_public_key"],
                row["server_secret_key"],
            ),
        )

        # Issue tokens
        access_token = self.auth.create_device_token(device_id)
        refresh_token = self.auth.create_refresh_token(device_id)

        logger.info("Device paired: {} ({} / {})", device_id, device_name, device_os)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "device_id": device_id,
            "server_public_key": row["server_public_key"],
        }

    async def refresh_device_token(self, device_id: str) -> dict | None:
        """Issue a new access token for a valid device."""
        device = await self.get_device(device_id)
        if not device or not device["is_active"]:
            return None
        access_token = self.auth.create_device_token(device_id)
        return {"access_token": access_token}

    async def list_devices(self) -> list[dict]:
        """List all paired devices."""
        return await self.db.fetchall(
            "SELECT id, device_name, device_os, paired_at, last_seen_at, is_active, push_token "
            "FROM remote_devices ORDER BY paired_at DESC"
        )

    async def get_device(self, device_id: str) -> dict | None:
        """Get a device by ID."""
        return await self.db.fetchone("SELECT * FROM remote_devices WHERE id = ?", (device_id,))

    async def remove_device(self, device_id: str) -> bool:
        """Deactivate a paired device."""
        cursor = await self.db.execute(
            "UPDATE remote_devices SET is_active = 0 WHERE id = ?", (device_id,)
        )
        if cursor.rowcount > 0:
            logger.info("Device deactivated: {}", device_id)
            return True
        return False

    async def update_push_token(self, device_id: str, push_token: str) -> bool:
        """Register or update the push notification token for a device."""
        cursor = await self.db.execute(
            "UPDATE remote_devices SET push_token = ? WHERE id = ? AND is_active = 1",
            (push_token, device_id),
        )
        return cursor.rowcount > 0

    async def touch_device(self, device_id: str) -> None:
        """Update the last_seen_at timestamp."""
        await self.db.execute(
            "UPDATE remote_devices SET last_seen_at = datetime('now') WHERE id = ?",
            (device_id,),
        )
